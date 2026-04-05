from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..config import settings
from ..core.database import extract_list, extract_single, get_supabase_client
from ..core.realtime import analysis_ws_manager
from ..core.security import ANALYSES_PER_HOUR_LIMIT, enforce_user_rate_limit, get_current_user
from ..services.ai_swarm_engine import AISwarmEngine
from ..services.dataset_processor import DatasetProcessor
from ..services.fairness_metrics import FairnessMetricsEngine

router = APIRouter()
processor = DatasetProcessor()
metrics_engine = FairnessMetricsEngine()
swarm_engine = AISwarmEngine()


class AnalysisStartRequest(BaseModel):
	dataset_id: str
	sensitive_columns: list[str] = Field(default_factory=list)
	target_column: str
	analysis_name: str | None = None


async def _broadcast_progress(analysis_id: str, status_value: str, progress: int, detail: str) -> None:
	await analysis_ws_manager.broadcast(
		analysis_id,
		{
			"analysis_id": analysis_id,
			"status": status_value,
			"progress": progress,
			"detail": detail,
			"timestamp": datetime.now(UTC).isoformat(),
		},
	)


def _update_analysis(
	analysis_id: str,
	updates: dict[str, Any],
) -> None:
	supabase = get_supabase_client()
	supabase.table("analyses").update(updates).eq("id", analysis_id).execute()


async def _run_swarm_follow_up(
	analysis_id: str,
	fairness_payload: dict[str, Any],
	intersectional_payload: dict[str, Any],
) -> None:
	swarm_consensus = await swarm_engine.run(
		analysis_id=analysis_id,
		fairness_results=fairness_payload,
		intersectional_results=intersectional_payload,
	)

	try:
		supabase = get_supabase_client()
		report_result = (
			supabase.table("bias_reports")
			.select("id")
			.eq("analysis_id", analysis_id)
			.order("created_at", desc=True)
			.limit(1)
			.execute()
		)
		report = extract_single(report_result)
		if report:
			supabase.table("bias_reports").update({"swarm_consensus": swarm_consensus}).eq(
				"id", report["id"]
			).execute()
	except Exception:
		pass


async def _analysis_pipeline(
	analysis_id: str,
	dataset_record: dict[str, Any],
	request_payload: AnalysisStartRequest,
) -> None:
	extension = str(dataset_record.get("file_path", "")).rsplit(".", 1)[-1].lower()
	if extension == "xls":
		extension = "xlsx"

	temp_path: str | None = None
	try:
		_update_analysis(analysis_id, {"status": "running", "progress": 0})
		await _broadcast_progress(analysis_id, "running", 0, "Analysis started")

		supabase = get_supabase_client()
		file_bytes = supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).download(
			str(dataset_record["file_path"])
		)
		with tempfile.NamedTemporaryFile(delete=False, suffix=f".{extension}") as temp_file:
			temp_file.write(file_bytes)
			temp_path = temp_file.name

		df = processor.load_dataset(temp_path, extension)
		binary_dataset, _ = processor.encode_for_analysis(
			df=df,
			sensitive_cols=request_payload.sensitive_columns,
			target_col=request_payload.target_column,
		)

		fairness_by_attribute: dict[str, Any] = {}
		for sensitive_attr in request_payload.sensitive_columns:
			result = metrics_engine.compute_all_metrics(binary_dataset, sensitive_attr)
			fairness_by_attribute[sensitive_attr] = result.model_dump()

		_update_analysis(analysis_id, {"progress": 40})
		await _broadcast_progress(analysis_id, "running", 40, "Fairness metrics computed")

		intersectional = metrics_engine.compute_intersectional_bias(
			df,
			request_payload.sensitive_columns,
			request_payload.target_column,
		)

		_update_analysis(analysis_id, {"progress": 70})
		await _broadcast_progress(analysis_id, "running", 70, "Intersectional analysis complete")

		fairness_scores = [
			float(item.get("fairness_score", 0.0))
			for item in fairness_by_attribute.values()
			if isinstance(item, dict)
		]
		overall_fairness_score = sum(fairness_scores) / max(len(fairness_scores), 1)

		mitigation_items: list[dict[str, str]] = []
		seen_keys: set[tuple[str, str]] = set()
		for attr_result in fairness_by_attribute.values():
			if not isinstance(attr_result, dict):
				continue
			for mitigation in attr_result.get("mitigations", []):
				if not isinstance(mitigation, dict):
					continue
				key = (str(mitigation.get("metric")), str(mitigation.get("strategy")))
				if key in seen_keys:
					continue
				seen_keys.add(key)
				mitigation_items.append({
					"metric": str(mitigation.get("metric")),
					"severity": str(mitigation.get("severity", "medium")),
					"strategy": str(mitigation.get("strategy")),
					"description": str(mitigation.get("description")),
				})

		supabase.table("bias_reports").insert(
			{
				"analysis_id": analysis_id,
				"overall_score": round(overall_fairness_score, 2),
				"fairness_metrics": {
					"metrics_by_sensitive_attribute": fairness_by_attribute,
					"intersectional_bias": intersectional,
				},
				"sensitive_attribute": ",".join(request_payload.sensitive_columns),
				"model_recommendations": mitigation_items,
				"swarm_consensus": {"status": "queued"},
			}
		).execute()

		_update_analysis(analysis_id, {"progress": 90})
		await _broadcast_progress(analysis_id, "running", 90, "Bias report saved")

		asyncio.create_task(_run_swarm_follow_up(analysis_id, fairness_by_attribute, intersectional))

		_update_analysis(
			analysis_id,
			{
				"progress": 100,
				"status": "completed",
				"completed_at": datetime.now(UTC).isoformat(),
			},
		)
		await _broadcast_progress(analysis_id, "completed", 100, "Analysis completed")
	except Exception as exc:
		_update_analysis(
			analysis_id,
			{
				"status": "failed",
				"progress": 100,
				"swarm_config": {"error": str(exc)},
			},
		)
		await _broadcast_progress(analysis_id, "failed", 100, f"Analysis failed: {exc}")
	finally:
		if temp_path and os.path.exists(temp_path):
			os.unlink(temp_path)


