from __future__ import annotations

import time
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.middleware import InputSanitizationMiddleware
from app.core.security import (
    create_access_token,
    decode_token,
    detect_csv_injection,
    enforce_user_rate_limit,
)


def test_rate_limiting_triggers_after_threshold(patch_supabase):
    enforce_user_rate_limit("user-1", "analysis_start", limit=2, window_seconds=3600)
    enforce_user_rate_limit("user-1", "analysis_start", limit=2, window_seconds=3600)

    with pytest.raises(Exception) as exc:
        enforce_user_rate_limit("user-1", "analysis_start", limit=2, window_seconds=3600)

    assert "Rate limit exceeded" in str(exc.value)


def test_jwt_expiry_is_enforced():
    token = create_access_token(
        {"sub": "expiry@example.com", "user_id": "u-exp"},
        expires_delta=timedelta(seconds=1),
    )
    time.sleep(2)

    with pytest.raises(Exception):
        decode_token(token)


def test_csv_injection_detection():
    csv_payload = b"name,value\nalpha,=cmd|' /C calc'!A0\n"
    issues = detect_csv_injection(csv_payload)
    assert len(issues) >= 1


def test_sql_injection_payload_returns_400():
    app = FastAPI()
    app.add_middleware(InputSanitizationMiddleware)

    @app.post("/api/v1/test")
    async def post_test(payload: dict[str, str]):
        return {"ok": True, "payload": payload}

    client = TestClient(app)
    response = client.post("/api/v1/test", json={"query": "' OR 1=1 --"})

    assert response.status_code == 400
    assert "malicious" in response.json()["detail"].lower()
