from __future__ import annotations

import hashlib
import io
import logging
import re
import zipfile
import csv
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import bcrypt
from pydantic import BaseModel

from ..config import settings
from .database import extract_single, get_supabase_client

logger = logging.getLogger("fairswarm.security")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

UPLOADS_PER_DAY_LIMIT = 50
ANALYSES_PER_HOUR_LIMIT = 10
CSV_INJECTION_PREFIXES = ("=", "+", "-", "@")


class TokenData(BaseModel):
    email: str
    user_id: str
    jti: str
    token_type: str = "access"
    exp: int


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        hashed_bytes = hashed_password.encode("utf-8") if isinstance(hashed_password, str) else hashed_password
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_bytes)
    except Exception:
        return False


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("ascii")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def validate_password_policy(password: str) -> None:
    checks = {
        "minimum 8 characters": len(password) >= 8,
        "one uppercase letter": bool(re.search(r"[A-Z]", password)),
        "one lowercase letter": bool(re.search(r"[a-z]", password)),
        "one number": bool(re.search(r"\d", password)),
        "one special character": bool(re.search(r"[^\w\s]", password)),
    }
    failed = [rule for rule, passed in checks.items() if not passed]
    if failed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Password must include {', '.join(failed)}.",
        )

    if password.strip().lower() in load_common_passwords():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password is too common. Please choose a stronger password.",
        )


@lru_cache(maxsize=1)
def load_common_passwords() -> set[str]:
    common_path = Path(__file__).parent / "common_passwords.txt"
    if not common_path.exists():
        logger.warning("common_passwords.txt not found; common-password policy check is degraded")
        return set()

    with common_path.open("r", encoding="utf-8", errors="ignore") as handle:
        return {line.strip().lower() for line in handle if line.strip()}


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=int(getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 60)))
    )
    payload = data.copy()
    payload.update(
        {
            "exp": expire,
            "iat": datetime.now(UTC),
            "jti": str(uuid4()),
            "token_type": "access",
        }
    )
    return str(jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM))


def create_refresh_token(data: dict[str, Any], expires_days: int = 7) -> str:
    days = expires_days or int(getattr(settings, "REFRESH_TOKEN_EXPIRE_DAYS", 7))
    expire = datetime.now(UTC) + timedelta(days=days)
    payload = data.copy()
    payload.update(
        {
            "exp": expire,
            "iat": datetime.now(UTC),
            "jti": str(uuid4()),
            "token_type": "refresh",
        }
    )
    return str(jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM))


def decode_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    email = payload.get("sub")
    user_id = payload.get("user_id")
    jti = payload.get("jti")
    exp = payload.get("exp")
    token_type = payload.get("token_type", "access")
    if not email or not user_id or not jti or exp is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload is invalid.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenData(
        email=str(email),
        user_id=str(user_id),
        jti=str(jti),
        token_type=str(token_type),
        exp=int(exp),
    )


def verify_token(token: str, credentials_exception: HTTPException | None = None) -> TokenData:
    try:
        return decode_token(token)
    except HTTPException:
        if credentials_exception is not None:
            raise credentials_exception
        raise


def store_refresh_token(user_id: str, refresh_token: str, token_data: TokenData) -> None:
    expires_at = datetime.fromtimestamp(token_data.exp, tz=UTC).isoformat()
    token_hash = hash_token(refresh_token)

    supabase = get_supabase_client()
    supabase.table("refresh_tokens").upsert(
        {
            "user_id": user_id,
            "token_hash": token_hash,
            "token_jti": token_data.jti,
            "expires_at": expires_at,
            "is_active": True,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        },
        on_conflict="token_hash",
    ).execute()


def revoke_refresh_token(refresh_token: str) -> None:
    token_hash = hash_token(refresh_token)
    supabase = get_supabase_client()
    supabase.table("refresh_tokens").update(
        {
            "is_active": False,
            "updated_at": datetime.now(UTC).isoformat(),
        }
    ).eq("token_hash", token_hash).execute()