@router.post("/start", status_code=status.HTTP_202_ACCEPTED)
async def start_analysis(
	payload: AnalysisStartRequest,
	background_tasks: BackgroundTasks,
	current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
	if not payload.sensitive_columns:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail="At least one sensitive column is required.",
		)

	enforce_user_rate_limit(
		user_id=current_user["id"],
		action="analysis_start",
		limit=ANALYSES_PER_HOUR_LIMIT,
		window_seconds=60 * 60,
	)

	try:
		supabase = get_supabase_client()
		dataset_result = (
			supabase.table("datasets")
			.select("id,file_path,status")
			.eq("id", payload.dataset_id)
			.eq("user_id", current_user["id"])
			.neq("status", "deleted")
			.limit(1)
			.execute()
		)
		dataset_record = extract_single(dataset_result)
	except Exception as exc:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Unable to validate dataset ownership.",
		) from exc

	if dataset_record is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")

	try:
		analysis_result = (
			supabase.table("analyses")
			.insert(
				{
					"dataset_id": payload.dataset_id,
					"user_id": current_user["id"],
					"status": "pending",
					"progress": 0,
					"swarm_config": {
						"analysis_name": payload.analysis_name,
						"sensitive_columns": payload.sensitive_columns,
						"target_column": payload.target_column,
					},
				}
			)
			.execute()
		)
		analysis_record = extract_single(analysis_result)
	except Exception as exc:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Unable to create analysis record.",
		) from exc

	if analysis_record is None:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to start analysis.",
		)

	analysis_id = str(analysis_record["id"])
	background_tasks.add_task(_analysis_pipeline, analysis_id, dataset_record, payload)

	return {
		"analysis_id": analysis_id,
		"status": "pending",
	}


@router.get("/{analysis_id}")
async def get_analysis(
	analysis_id: str,
	current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
	try:
		supabase = get_supabase_client()
		analysis_result = (
			supabase.table("analyses")
			.select("*")
			.eq("id", analysis_id)
			.eq("user_id", current_user["id"])
			.limit(1)
			.execute()
		)
		analysis_record = extract_single(analysis_result)
		if analysis_record is None:
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found.")

		report_result = (
			supabase.table("bias_reports")
			.select("*")
			.eq("analysis_id", analysis_id)
			.order("created_at", desc=True)
			.limit(1)
			.execute()
		)
		report = extract_single(report_result)

		swarm_result = (
			supabase.table("ai_swarm_results")
			.select("*")
			.eq("analysis_id", analysis_id)
			.order("created_at", desc=False)
			.execute()
		)
	except HTTPException:
		raise
	except Exception as exc:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Unable to load analysis data.",
		) from exc

	return {
		"analysis": analysis_record,
		"bias_report": report,
		"swarm_results": extract_list(swarm_result),
	}


@router.get("/")
async def list_analyses(
	page: int = Query(default=1, ge=1),
	page_size: int = Query(default=20, ge=1, le=50),
	current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
	offset = (page - 1) * page_size
	try:
		supabase = get_supabase_client()
		result = (
			supabase.table("analyses")
			.select("id,dataset_id,status,progress,created_at,completed_at", count="exact")
			.eq("user_id", current_user["id"])
			.order("created_at", desc=True)
			.range(offset, offset + page_size - 1)
			.execute()
		)
	except Exception as exc:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Unable to list analyses.",
		) from exc

	return {
		"items": extract_list(result),
		"page": page,
		"page_size": page_size,
		"total": int(getattr(result, "count", 0) or 0),
	}


@router.delete("/{analysis_id}")
async def delete_analysis(
	analysis_id: str,
	current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
	try:
		supabase = get_supabase_client()
		ownership = (
			supabase.table("analyses")
			.select("id")
			.eq("id", analysis_id)
			.eq("user_id", current_user["id"])
			.limit(1)
			.execute()
		)
		if extract_single(ownership) is None:
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found.")

		supabase.table("analyses").delete().eq("id", analysis_id).execute()
	except HTTPException:
		raise
	except Exception as exc:
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Unable to delete analysis.",
		) from exc

	return {"message": "Analysis deleted successfully."}
