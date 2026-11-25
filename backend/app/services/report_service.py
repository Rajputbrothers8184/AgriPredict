"""PDF and Excel export for financial records and forecasts.

Why generation happens on the server
------------------------------------
A React Native app that renders PDFs needs a native library per platform, embeds
fonts, and cannot easily be tested. Generating the file server-side means one
implementation, real unit tests, and a download link the app can hand to the
device's PDF/Excel viewer.

Design notes
------------
* **ReportLab** for PDF (pure Python, no system dependencies such as wkhtmltopdf).
* **OpenPyXL** for Excel, with real number formats so totals are usable in Excel
  rather than text.
* Urdu text is included where a font is available; ReportLab's built-in CID
  fonts are used for Urdu/Arabic shaping (``STSong-Light``-style fallback is not
  appropriate), so when ``REPORTS_URDU_FONT`` is not provided the report states
  the limitation in English instead of emitting broken glyphs. This is documented
  in the README limitations.
* Files are written to ``REPORT_STORAGE_DIR`` with a random name, and only
  metadata is stored in the database. The download endpoint streams the file and
  checks ownership, so a guessed filename leaks nothing.
"""

from __future__ import annotations

import logging
import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.models import CropCycle
from app.services.finance_service import as_decimal, summarise_cycle_orm

logger = logging.getLogger(__name__)

BRAND_COLOR = "#1F6F43"  # agricultural green


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _money(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"PKR {value:,.2f}"


def _safe_filename(prefix: str, suffix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stamp}-{secrets.token_hex(4)}.{suffix}"


def storage_path(filename: str) -> Path:
    return settings.report_dir / filename


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def _pdf_styles() -> dict[str, ParagraphStyle]:
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "AgriTitle",
            parent=styles["Title"],
            fontSize=18,
            textColor=colors.HexColor(BRAND_COLOR),
            spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "AgriSubtitle", parent=styles["Normal"], fontSize=9, textColor=colors.grey
        ),
        "h2": ParagraphStyle(
            "AgriH2",
            parent=styles["Heading2"],
            fontSize=12,
            textColor=colors.HexColor(BRAND_COLOR),
            spaceBefore=10,
            spaceAfter=4,
        ),
        "body": ParagraphStyle("AgriBody", parent=styles["Normal"], fontSize=9, leading=12),
        "small": ParagraphStyle(
            "AgriSmall", parent=styles["Normal"], fontSize=7, textColor=colors.grey
        ),
    }


def _table(rows: list[list[str]], *, widths: list[float] | None = None) -> Table:
    table = Table(rows, colWidths=widths, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BRAND_COLOR)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F7F5")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def build_financial_pdf(
    *, user_name: str, cycles: list[CropCycle], generated_at: datetime | None = None
) -> tuple[BytesIO, str]:
    """Render a financial statement PDF; returns ``(buffer, filename)``."""
    generated_at = generated_at or datetime.now(timezone.utc)
    styles = _pdf_styles()
    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="AgriPredict Financial Statement",
        author="AgriPredict",
    )
    story: list = [
        Paragraph("AgriPredict — Financial Statement", styles["title"]),
        Paragraph(
            f"Prepared for {user_name} · generated {generated_at:%d %b %Y, %H:%M} UTC · "
            "all amounts in PKR, prices per 40 kg (maund)",
            styles["subtitle"],
        ),
        Spacer(1, 6),
    ]

    totals = {"revenue": Decimal("0"), "cost": Decimal("0"), "profit": Decimal("0")}
    per_cycle: list[list[str]] = [["Crop", "Season", "Area (acre)", "Revenue", "Cost", "Profit", "Margin"]]

    for cycle in cycles:
        summary = summarise_cycle_orm(cycle)
        totals["revenue"] += as_decimal(summary.revenue_pkr)
        totals["cost"] += as_decimal(summary.cost_pkr)
        totals["profit"] += as_decimal(summary.profit_pkr)
        per_cycle.append(
            [
                f"{cycle.commodity.name_en} ({cycle.farm.name})",
                f"{cycle.season} {cycle.sowing_date.year}",
                f"{as_decimal(cycle.area_acres):,.2f}",
                _money(summary.revenue_pkr),
                _money(summary.cost_pkr),
                _money(summary.profit_pkr),
                f"{summary.margin_pct}%" if summary.margin_pct is not None else "—",
            ]
        )

    per_cycle.append(
        [
            "TOTAL",
            "",
            "",
            _money(totals["revenue"]),
            _money(totals["cost"]),
            _money(totals["profit"]),
            "",
        ]
    )

    story.append(Paragraph("Crop cycle summary", styles["h2"]))
    story.append(_table(per_cycle, widths=[110, 62, 48, 70, 70, 70, 40]))

    if not cycles:
        story.append(
            Paragraph(
                "No crop cycles were recorded for this account, so there is nothing to "
                "total yet.",
                styles["body"],
            )
        )

    # Expense detail per cycle
    story.append(Paragraph("Expense detail", styles["h2"]))
    expense_rows: list[list[str]] = [["Date", "Crop", "Category", "Amount", "Description"]]
    for cycle in cycles:
        for expense in sorted(cycle.expenses, key=lambda e: e.expense_date):
            expense_rows.append(
                [
                    expense.expense_date.isoformat(),
                    cycle.commodity.name_en,
                    expense.category,
                    _money(as_decimal(expense.amount_pkr)),
                    (expense.description or "")[:60],
                ]
            )
    if len(expense_rows) == 1:
        expense_rows.append(["—", "—", "—", "—", "No expenses recorded"])
    story.append(_table(expense_rows, widths=[55, 70, 60, 70, 165]))

    # Sales detail
    story.append(Paragraph("Sales detail", styles["h2"]))
    sales_rows: list[list[str]] = [
        ["Date", "Crop", "Qty (kg)", "Price/maund", "Total", "Buyer"]
    ]
    for cycle in cycles:
        for sale in sorted(cycle.sales, key=lambda s: s.sale_date):
            sales_rows.append(
                [
                    sale.sale_date.isoformat(),
                    cycle.commodity.name_en,
                    f"{as_decimal(sale.quantity_kg):,.0f}",
                    _money(as_decimal(sale.unit_price_pkr)),
                    _money(as_decimal(sale.total_amount_pkr)),
                    (sale.buyer_name or "—")[:24],
                ]
            )
    if len(sales_rows) == 1:
        sales_rows.append(["—", "—", "—", "—", "—", "No sales recorded"])
    story.append(_table(sales_rows, widths=[55, 70, 55, 70, 70, 95]))

    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "Generated by AgriPredict from records entered by the user. Figures are "
            "derived, not audited; forecasts and market reference data are excluded "
            "from profit and loss.",
            styles["small"],
        )
    )

    document.build(story)
    buffer.seek(0)
    return buffer, _safe_filename("agripredict-financial", "pdf")


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------
HEADER_FILL = PatternFill("solid", fgColor="1F6F43")
HEADER_FONT = Font(color="FFFFFF", bold=True)
MONEY_FORMAT = '#,##0.00'


