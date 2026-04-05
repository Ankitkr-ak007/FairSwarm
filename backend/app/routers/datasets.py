from __future__ import annotations

import os
import tempfile
from pathlib import PurePath
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from ..config import settings
from ..core.database import extract_list, extract_single, get_supabase_client
from ..core.security import (
	UPLOADS_PER_DAY_LIMIT,
	detect_csv_injection,
	detect_excel_embedded_scripts,
	enforce_user_rate_limit,
	get_current_user,
	sanitize_column_names,
	validate_upload_magic_bytes,
)
from ..services.dataset_processor import DatasetProcessor

router = APIRouter()
processor = DatasetProcessor()


def _validate_filename(filename: str) -> None:
	if not filename:
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required.")

	normalized = PurePath(filename)
	if normalized.name != filename or ".." in filename or "/" in filename or "\\" in filename:
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename detected.")


def _parse_extension(filename: str) -> str:
	extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
	if extension == "xls":
		extension = "xlsx"
	return extension


def _serialize_records(df: pd.DataFrame, limit: int) -> list[dict[str, Any]]:
	trimmed = df.head(limit).replace({np.nan: None})
	return trimmed.to_dict(orient="records")


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_dataset(
	file: UploadFile = File(...),
	current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
	_validate_filename(file.filename or "")
	extension = _parse_extension(file.filename or "")
	if extension not in settings.ALLOWED_EXTENSIONS:
		raise HTTPException(
			status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
			detail="Only CSV, Excel, and JSON files are supported.",
		)

	file_bytes = await file.read()
	max_size_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
	if len(file_bytes) > max_size_bytes:
		raise HTTPException(
			status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
			detail=f"File exceeds {settings.MAX_FILE_SIZE_MB}MB limit.",
		)

	validate_upload_magic_bytes(file.filename or "", file_bytes)
	if extension == "csv":
		injection_issues = detect_csv_injection(file_bytes)
		if injection_issues:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail=(
					"Potential CSV injection detected. Remove cells starting with =, +, -, or @. "
					f"First issue at row {injection_issues[0]['row']} col {injection_issues[0]['column']}."
				),
			)

	if extension == "xlsx" and detect_excel_embedded_scripts(file_bytes):
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Excel file contains embedded scripts/macros and cannot be processed.",
		)

	enforce_user_rate_limit(
		user_id=current_user["id"],
		action="dataset_upload",
		limit=UPLOADS_PER_DAY_LIMIT,
		window_seconds=24 * 60 * 60,
	)

	storage_path = f"{current_user['id']}/{uuid4()}.{extension}"
	temp_path: str | None = None

	try:
		supabase = get_supabase_client()
		supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
			path=storage_path,
			file=file_bytes,
			file_options={
				"content-type": file.content_type or "application/octet-stream",
				"upsert": "false",
			},
		)

		with tempfile.NamedTemporaryFile(delete=False, suffix=f".{extension}") as temp_file:
			temp_file.write(file_bytes)
			temp_path = temp_file.name

		df = processor.load_dataset(temp_path, extension)
		df.columns = sanitize_column_names([str(column) for column in df.columns])
		profile = processor.profile_dataset(df)
		sensitive_columns = processor.detect_sensitive_columns(df)
		validation = processor.validate_dataset(df)

		insert_response = (
			supabase.table("datasets")
			.insert(
				{
					"user_id": current_user["id"],
					"name": file.filename,
					"description": f"Uploaded dataset ({extension.upper()})",
					"file_path": storage_path,
					"file_size": len(file_bytes),
					"columns": profile,
					"row_count": profile["row_count"],
					"sensitive_columns": sensitive_columns,
					"status": "uploaded" if validation.is_valid else "needs_review",
				}
			)
			.execute()
		)
		dataset_record = extract_single(insert_response)
	except HTTPException:
		raise
	except Exception as exc:
		try:
			get_supabase_client().storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove([storage_path])
		except Exception:
			pass
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=f"Failed to upload dataset: {exc}",
		) from exc
	finally:
		if temp_path and os.path.exists(temp_path):
			os.unlink(temp_path)

	if dataset_record is None:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Dataset metadata could not be created.",
		)

	return {
		"dataset_id": str(dataset_record["id"]),
		"profile": profile,
		"detected_sensitive_cols": sensitive_columns,
		"validation": validation.model_dump(),
	}


@router.get("/")
async def list_datasets(
	page: int = Query(default=1, ge=1),
	current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
	page_size = 20
	offset = (page - 1) * page_size

	try:
		supabase = get_supabase_client()
		result = (
			supabase.table("datasets")
			.select("id,name,file_size,row_count,sensitive_columns,status,created_at", count="exact")
			.eq("user_id", current_user["id"])
			.neq("status", "deleted")
			.order("created_at", desc=True)
			.range(offset, offset + page_size - 1)
			.execute()
		)
		rows = extract_list(result)
		total = int(getattr(result, "count", 0) or 0)
	except Exception as exc:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Unable to list datasets.",
		) from exc

	return {
		"items": rows,
		"page": page,
		"page_size": page_size,
		"total": total,
	}


@router.get("/{dataset_id}")
async def get_dataset(
	dataset_id: str,
	current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
	try:
		supabase = get_supabase_client()
		result = (
			supabase.table("datasets")
			.select("*")
			.eq("id", dataset_id)
			.eq("user_id", current_user["id"])
			.neq("status", "deleted")
			.limit(1)
			.execute()
		)
		dataset = extract_single(result)
	except Exception as exc:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Unable to fetch dataset details.",
		) from exc

	if dataset is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
	return dataset


@router.delete("/{dataset_id}")
async def delete_dataset(
	dataset_id: str,
	current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
	try:
		supabase = get_supabase_client()
		dataset_result = (
			supabase.table("datasets")
			.select("id,file_path")
			.eq("id", dataset_id)
			.eq("user_id", current_user["id"])
			.limit(1)
			.execute()
		)
		dataset = extract_single(dataset_result)
	except Exception as exc:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Unable to verify dataset.",
		) from exc

	if dataset is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")

	try:
		if dataset.get("file_path"):
			supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove([dataset["file_path"]])

		supabase.table("datasets").update({"status": "deleted"}).eq("id", dataset_id).execute()
	except Exception as exc:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Unable to delete dataset.",
		) from exc

	return {"message": "Dataset deleted successfully."}


@router.get("/{dataset_id}/preview")
async def preview_dataset(
	dataset_id: str,
	current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
	try:
		supabase = get_supabase_client()
		result = (
			supabase.table("datasets")
			.select("id,name,file_path")
			.eq("id", dataset_id)
			.eq("user_id", current_user["id"])
			.neq("status", "deleted")
			.limit(1)
			.execute()
		)
		dataset = extract_single(result)
	except Exception as exc:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Unable to retrieve dataset metadata.",
		) from exc

	if dataset is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")

	file_path = str(dataset.get("file_path"))
	extension = _parse_extension(file_path)
	temp_path: str | None = None

	try:
		file_bytes = supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).download(file_path)
		with tempfile.NamedTemporaryFile(delete=False, suffix=f".{extension}") as temp_file:
			temp_file.write(file_bytes)
			temp_path = temp_file.name

		df = processor.load_dataset(temp_path, extension)
		preview = _serialize_records(df, limit=20)
	except Exception as exc:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail=f"Unable to generate dataset preview: {exc}",
		) from exc
	finally:
		if temp_path and os.path.exists(temp_path):
			os.unlink(temp_path)

	return {
		"dataset_id": dataset_id,
		"rows": preview,
		"row_count": len(preview),
	}
