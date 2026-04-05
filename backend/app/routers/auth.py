from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field

from ..config import settings
from ..core.database import extract_single, get_supabase_client
from ..core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    hash_token,
    is_refresh_token_valid,
    is_token_blocklisted,
    oauth2_scheme,
    revoke_refresh_token,
    store_refresh_token,
    validate_password_policy,
    verify_password,
)

router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str | None = None
    organization: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ProfileUpdateRequest(BaseModel):
    full_name: str | None = None
    organization: str | None = None


def _set_csrf_cookie(response: Response, csrf_token: str) -> None:
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=settings.CSRF_COOKIE_SECURE,
        samesite="lax",
        max_age=7 * 24 * 3600,
    )


def _serialize_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(user.get("id", "")),
        "email": user.get("email"),
        "full_name": user.get("full_name"),
        "organization": user.get("organization"),
        "created_at": user.get("created_at"),
    }


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, response: Response) -> dict[str, Any]:
    validate_password_policy(payload.password)

    try:
        supabase = get_supabase_client()
        existing = (
            supabase.table("users")
            .select("id")
            .eq("email", payload.email.lower())
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to verify existing user.",
        ) from exc

    if extract_single(existing) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email address is already registered.",
        )

    try:
        insert_response = (
            supabase.table("users")
            .insert(
                {
                    "email": payload.email.lower(),
                    "hashed_password": hash_password(payload.password),
                    "full_name": payload.full_name,
                    "organization": payload.organization,
                    "is_active": True,
                }
            )
            .execute()
        )
        user = extract_single(insert_response)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create user account.",
        ) from exc

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User account was not created.",
        )

    token_payload = {"sub": user["email"], "user_id": str(user["id"])}
    access_token = create_access_token(token_payload)
    refresh_token = create_refresh_token(token_payload)
    refresh_token_data = decode_token(refresh_token)
    store_refresh_token(str(user["id"]), refresh_token, refresh_token_data)
    csrf_token = secrets.token_urlsafe(32)
    _set_csrf_cookie(response, csrf_token)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "csrf_token": csrf_token,
        "user": _serialize_user(user),
    }


@router.post("/login")
async def login(payload: LoginRequest, response: Response) -> dict[str, Any]:
    try:
        supabase = get_supabase_client()
        result = (
            supabase.table("users")
            .select("id,email,hashed_password,full_name,organization,created_at,is_active")
            .eq("email", payload.email.lower())
            .limit(1)
            .execute()
        )
        user = extract_single(result)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to verify credentials.",
        ) from exc

    if user is None or not verify_password(payload.password, str(user["hashed_password"])):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled.",
        )

    token_payload = {"sub": user["email"], "user_id": str(user["id"])}
    access_token = create_access_token(token_payload)
    refresh_token = create_refresh_token(token_payload)
    refresh_token_data = decode_token(refresh_token)
    store_refresh_token(str(user["id"]), refresh_token, refresh_token_data)
    csrf_token = secrets.token_urlsafe(32)
    _set_csrf_cookie(response, csrf_token)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "csrf_token": csrf_token,
        "user": _serialize_user(user),
    }


@router.post("/refresh")
async def refresh_token(payload: RefreshRequest, response: Response) -> dict[str, Any]:
    if is_token_blocklisted(payload.refresh_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked.",
        )

    if not is_refresh_token_valid(payload.refresh_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is inactive or expired.",
        )

    token_data = decode_token(payload.refresh_token)
    if token_data.token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
        )

    token_payload = {"sub": token_data.email, "user_id": token_data.user_id}
    access_token = create_access_token(token_payload)
    revoke_refresh_token(payload.refresh_token)
    new_refresh_token = create_refresh_token(token_payload)
    new_refresh_data = decode_token(new_refresh_token)
    store_refresh_token(token_data.user_id, new_refresh_token, new_refresh_data)
    csrf_token = secrets.token_urlsafe(32)
    _set_csrf_cookie(response, csrf_token)

    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "csrf_token": csrf_token,
    }


@router.get("/me")
async def me(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {"user": current_user}


@router.put("/profile")
async def update_profile(
    payload: ProfileUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    updates = {
        "full_name": payload.full_name,
        "organization": payload.organization,
        "updated_at": datetime.now(UTC).isoformat(),
    }

    cleaned_updates = {key: value for key, value in updates.items() if value is not None}
    if len(cleaned_updates) == 1 and "updated_at" in cleaned_updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No profile updates were provided.",
        )

    try:
        supabase = get_supabase_client()
        supabase.table("users").update(cleaned_updates).eq("id", current_user["id"]).execute()
        refresh_result = (
            supabase.table("users")
            .select("id,email,full_name,organization,created_at")
            .eq("id", current_user["id"])
            .limit(1)
            .execute()
        )
        updated_user = extract_single(refresh_result)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update user profile.",
        ) from exc

    if updated_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found.",
        )

    return {"user": _serialize_user(updated_user)}


@router.post("/logout")
async def logout(
    response: Response,
    token: str = Depends(oauth2_scheme),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    token_data = decode_token(token)

    try:
        supabase = get_supabase_client()
        supabase.table("token_blocklist").insert(
            {
                "token_hash": hash_token(token),
                "token_jti": token_data.jti,
                "user_id": current_user["id"],
                "expires_at": datetime.fromtimestamp(token_data.exp, tz=UTC).isoformat(),
                "created_at": datetime.now(UTC).isoformat(),
            }
        ).execute()
        supabase.table("refresh_tokens").update(
            {
                "is_active": False,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ).eq("user_id", current_user["id"]).eq("is_active", True).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to invalidate token. Ensure token_blocklist table exists.",
        ) from exc

    response.delete_cookie("csrf_token")
    return {"message": "Successfully logged out."}
