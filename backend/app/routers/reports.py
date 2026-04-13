from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from pydantic import BaseModel, Field

from ..config import settings
from ..core.database import extract_list, extract_single, get_supabase_client
from ..core.security import get_current_user
from ..services.report_generator import ReportGenerator

router = APIRouter()
report_generator = ReportGenerator()


class BulkReportDownloadRequest(BaseModel):
    analysis_ids: list[str] = Field(default_factory=list, min_length=1, max_length=30)


class ShareReportRequest(BaseModel):
    analysis_id: str


def _fetch_analysis_bundle(analysis_id: str, user_id: str | None = None) -> dict[str, Any]:
    supabase = get_supabase_client()

    analysis_query = supabase.table("analyses").select("*").eq("id", analysis_id).limit(1)
    if user_id:
        analysis_query = analysis_query.eq("user_id", user_id)

    analysis_result = analysis_query.execute()
    analysis = extract_single(analysis_result)
    if analysis is None:
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
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")

    dataset_result = (
        supabase.table("datasets")
        .select("id,name,row_count,columns,sensitive_columns,created_at")
        .eq("id", analysis["dataset_id"])
        .limit(1)
        .execute()
    )
    dataset = extract_single(dataset_result)

    swarm_result = (
        supabase.table("ai_swarm_results")
        .select("*")
        .eq("analysis_id", analysis_id)
        .order("created_at", desc=False)
        .execute()
    )

    return {
        "analysis": analysis,
        "report": report,
        "dataset": dataset,
        "swarm_results": extract_list(swarm_result),
    }


def _extract_metric_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    fairness_metrics = report.get("fairness_metrics") or {}
    by_attr = fairness_metrics.get("metrics_by_sensitive_attribute", {})
    rows: list[dict[str, Any]] = []
    if not isinstance(by_attr, dict):
        return rows

    for attr, payload in by_attr.items():
        if not isinstance(payload, dict):
            continue
        metric_entries = payload.get("metrics", [])
        if not isinstance(metric_entries, list):
            continue
        for metric in metric_entries:
            if not isinstance(metric, dict):
                continue
            rows.append({"sensitive_attribute": attr, **metric})
    return rows


def _top_findings(metric_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    biased = [row for row in metric_rows if not bool(row.get("is_fair", False))]
    sorted_rows = sorted(
        biased,
        key=lambda row: severity_order.get(str(row.get("severity", "low")), 0),
        reverse=True,
    )
    return sorted_rows[:3]


def _issue_share_token(analysis_id: str, expires_at: datetime) -> str:
    payload = {
        "type": "report_share",
        "analysis_id": analysis_id,
        "exp": expires_at,
        "iat": datetime.now(UTC),
    }
    return str(jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM))