def _write_sheet(workbook: openpyxl.Workbook, title: str, headers: list[str], rows: list[list]) -> None:
    sheet = workbook.create_sheet(title=title)
    sheet.append(headers)
    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for row in rows:
        sheet.append(row)

    # Column widths from content, capped so a long description cannot push the
    # numeric columns off the screen.
    for index, header in enumerate(headers, start=1):
        longest = max(
            [len(str(header))] + [len(str(row[index - 1])) for row in rows if len(row) >= index]
        )
        sheet.column_dimensions[get_column_letter(index)].width = min(max(longest + 2, 10), 46)

    # Money formats: apply per column by header name so the mapping is explicit.
    money_columns = [
        i
        for i, header in enumerate(headers, start=1)
        if any(token in header.lower() for token in ("pkr", "amount", "revenue", "cost", "profit", "price"))
    ]
    for column in money_columns:
        for cell in sheet.iter_cols(min_col=column, max_col=column, min_row=2):
            for value_cell in cell:
                value_cell.number_format = MONEY_FORMAT

    sheet.freeze_panes = "A2"


def build_financial_workbook(
    *, user_name: str, cycles: list[CropCycle], generated_at: datetime | None = None
) -> tuple[BytesIO, str]:
    """Build a multi-sheet Excel workbook; returns ``(buffer, filename)``."""
    generated_at = generated_at or datetime.now(timezone.utc)
    workbook = openpyxl.Workbook()

    overview = workbook.active
    overview.title = "Overview"
    overview["A1"] = "AgriPredict — Financial Workbook"
    overview["A1"].font = Font(size=14, bold=True, color="1F6F43")
    overview["A2"] = f"Prepared for {user_name}"
    overview["A3"] = f"Generated {generated_at:%Y-%m-%d %H:%M} UTC"
    overview["A4"] = "Amounts in PKR; prices per 40 kg (maund); quantities in kg"

    cycle_rows: list[list] = []
    expense_rows: list[list] = []
    sales_rows: list[list] = []

    total_revenue = total_cost = Decimal("0")
    for cycle in cycles:
        summary = summarise_cycle_orm(cycle)
        total_revenue += as_decimal(summary.revenue_pkr)
        total_cost += as_decimal(summary.cost_pkr)
        cycle_rows.append(
            [
                cycle.farm.name,
                cycle.commodity.name_en,
                cycle.season,
                cycle.sowing_date.year,
                float(as_decimal(cycle.area_acres)),
                float(as_decimal(summary.revenue_pkr)),
                float(as_decimal(summary.cost_pkr)),
                float(as_decimal(summary.profit_pkr)),
                float(summary.margin_pct) if summary.margin_pct is not None else None,
                float(as_decimal(summary.break_even_price_pkr))
                if summary.break_even_price_pkr is not None
                else None,
                cycle.status,
            ]
        )
        for expense in sorted(cycle.expenses, key=lambda e: e.expense_date):
            expense_rows.append(
                [
                    expense.expense_date.isoformat(),
                    cycle.commodity.name_en,
                    cycle.farm.name,
                    expense.category,
                    float(as_decimal(expense.amount_pkr)),
                    expense.description or "",
                ]
            )
        for sale in sorted(cycle.sales, key=lambda s: s.sale_date):
            sales_rows.append(
                [
                    sale.sale_date.isoformat(),
                    cycle.commodity.name_en,
                    cycle.farm.name,
                    (sale.market.name if sale.market else ""),
                    float(as_decimal(sale.quantity_kg)),
                    float(as_decimal(sale.unit_price_pkr)),
                    float(as_decimal(sale.total_amount_pkr)),
                    sale.buyer_name or "",
                ]
            )

    total_profit = total_revenue - total_cost
    overview["A6"] = "Total revenue (PKR)"
    overview["B6"] = float(total_revenue)
    overview["A7"] = "Total cost (PKR)"
    overview["B7"] = float(total_cost)
    overview["A8"] = "Profit (PKR)"
    overview["B8"] = float(total_profit)
    overview["A9"] = "Margin (%)"
    overview["B9"] = (
        round(float(total_profit / total_revenue * 100), 1) if total_revenue > 0 else None
    )
    overview["A10"] = "Crop cycles"
    overview["B10"] = len(cycles)
    for cell in ("B6", "B7", "B8"):
        overview[cell].number_format = MONEY_FORMAT

    _write_sheet(
        workbook,
        "Crop Cycles",
        [
            "Farm",
            "Crop",
            "Season",
            "Year",
            "Area (acre)",
            "Revenue (PKR)",
            "Cost (PKR)",
            "Profit (PKR)",
            "Margin (%)",
            "Break-even (PKR/maund)",
            "Status",
        ],
        cycle_rows,
    )
    _write_sheet(
        workbook,
        "Expenses",
        ["Date", "Crop", "Farm", "Category", "Amount (PKR)", "Description"],
        expense_rows,
    )
    _write_sheet(
        workbook,
        "Sales",
        [
            "Date",
            "Crop",
            "Farm",
            "Market",
            "Quantity (kg)",
            "Price (PKR/maund)",
            "Total (PKR)",
            "Buyer",
        ],
        sales_rows,
    )

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer, _safe_filename("agripredict-financial", "xlsx")


