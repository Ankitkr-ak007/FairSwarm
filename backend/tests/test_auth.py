from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException, Response

from app.core.security import decode_token, hash_password
from app.routers import auth as auth_router


@pytest.mark.asyncio
async def test_register_creates_user_and_tokens(patch_supabase):
    payload = auth_router.RegisterRequest(
        email="alice@example.com",
        password="Strong@123",
        full_name="Alice",
        organization="Fair Org",
    )
    response = Response()

    result = await auth_router.register(payload, response)

    assert result["token_type"] == "bearer"
    assert result["user"]["email"] == "alice@example.com"
    assert len(patch_supabase.tables["users"]) == 1
    assert len(patch_supabase.tables["refresh_tokens"]) == 1


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(patch_supabase):
    patch_supabase.tables["users"].append(
        {
            "id": "u1",
            "email": "dup@example.com",
            "hashed_password": hash_password("Strong@123"),
            "is_active": True,
        }
    )

    payload = auth_router.RegisterRequest(
        email="dup@example.com",
        password="Strong@123",
    )

    with pytest.raises(HTTPException) as exc:
        await auth_router.register(payload, Response())

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_login_refresh_and_logout_flow(patch_supabase):
    patch_supabase.tables["users"].append(
        {
            "id": "u-login",
            "email": "login@example.com",
            "hashed_password": hash_password("Strong@123"),
            "full_name": "Login User",
            "organization": "Fair Org",
            "created_at": datetime.now(UTC).isoformat(),
            "is_active": True,
        }
    )

    login_result = await auth_router.login(
        auth_router.LoginRequest(email="login@example.com", password="Strong@123"),
        Response(),
    )

    assert login_result["token_type"] == "bearer"
    old_refresh = login_result["refresh_token"]

    refresh_result = await auth_router.refresh_token(
        auth_router.RefreshRequest(refresh_token=old_refresh),
        Response(),
    )

    assert refresh_result["refresh_token"] != old_refresh
    assert len(patch_supabase.tables["refresh_tokens"]) >= 1

    access_token = login_result["access_token"]
    token_data = decode_token(access_token)
    current_user = {"id": token_data.user_id, "email": token_data.email}

    logout_result = await auth_router.logout(
        Response(),
        token=access_token,
        current_user=current_user,
    )

    assert logout_result["message"].lower().startswith("success")
    assert len(patch_supabase.tables["token_blocklist"]) == 1


@pytest.mark.asyncio
async def test_login_rejects_invalid_credentials(patch_supabase):
    patch_supabase.tables["users"].append(
        {
            "id": "u2",
            "email": "invalid@example.com",
            "hashed_password": hash_password("Strong@123"),
            "is_active": True,
        }
    )

    with pytest.raises(HTTPException) as exc:
        await auth_router.login(
            auth_router.LoginRequest(email="invalid@example.com", password="Wrong@123"),
            Response(),
        )

    assert exc.value.status_code == 401