def _verify_share_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired share link.") from exc

    if payload.get("type") != "report_share" or not payload.get("analysis_id"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid share token payload.")

    return str(payload["analysis_id"])


def _parse_iso_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


@router.get("/")
async def list_reports(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    grade: Literal["A", "B", "C", "D", "E", "F"] | None = Query(default=None),
    dataset_id: str | None = Query(default=None),
    sort: Literal["newest", "worst_bias_score", "best_bias_score"] = Query(default="newest"),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    supabase = get_supabase_client()

    try:
        analyses_result = (
            supabase.table("analyses")
            .select("id,dataset_id,created_at,swarm_config")
            .eq("user_id", current_user["id"])
            .execute()
        )
        analysis_rows = extract_list(analyses_result)
        analysis_ids = [str(row.get("id")) for row in analysis_rows]
        if not analysis_ids:
            return {"items": [], "page": page, "page_size": page_size, "total": 0}

        report_result = (
            supabase.table("bias_reports")
            .select("id,analysis_id,overall_score,sensitive_attribute,created_at")
            .in_("analysis_id", analysis_ids)
            .execute()
        )
        report_rows = extract_list(report_result)

        dataset_ids = list({str(item.get("dataset_id")) for item in analysis_rows if item.get("dataset_id")})
        dataset_map: dict[str, dict[str, Any]] = {}
        if dataset_ids:
            datasets_result = (
                supabase.table("datasets")
                .select("id,name")
                .in_("id", dataset_ids)
                .execute()
            )
            dataset_map = {str(item["id"]): item for item in extract_list(datasets_result)}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to list reports.",
        ) from exc

    analysis_map = {str(item["id"]): item for item in analysis_rows}

    items: list[dict[str, Any]] = []
    for report in report_rows:
        analysis_id = str(report.get("analysis_id"))
        analysis = analysis_map.get(analysis_id)
        if not analysis:
            continue

        dataset_ref = str(analysis.get("dataset_id", ""))
        score = float(report.get("overall_score") or 0.0)
        fair_grade = report_generator.grade_from_score(score)

        items.append(
            {
                "id": str(report.get("id")),
                "analysis_id": analysis_id,
                "project_name": str((analysis.get("swarm_config") or {}).get("analysis_name") or f"Analysis {analysis_id[:8]}"),
                "dataset_id": dataset_ref,
                "dataset_name": str((dataset_map.get(dataset_ref) or {}).get("name") or dataset_ref or "Unknown"),
                "overall_score": score,
                "fairness_grade": fair_grade,
                "sensitive_attribute": report.get("sensitive_attribute"),
                "created_at": report.get("created_at") or analysis.get("created_at"),
            }
        )

    if grade:
        effective_grade = "F" if grade == "E" else grade
        items = [item for item in items if item.get("fairness_grade") == effective_grade]

    if dataset_id:
        items = [item for item in items if item.get("dataset_id") == dataset_id]

    if start_date:
        start_dt = _parse_iso_datetime(start_date)
        items = [item for item in items if _parse_iso_datetime(str(item["created_at"])) >= start_dt]

    if end_date:
        end_dt = _parse_iso_datetime(end_date)
        items = [item for item in items if _parse_iso_datetime(str(item["created_at"])) <= end_dt]

    if sort == "worst_bias_score":
        items.sort(key=lambda item: float(item.get("overall_score") or 0.0))
    elif sort == "best_bias_score":
        items.sort(key=lambda item: float(item.get("overall_score") or 0.0), reverse=True)
    else:
        items.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)

    total = len(items)
    offset = (page - 1) * page_size
    paginated = items[offset : offset + page_size]

    return {
        "items": paginated,
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.post("/bulk-download")
async def bulk_download_reports(
    payload: BulkReportDownloadRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
    archive = io.BytesIO()

    with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for analysis_id in payload.analysis_ids:
            bundle = _fetch_analysis_bundle(analysis_id, current_user["id"])
            pdf_bytes = report_generator.build_pdf_report(
                analysis=bundle["analysis"],
                dataset=bundle.get("dataset"),
                bias_report=bundle["report"],
                swarm_results=bundle.get("swarm_results", []),
                organization_name=str(current_user.get("organization") or current_user.get("full_name") or "FairSwarm User"),
            )
            zf.writestr(f"fairswarm-report-{analysis_id}.pdf", pdf_bytes)

    archive.seek(0)
    filename = f"fairswarm-reports-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.zip"
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/share")
async def create_report_share_link(
    payload: ShareReportRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    _fetch_analysis_bundle(payload.analysis_id, current_user["id"])

    expires_at = datetime.now(UTC) + timedelta(days=7)
    token = _issue_share_token(payload.analysis_id, expires_at)
    share_url = str(request.base_url).rstrip("/") + f"/api/v1/reports/public/{token}"

    return {
        "share_url": share_url,
        "expires_at": expires_at.isoformat(),
    }


@router.get("/public/{share_token}")
async def get_public_report_json(share_token: str) -> dict[str, Any]:
    analysis_id = _verify_share_token(share_token)
    bundle = _fetch_analysis_bundle(analysis_id)
    metric_rows = _extract_metric_rows(bundle["report"])

    report_json = report_generator.build_json_report(
        analysis=bundle["analysis"],
        dataset=bundle.get("dataset"),
        bias_report=bundle["report"],
        swarm_results=bundle.get("swarm_results", []),
    )
    report_json["top_findings"] = _top_findings(metric_rows)
    return report_json


@router.get("/public/{share_token}/pdf")
async def get_public_report_pdf(share_token: str) -> StreamingResponse:
    analysis_id = _verify_share_token(share_token)
    bundle = _fetch_analysis_bundle(analysis_id)
    pdf_bytes = report_generator.build_pdf_report(
        analysis=bundle["analysis"],
        dataset=bundle.get("dataset"),
        bias_report=bundle["report"],
        swarm_results=bundle.get("swarm_results", []),
        organization_name="Shared FairSwarm Report",
    )

    filename = f"fairswarm-report-{analysis_id}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"},
    )


@router.get("/{analysis_id}/pdf")
async def get_pdf_report(
    analysis_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
    try:
        bundle = _fetch_analysis_bundle(analysis_id, current_user["id"])
        pdf_bytes = report_generator.build_pdf_report(
            analysis=bundle["analysis"],
            dataset=bundle.get("dataset"),
            bias_report=bundle["report"],
            swarm_results=bundle.get("swarm_results", []),
            organization_name=str(current_user.get("organization") or current_user.get("full_name") or "FairSwarm User"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to generate PDF report: {exc}",
        ) from exc

    filename = f"fairswarm-report-{analysis_id}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/{analysis_id}/json")
async def get_json_report(
    analysis_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        bundle = _fetch_analysis_bundle(analysis_id, current_user["id"])
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch report JSON.",
        ) from exc

    metric_rows = _extract_metric_rows(bundle["report"])
    report_json = report_generator.build_json_report(
        analysis=bundle["analysis"],
        dataset=bundle.get("dataset"),
        bias_report=bundle["report"],
        swarm_results=bundle.get("swarm_results", []),
    )
    report_json["top_findings"] = _top_findings(metric_rows)
    return report_json
