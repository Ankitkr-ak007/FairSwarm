from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any, Callable

from fastapi import HTTPException, Request, Response, status
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ..config import settings
from .database import get_supabase_client
from .security import mask_sensitive_text

logger = logging.getLogger("fairswarm.middleware")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        allowed_connect = ["'self'", *settings.CORS_ORIGINS]
        connect_src = " ".join(sorted(set(allowed_connect)))
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            f"connect-src {connect_src}; "
            "script-src 'self' https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com data:; "
            "img-src 'self' data: blob:;"
        )
        return response  # type: ignore[no-any-return]


class InputSanitizationMiddleware(BaseHTTPMiddleware):
    _allowed_content_types = (
        "application/json",
        "multipart/form-data",
        "application/x-www-form-urlencoded",
        "text/plain",
    )
    _csrf_exempt_paths = {
        "/health",
        "/docs",
        "/openapi.json",
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/refresh",
    }
    _sqli_pattern = re.compile(
        r"(?i)(\bUNION\b\s+\bSELECT\b|\bDROP\b\s+\bTABLE\b|\bINSERT\b\s+\bINTO\b|\bDELETE\b\s+\bFROM\b|;\s*--|\bOR\b\s+1=1)",
    )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            self._validate_request_size(request)
            self._validate_content_type(request)
            await self._sanitize_body(request)
            self._validate_csrf(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        return await call_next(request)  # type: ignore[no-any-return]

    def _validate_request_size(self, request: Request) -> None:
        content_length = request.headers.get("content-length")
        if not content_length:
            return
        try:
            payload_size = int(content_length)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Content-Length header.",
            ) from exc

        content_type = request.headers.get("content-type", "").lower()
        if content_type.startswith("multipart/form-data"):
            max_size = 50 * 1024 * 1024
        elif content_type.startswith("application/json"):
            max_size = 10 * 1024
        else:
            max_size = settings.MAX_REQUEST_SIZE_MB * 1024 * 1024
        if payload_size > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Request payload exceeds allowed size limit.",
            )

    def _validate_content_type(self, request: Request) -> None:
        if request.method.upper() not in {"POST", "PUT", "PATCH"}:
            return

        content_type = request.headers.get("content-type", "")
        if not content_type:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Content-Type header is required.",
            )

        if not any(content_type.startswith(allowed) for allowed in self._allowed_content_types):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Unsupported Content-Type.",
            )

    async def _sanitize_body(self, request: Request) -> None:
        if request.method.upper() not in {"POST", "PUT", "PATCH"}:
            return

        if request.headers.get("content-type", "").startswith("multipart/form-data"):
            return

        body = await request.body()
        if not body:
            return

        sanitized = body.replace(b"\x00", b"")
        if sanitized != body:
            await self._set_request_body(request, sanitized)

        if request.headers.get("content-type", "").startswith("application/json"):
            try:
                payload = json.loads(sanitized.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid JSON payload.",
                ) from exc

            if self._contains_sqli_pattern(payload):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Potentially malicious SQL-like input detected.",
                )

    async def _set_request_body(self, request: Request, body: bytes) -> None:
        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = receive  # type: ignore[attr-defined]
        request._body = body  # type: ignore[attr-defined]

    def _validate_csrf(self, request: Request) -> None:
        if request.method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
            return
        if request.url.path in self._csrf_exempt_paths:
            return
        if not request.url.path.startswith("/api/v1/"):
            return

        auth_header = request.headers.get("authorization")
        if not auth_header:
            return

        csrf_cookie = request.cookies.get("csrf_token")
        csrf_header = request.headers.get("x-csrf-token")
        if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token missing or invalid.",
            )

    def _contains_sqli_pattern(self, payload: object) -> bool:
        if isinstance(payload, dict):
            return any(self._contains_sqli_pattern(value) for value in payload.values())
        if isinstance(payload, list):
            return any(self._contains_sqli_pattern(item) for item in payload)
        if isinstance(payload, str):
            return bool(self._sqli_pattern.search(payload))
        return False


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        user_id = self._extract_user_id(request)
        ip_address = request.client.host if request.client else None
        action = mask_sensitive_text(f"{request.method} {request.url.path}")

        try:
            supabase = get_supabase_client()
            supabase.table("audit_logs").insert(
                {
                    "user_id": user_id,
                    "action": action,
                    "resource_type": "http_request",
                    "resource_id": None,
                    "ip_address": ip_address,
                    "created_at": datetime.now(UTC).isoformat(),
                }
            ).execute()
        except Exception as exc:
            logger.warning("Failed to write audit log: %s", mask_sensitive_text(str(exc)))

        return response  # type: ignore[no-any-return]

    def _extract_user_id(self, request: Request) -> str | None:
        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return None

        token = auth_header.split(" ", 1)[1].strip()
        if not token:
            return None

        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            raw_user_id = payload.get("user_id")
            return str(raw_user_id) if raw_user_id else None
        except JWTError:
            return None
