from __future__ import annotations

import io

import pytest
from fastapi import HTTPException, UploadFile

from app.config import settings
from app.routers import datasets as datasets_router


def _build_csv(rows: int = 120) -> bytes:
    lines = ["gender,target,feature"]
    for index in range(rows):
        gender = index % 2
        target = 1 if index % 3 else 0
        lines.append(f"{gender},{target},{index}")
    return "\n".join(lines).encode("utf-8")


@pytest.mark.asyncio
async def test_upload_csv_success(patch_supabase):
    file = UploadFile(filename="demo.csv", file=io.BytesIO(_build_csv()))
    current_user = {"id": "user-1", "email": "user@example.com"}

    response = await datasets_router.upload_dataset(file=file, current_user=current_user)

    assert response["dataset_id"]
    assert response["profile"]["row_count"] == 120
    assert len(patch_supabase.tables["datasets"]) == 1


@pytest.mark.asyncio
async def test_upload_rejects_wrong_type(patch_supabase):
    file = UploadFile(filename="bad.exe", file=io.BytesIO(b"not valid"))
    current_user = {"id": "user-2", "email": "user@example.com"}

    with pytest.raises(HTTPException) as exc:
        await datasets_router.upload_dataset(file=file, current_user=current_user)

    assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file(patch_supabase, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "MAX_FILE_SIZE_MB", 1)
    large_csv = b"a,b\n" + (b"1,2\n" * 600000)
    file = UploadFile(filename="large.csv", file=io.BytesIO(large_csv))
    current_user = {"id": "user-3", "email": "user@example.com"}

    with pytest.raises(HTTPException) as exc:
        await datasets_router.upload_dataset(file=file, current_user=current_user)

    assert exc.value.status_code == 413


@pytest.mark.asyncio
async def test_preview_and_delete_dataset(patch_supabase):
    file = UploadFile(filename="preview.csv", file=io.BytesIO(_build_csv()))
    current_user = {"id": "user-4", "email": "user@example.com"}

    uploaded = await datasets_router.upload_dataset(file=file, current_user=current_user)
    dataset_id = uploaded["dataset_id"]

    preview = await datasets_router.preview_dataset(dataset_id=dataset_id, current_user=current_user)
    assert preview["row_count"] > 0

    deleted = await datasets_router.delete_dataset(dataset_id=dataset_id, current_user=current_user)
    assert "deleted" in deleted["message"].lower()
