"""Report generation and download endpoints (PDF / Excel)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models import Report
from app.schemas import ReportCreate, ReportRead
from app.services import crop_service, report_service

router = APIRouter(prefix="/reports", tags=["reports"])

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@router.post("", response_model=ReportRead, summary="Generate a PDF or Excel report")
def create_report(payload: ReportCreate, session: DbSession, user: CurrentUser) -> ReportRead:
    if payload.report_type == "crop_cycle" and payload.crop_cycle_id is None:
        raise ValidationError(
            "crop_cycle_id is required for a crop_cycle report.",
            details={"field": "crop_cycle_id"},
        )

    # Select the cycles that belong in this report.
    if payload.crop_cycle_id is not None:
        cycles = [crop_service.get_cycle(session, user.id, payload.crop_cycle_id)]
    else:
        cycles = crop_service.all_user_cycles(session, user)
        if payload.season:
            cycles = [c for c in cycles if c.season == payload.season]

    if payload.file_format == "pdf":
        buffer, filename = report_service.build_financial_pdf(
            user_name=user.full_name, cycles=cycles
        )
    else:
        buffer, filename = report_service.build_financial_workbook(
            user_name=user.full_name, cycles=cycles
        )

    _path, size = report_service.persist(buffer, filename)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.report_ttl_minutes)

    record = Report(
        user_id=user.id,
        report_type=payload.report_type,
        file_format=payload.file_format,
        filename=filename,
        size_bytes=size,
        expires_at=expires_at,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    result = ReportRead.model_validate(record)
    result.download_url = f"{settings.api_v1_prefix}/reports/{record.id}/download"
    return result


@router.get("", response_model=list[ReportRead], summary="List my generated reports")
def list_reports(session: DbSession, user: CurrentUser, limit: int = Query(default=20, ge=1, le=100)):
    from sqlalchemy import select

    rows = list(
        session.scalars(
            select(Report)
            .where(Report.user_id == user.id)
            .order_by(Report.created_at.desc())
            .limit(limit)
        )
    )
    results = []
    for row in rows:
        item = ReportRead.model_validate(row)
        item.download_url = f"{settings.api_v1_prefix}/reports/{row.id}/download"
        results.append(item)
    return results


@router.get("/{report_id}/download", summary="Download a generated report")
def download_report(report_id: int, session: DbSession, user: CurrentUser):
    record = session.get(Report, report_id)
    if record is None or record.user_id != user.id:
        # 404 rather than 403: do not confirm that another user's report exists.
        raise NotFoundError("Report not found.")
    path = report_service.resolve_existing(record.filename)
    return FileResponse(
        path,
        media_type=MEDIA_TYPES.get(record.file_format, "application/octet-stream"),
        filename=record.filename,
    )
