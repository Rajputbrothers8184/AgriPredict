"""Report generation and download endpoints (PDF / Excel)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps import CurrentUser, DbSession, bearer_scheme
from app.core.config import settings
from app.core.exceptions import AuthError, NotFoundError, ValidationError
from app.core.security import (
    create_report_download_token,
    decode_report_download_token,
    decode_token,
)
from app.database import get_db
from app.models import User
from app.models import Report
from app.schemas import ReportCreate, ReportRead
from app.services import crop_service, report_service

router = APIRouter(prefix="/reports", tags=["reports"])

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _as_utc(value: datetime | None) -> datetime | None:
    """Attach UTC to a naive datetime.

    SQLite does not persist timezone information, so a value read back from the
    database is naive even though it was written as UTC-aware. Comparing it with
    an aware ``datetime.now(timezone.utc)`` raises TypeError, so every timestamp
    crossing this boundary is normalised here. The alternative — storing naive
    UTC everywhere — spreads the assumption across the whole codebase.
    """
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _signed_download_url(user_id: int, report_id: int, expires_at: datetime | None) -> str:
    """Build a download URL the browser can use without an Authorization header.

    The token TTL is capped at the report's own expiry so the link can never
    outlive the file it points at.
    """
    ttl_minutes = settings.report_ttl_minutes
    expires_at = _as_utc(expires_at)
    if expires_at is not None:
        remaining = (expires_at - datetime.now(timezone.utc)).total_seconds() / 60
        ttl_minutes = max(1, min(ttl_minutes, int(remaining)))
    token = create_report_download_token(user_id, report_id, ttl_minutes)
    return f"{settings.api_v1_prefix}/reports/{report_id}/download?token={token}"


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
    result.download_url = _signed_download_url(user.id, record.id, record.expires_at)
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
        item.download_url = _signed_download_url(user.id, row.id, row.expires_at)
        results.append(item)
    return results


@router.get(
    "/{report_id}/download",
    summary="Download a generated report (bearer token or signed link)",
)
def download_report(
    report_id: int,
    session: DbSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
    token: str | None = Query(
        default=None,
        description=(
            "Signed short-lived download token. Use this when the URL is opened "
            "by a browser or download manager that cannot send an Authorization header."
        ),
    ),
):
    """Serve a generated PDF/XLSX.

    Two authentication paths, because the two callers differ:

    * an API client sends the normal bearer token;
    * a browser or Android download manager sends no headers at all, so it uses
      the signed ``?token=`` link issued in ``download_url``.

    Both resolve to the same ownership check: a report is only served to the
    user who generated it. A wrong or expired link is a 401, an existing report
    belonging to someone else is a 404 (never confirm another user's report).
    """
    user_id: int | None = None
    if credentials is not None and credentials.credentials:
        payload = decode_token(credentials.credentials, expected_type="access")
        user_id = int(payload["sub"])
    elif token:
        payload = decode_report_download_token(token)
        user_id = int(payload["sub"])
        if payload.get("report") != report_id:
            # A valid token for a different report must not unlock this one.
            raise AuthError(
                "This download link is not valid for the requested report.",
                code="invalid_download_token",
            )
    else:
        raise AuthError("Authentication credentials were not provided.")

    record = session.get(Report, report_id)
    if record is None or record.user_id != user_id:
        # 404 rather than 403: do not confirm that another user's report exists.
        raise NotFoundError("Report not found.")
    record_expires = _as_utc(record.expires_at)
    if record_expires is not None and record_expires < datetime.now(timezone.utc):
        raise NotFoundError("This report has expired. Please generate it again.")

    path = report_service.resolve_existing(record.filename)
    return FileResponse(
        path,
        media_type=MEDIA_TYPES.get(record.file_format, "application/octet-stream"),
        filename=record.filename,
    )