# ---------------------------------------------------------------------------
# Forecast report (PDF)
# ---------------------------------------------------------------------------
def build_forecast_pdf(
    *,
    commodity_name: str,
    market_name: str,
    model_name: str,
    issued_on: date,
    points: list[dict],
    mae: Decimal | None,
    rmse: Decimal | None,
    disclaimer: str | None = None,
) -> tuple[BytesIO, str]:
    styles = _pdf_styles()
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, title="AgriPredict Price Forecast")

    rows: list[list[str]] = [["Date", "Predicted (PKR/maund)", "Lower", "Upper"]]
    for point in points:
        rows.append(
            [
                str(point["target_date"]),
                _money(point.get("predicted_price_pkr")),
                _money(point.get("lower_bound_pkr")),
                _money(point.get("upper_bound_pkr")),
            ]
        )

    story: list = [
        Paragraph("AgriPredict — Price Forecast", styles["title"]),
        Paragraph(
            f"{commodity_name} at {market_name} · model: {model_name} · "
            f"issued {issued_on.isoformat()}",
            styles["subtitle"],
        ),
        Spacer(1, 8),
        Paragraph(
            f"Measured error on historical hold-out data: MAE {_money(mae)}, "
            f"RMSE {_money(rmse)}.",
            styles["body"],
        ),
        Spacer(1, 6),
        _table(rows, widths=[90, 110, 90, 90]),
        Spacer(1, 8),
        Paragraph(
            disclaimer
            or "Forecasts are estimates derived from historical prices. Actual market "
            "prices can differ substantially; use this as one input among several.",
            styles["small"],
        ),
    ]
    document.build(story)
    buffer.seek(0)
    return buffer, _safe_filename("agripredict-forecast", "pdf")


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def persist(buffer: BytesIO, filename: str) -> tuple[Path, int]:
    """Write a generated artefact to the report directory."""
    path = storage_path(filename)
    data = buffer.getvalue()
    path.write_bytes(data)
    return path, len(data)


def cleanup_expired(now: datetime | None = None) -> int:
    """Delete report files older than ``REPORT_TTL_MINUTES``; returns the count."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=settings.report_ttl_minutes)
    removed = 0
    directory = settings.report_dir
    for file in directory.glob("agripredict-*"):
        if not file.is_file():
            continue
        modified = datetime.fromtimestamp(file.stat().st_mtime, tz=timezone.utc)
        if modified < cutoff:
            try:
                file.unlink()
                removed += 1
            except OSError as exc:  # pragma: no cover - filesystem race
                logger.warning("Could not remove expired report %s: %s", file, exc)
    return removed


def resolve_existing(filename: str) -> Path:
    """Return the path for a stored report, rejecting traversal attempts."""
    candidate = (settings.report_dir / filename).resolve()
    base = settings.report_dir.resolve()
    if base not in candidate.parents and candidate != base:
        raise NotFoundError("Report not found.")
    if not candidate.is_file():
        raise NotFoundError("Report not found or has expired.")
    return candidate
