from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..config import settings
from ..core.database import extract_list, extract_single, get_supabase_client
from ..core.rate_limit import limiter
from ..core.realtime import analysis_ws_manager
from ..core.security import decode_token, get_current_user
from ..models.schemas import SwarmAnalyzeRequest, SwarmConsensusResult
from ..services.ai_swarm_engine import AISwarmEngine

router = APIRouter()
swarm_engine = AISwarmEngine()


def _ai_rate_limit_key(request: Request) -> str:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        try:
            token_data = decode_token(token)
            return f"user:{token_data.user_id}"
        except Exception:
            pass

    if request.client and request.client.host:
        return f"ip:{request.client.host}"
    return "anonymous"


def _build_swarm_result_rows(analysis_id: str, consensus: SwarmConsensusResult) -> list[dict[str, Any]]:
    now_iso = datetime.now(UTC).isoformat()
    provider_map = {
        "nvidia_llama": "nvidia",
        "google_gemini": "google",
        "groq_llama": "groq",
        "hf_mixtral": "huggingface",
    }
    rows: list[dict[str, Any]] = []
    for agent_result in consensus.agent_results:
        rows.append(
            {
                "analysis_id": analysis_id,
                "model_name": agent_result.agent_name,
                "model_provider": provider_map.get(agent_result.agent_name, "unknown"),
                "bias_findings": {
                    "specialty": agent_result.specialty,
                    "top_finding": agent_result.top_finding,
                    "recommended_action": agent_result.recommended_action,
                    "analysis_reasoning": agent_result.analysis_reasoning,
                    "bias_indicators": [item.model_dump() for item in agent_result.bias_indicators],
                },
                "confidence_score": agent_result.confidence_score,
                "processing_time_ms": None,
                "created_at": now_iso,
            }
        )
    return rows