def is_refresh_token_valid(refresh_token: str) -> bool:
    token_hash = hash_token(refresh_token)
    try:
        supabase = get_supabase_client()
        response = (
            supabase.table("refresh_tokens")
            .select("id,is_active,expires_at")
            .eq("token_hash", token_hash)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        row = extract_single(response)
    except Exception as exc:
        logger.warning("Refresh token check failed: %s", exc)
        return False

    if row is None:
        return False

    expires_at = row.get("expires_at")
    if not expires_at:
        return False

    try:
        return datetime.fromisoformat(str(expires_at).replace("Z", "+00:00")) > datetime.now(UTC)
    except ValueError:
        return False


def is_token_blocklisted(token: str) -> bool:
    token_hash = hash_token(token)
    try:
        supabase = get_supabase_client()
        response = (
            supabase.table("token_blocklist")
            .select("id")
            .eq("token_hash", token_hash)
            .limit(1)
            .execute()
        )
        return bool(getattr(response, "data", None))
    except Exception as exc:
        logger.warning("Token blocklist check failed: %s", exc)
        return False


def enforce_user_rate_limit(user_id: str, action: str, limit: int, window_seconds: int) -> None:
    now = datetime.now(UTC)
    window_start = int(now.timestamp()) // window_seconds * window_seconds

    supabase = get_supabase_client()
    key_filter = (
        supabase.table("rate_limit_counters")
        .select("id,count")
        .eq("user_id", user_id)
        .eq("action", action)
        .eq("window_start", window_start)
        .limit(1)
        .execute()
    )
    existing = extract_single(key_filter)

    if existing:
        current_count = int(existing.get("count", 0))
        if current_count >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for {action}. Try again later.",
            )

        supabase.table("rate_limit_counters").update(
            {
                "count": current_count + 1,
                "updated_at": now.isoformat(),
            }
        ).eq("id", existing["id"]).execute()
        return

    supabase.table("rate_limit_counters").insert(
        {
            "user_id": user_id,
            "action": action,
            "window_start": window_start,
            "count": 1,
            "updated_at": now.isoformat(),
        }
    ).execute()


def sanitize_column_name(name: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_\s]", "", str(name)).strip().replace(" ", "_")
    sanitized = re.sub(r"_+", "_", sanitized)
    return sanitized[:128] if sanitized else "column"


def sanitize_column_names(names: list[str]) -> list[str]:
    seen: set[str] = set()
    sanitized_names: list[str] = []
    for name in names:
        base = sanitize_column_name(name)
        candidate = base
        suffix = 1
        while candidate in seen:
            suffix += 1
            candidate = f"{base}_{suffix}"
        seen.add(candidate)
        sanitized_names.append(candidate)
    return sanitized_names


def validate_upload_magic_bytes(filename: str, file_bytes: bytes) -> None:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension == "xls":
        extension = "xlsx"

    if extension == "xlsx":
        if not file_bytes.startswith(b"PK\x03\x04"):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Excel file signature is invalid.",
            )
        return

    if extension == "json":
        head = file_bytes[:512].lstrip()
        if not (head.startswith(b"{") or head.startswith(b"[")):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="JSON signature is invalid.",
            )
        return

    if extension == "csv":
        try:
            file_bytes[:4096].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="CSV encoding is invalid or unsupported.",
            ) from exc
        return

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Unsupported file type.",
    )


def detect_csv_injection(file_bytes: bytes) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    sample_stream = io.StringIO(file_bytes.decode("utf-8", errors="ignore"))
    reader = csv.reader(sample_stream)
    for row_index, row in enumerate(reader, start=1):
        for col_index, cell in enumerate(row, start=1):
            normalized = cell.strip()
            if normalized.startswith(CSV_INJECTION_PREFIXES):
                issues.append(
                    {
                        "row": row_index,
                        "column": col_index,
                        "value": normalized[:40],
                    }
                )
                if len(issues) >= 25:
                    return issues
    return issues


def detect_excel_embedded_scripts(file_bytes: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            names = {name.lower() for name in archive.namelist()}
            markers = {"xl/vbaproject.bin", "xl/macrosheets", "customui/customui.xml"}
            return any(marker in name for marker in markers for name in names)
    except zipfile.BadZipFile:
        return False


def mask_email(value: str | None) -> str:
    if not value or "@" not in value:
        return "***"
    local, domain = value.split("@", 1)
    if len(local) <= 2:
        local_masked = "*" * len(local)
    else:
        local_masked = local[:1] + "***" + local[-1:]
    return f"{local_masked}@{domain}"


def mask_api_key(value: str | None) -> str:
    if not value:
        return "***"
    if len(value) <= 6:
        return f"{value[:2]}***"
    return f"{value[:4]}***"


def mask_sensitive_text(text: str) -> str:
    masked = re.sub(r"([A-Za-z0-9._%+-]{1,64})@([A-Za-z0-9.-]+\.[A-Za-z]{2,})", lambda m: mask_email(m.group(0)), text)
    masked = re.sub(r"\b(sk|api|hf|gsk|nvapi)[A-Za-z0-9_-]{6,}\b", lambda m: mask_api_key(m.group(0)), masked, flags=re.IGNORECASE)
    return masked


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict[str, Any]:
    if is_token_blocklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = decode_token(token)
    if token_data.token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        supabase = get_supabase_client()
        result = (
            supabase.table("users")
            .select("id,email,full_name,organization,is_active,created_at")
            .eq("id", token_data.user_id)
            .limit(1)
            .execute()
        )
        user = extract_single(result)
    except Exception as exc:
        logger.exception("Failed to fetch current user")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load user profile.",
        ) from exc

    if user is None or not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is not active.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "id": str(user["id"]),
        "email": user["email"],
        "full_name": user.get("full_name"),
        "organization": user.get("organization"),
        "created_at": user.get("created_at"),
    }