@router.post("/analyze", response_model=SwarmConsensusResult)
@limiter.limit(f"{settings.AI_RATE_LIMIT}/minute", key_func=_ai_rate_limit_key)
async def analyze_with_swarm(
    request: Request,
    payload: SwarmAnalyzeRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> SwarmConsensusResult:
    _ = request
    supabase = get_supabase_client()

    await analysis_ws_manager.broadcast(
        payload.analysis_id,
        {
            "analysis_id": payload.analysis_id,
            "status": "swarm_running",
            "progress": 5,
            "detail": "Swarm analysis request accepted",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    try:
        ownership = (
            supabase.table("analyses")
            .select("id,dataset_id,status")
            .eq("id", payload.analysis_id)
            .eq("user_id", current_user["id"])
            .limit(1)
            .execute()
        )
        analysis = extract_single(ownership)
        if analysis is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found.")
        if str(analysis.get("dataset_id")) != payload.dataset_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dataset does not match analysis.",
            )

        dataset_result = (
            supabase.table("datasets")
            .select("id,name,row_count,columns,sensitive_columns")
            .eq("id", payload.dataset_id)
            .eq("user_id", current_user["id"])
            .limit(1)
            .execute()
        )
        dataset = extract_single(dataset_result)
        if dataset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")

        report_result = (
            supabase.table("bias_reports")
            .select("id,fairness_metrics")
            .eq("analysis_id", payload.analysis_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        report = extract_single(report_result)
        if report is None or not isinstance(report.get("fairness_metrics"), dict):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fairness metrics not found. Run analysis first.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to prepare swarm analysis: {exc}",
        ) from exc

    await analysis_ws_manager.broadcast(
        payload.analysis_id,
        {
            "analysis_id": payload.analysis_id,
            "status": "swarm_running",
            "progress": 30,
            "detail": "Launching 4-agent AI swarm",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    dataset_profile = dataset.get("columns") if isinstance(dataset.get("columns"), dict) else {}
    dataset_summary = {
        "dataset_id": dataset.get("id"),
        "name": dataset.get("name"),
        "row_count": dataset.get("row_count"),
        "sensitive_columns": payload.sensitive_columns,
        "target_column": payload.target_column,
        "profile": dataset_profile,
    }
    sample_data = {
        "sample_rows": dataset_profile.get("sample_rows", []),
        "null_counts": dataset_profile.get("null_counts", {}),
        "unique_counts": dataset_profile.get("unique_counts", {}),
    }

    try:
        consensus = await swarm_engine.run_swarm_analysis(
            analysis_id=payload.analysis_id,
            dataset_summary=dataset_summary,
            fairness_metrics=report.get("fairness_metrics", {}),
            sensitive_attributes=payload.sensitive_columns,
            target_column=payload.target_column,
            sample_data=sample_data,
            user_id=current_user["id"],
        )
    except RuntimeError as exc:
        await analysis_ws_manager.broadcast(
            payload.analysis_id,
            {
                "analysis_id": payload.analysis_id,
                "status": "swarm_failed",
                "progress": 100,
                "detail": str(exc),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{exc} Suggestion: retry in 1-2 minutes.",
        ) from exc
    except Exception as exc:
        await analysis_ws_manager.broadcast(
            payload.analysis_id,
            {
                "analysis_id": payload.analysis_id,
                "status": "swarm_failed",
                "progress": 100,
                "detail": "Unexpected swarm error",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Swarm analysis failed unexpectedly: {exc}",
        ) from exc

    try:
        rows = _build_swarm_result_rows(payload.analysis_id, consensus)
        if rows:
            supabase.table("ai_swarm_results").insert(rows).execute()

        report_id = report.get("id")
        if report_id:
            supabase.table("bias_reports").update(
                {"swarm_consensus": consensus.model_dump()}
            ).eq("id", report_id).execute()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to persist swarm analysis results: {exc}",
        ) from exc

    await analysis_ws_manager.broadcast(
        payload.analysis_id,
        {
            "analysis_id": payload.analysis_id,
            "status": "swarm_completed",
            "progress": 100,
            "detail": "Swarm consensus generated",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    return consensus


@router.get("/status/{analysis_id}")
@limiter.limit(f"{settings.AI_RATE_LIMIT}/minute", key_func=_ai_rate_limit_key)
async def get_swarm_status(
    request: Request,
    analysis_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    _ = request
    supabase = get_supabase_client()

    try:
        ownership = (
            supabase.table("analyses")
            .select("id,status,progress")
            .eq("id", analysis_id)
            .eq("user_id", current_user["id"])
            .limit(1)
            .execute()
        )
        analysis = extract_single(ownership)
        if analysis is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found.")

        agent_results = (
            supabase.table("ai_swarm_results")
            .select("*")
            .eq("analysis_id", analysis_id)
            .order("created_at", desc=False)
            .execute()
        )
        report_result = (
            supabase.table("bias_reports")
            .select("id,swarm_consensus")
            .eq("analysis_id", analysis_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        report = extract_single(report_result)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load swarm status.",
        ) from exc

    rows = extract_list(agent_results)
    swarm_consensus = report.get("swarm_consensus") if report else None
    if isinstance(swarm_consensus, dict) and int(swarm_consensus.get("agents_completed", 0)) > 0:
        swarm_status = "completed"
    elif rows:
        swarm_status = "running"
    else:
        swarm_status = "pending"

    return {
        "analysis_id": analysis_id,
        "analysis_status": analysis.get("status"),
        "analysis_progress": analysis.get("progress"),
        "swarm_status": swarm_status,
        "agents_completed": len(rows),
        "partial_results": rows,
        "swarm_consensus": swarm_consensus,
    }


@router.get("/analysis/{analysis_id}/results")
@limiter.limit(f"{settings.AI_RATE_LIMIT}/minute", key_func=_ai_rate_limit_key)
async def get_swarm_results_alias(
    request: Request,
    analysis_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return await get_swarm_status(request, analysis_id, current_user)
