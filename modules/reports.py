"""
Report generation utilities (CSV/Excel/PDF).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas


EXPORTS_DIR = Path(__file__).resolve().parent.parent / "exports"


def ensure_exports_dir() -> None:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


def to_dataframe(lines: List[Dict[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(lines)


def export_csv(df: pd.DataFrame, filename: str) -> Path:
    ensure_exports_dir()
    path = EXPORTS_DIR / filename
    df.to_csv(path, index=False)
    return path


def export_excel(detailed: pd.DataFrame, summary: pd.DataFrame, warnings: pd.DataFrame, filename: str) -> Path:
    ensure_exports_dir()
    path = EXPORTS_DIR / filename
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        detailed.to_excel(writer, sheet_name="Detailed", index=False)
        summary.to_excel(writer, sheet_name="Summary", index=False)
        warnings.to_excel(writer, sheet_name="Warnings", index=False)
    return path


def export_excel_single(df: pd.DataFrame, filename: str, sheet_name: str = "Sheet1") -> Path:
    ensure_exports_dir()
    path = EXPORTS_DIR / filename
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    return path


def export_excel_with_metadata(
    detailed: pd.DataFrame,
    summary: Optional[pd.DataFrame],
    warnings: Optional[pd.DataFrame],
    metadata: Dict[str, str],
    filename: str,
) -> Path:
    ensure_exports_dir()
    path = EXPORTS_DIR / filename
    meta_df = pd.DataFrame(list(metadata.items()), columns=["Field", "Value"])
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        meta_df.to_excel(writer, sheet_name="Metadata", index=False)
        detailed.to_excel(writer, sheet_name="Detailed", index=False)
        if summary is not None and not summary.empty:
            summary.to_excel(writer, sheet_name="Summary", index=False)
        if warnings is not None and not warnings.empty:
            warnings.to_excel(writer, sheet_name="Warnings", index=False)
    return path


def _compute_col_widths(df: pd.DataFrame, width: float, weights: Optional[Dict[str, float]] = None) -> List[float]:
    col_names = list(df.columns)
    if not col_names:
        return []
    max_lens = []
    sample = df.head(50)
    for col in col_names:
        max_len = len(str(col))
        for v in sample[col].tolist():
            max_len = max(max_len, len(str(v)) if v is not None else 0)
        weight = 1.0
        if weights and col in weights:
            weight = max(0.2, weights[col])
        max_lens.append(max_len * weight)
    total = sum(max_lens) or 1
    raw = [width * (l / total) for l in max_lens]
    min_w = width * 0.03
    max_w = width * 0.25
    clamped = [min(max(r, min_w), max_w) for r in raw]
    scale = width / sum(clamped)
    return [w * scale for w in clamped]


def _draw_footer(c: canvas.Canvas, page_width: float, footer_left: str) -> None:
    y = 0.35 * inch
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(0.5 * inch, y, footer_left)
    c.drawRightString(page_width - 0.5 * inch, y, f"Page {c.getPageNumber()}")


def _draw_table(
    c: canvas.Canvas,
    df: pd.DataFrame,
    x: float,
    y: float,
    width: float,
    min_y: float,
    page_height: float,
    footer_text: str,
    column_weights: Optional[Dict[str, float]] = None,
    right_align: Optional[List[str]] = None,
    max_chars: Optional[Dict[str, int]] = None,
) -> float:
    if df.empty:
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(x, y, "No data available.")
        return y - 0.25 * inch

    col_names = list(df.columns)
    col_widths = _compute_col_widths(df, width, column_weights)
    row_height = 0.22 * inch

    right_align = set(right_align or [])
    max_chars = max_chars or {}

    def draw_row(values, y_pos):
        c.setFont("Helvetica", 8.5)
        x_pos = x
        for idx, v in enumerate(values):
            col_name = col_names[idx]
            text = str(v) if v is not None else ""
            limit = max_chars.get(col_name, 30)
            if len(text) > limit:
                text = text[: max(0, limit - 1)] + "…"
            if col_name in right_align:
                c.drawRightString(x_pos + col_widths[idx] - 2, y_pos, text)
            else:
                c.drawString(x_pos, y_pos, text)
            x_pos += col_widths[idx]

    def draw_header(y_pos):
        c.setFillGray(0.9)
        c.rect(x, y_pos - 0.02 * inch, width, row_height, fill=1, stroke=0)
        c.setFillGray(0)
        c.setFont("Helvetica-Bold", 8.5)
        draw_row(col_names, y_pos)
        c.line(x, y_pos - 0.04 * inch, x + width, y_pos - 0.04 * inch)
        x_pos = x
        top = y_pos + row_height - 0.02 * inch
        bottom = y_pos - 0.04 * inch
        for w in col_widths[:-1]:
            x_pos += w
            c.line(x_pos, bottom, x_pos, top)

    draw_header(y)
    y -= row_height

    row_index = 0
    for _, row in df.iterrows():
        if row_index % 2 == 1:
            c.setFillGray(0.97)
            c.rect(x, y - 0.02 * inch, width, row_height, fill=1, stroke=0)
            c.setFillGray(0)
        draw_row(row.tolist(), y)
        y -= row_height
        if y < min_y:
            _draw_footer(c, page_height, footer_text)
            c.showPage()
            y = page_height - 0.5 * inch
            draw_header(y)
            y -= row_height
        row_index += 1
    return y


def export_pdf_report(
    report_title: str,
    detailed: pd.DataFrame,
    summary: pd.DataFrame,
    warnings: pd.DataFrame,
    metadata: Dict[str, str],
    kpis: Dict[str, str],
    filename: str,
) -> Path:
    ensure_exports_dir()
    path = EXPORTS_DIR / filename
    c = canvas.Canvas(str(path), pagesize=landscape(A4))
    width, height = landscape(A4)
    x = 0.5 * inch
    y = height - 0.5 * inch

    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, report_title)
    y -= 0.35 * inch

    c.setFont("Helvetica", 9.5)
    for key, value in metadata.items():
        c.drawString(x, y, f"{key}: {value}")
        y -= 0.2 * inch

    y -= 0.1 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, "KPIs")
    y -= 0.25 * inch
    c.setFont("Helvetica", 9.5)
    for key, value in kpis.items():
        c.drawString(x, y, f"{key}: {value}")
        y -= 0.2 * inch

    y -= 0.1 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, "Warnings")
    y -= 0.25 * inch
    c.setFont("Helvetica", 8.5)
    if warnings.empty:
        c.drawString(x, y, "No warnings.")
        y -= 0.25 * inch
    else:
        warnings_weights = {"trade_name": 1.8, "scientific_name": 1.6, "gtin": 1.2, "notes": 1.4}
        warnings_right = ["gtin", "expiry_date", "on_hand_count", "price"]
        warnings_trunc = {"trade_name": 36, "scientific_name": 30, "notes": 40}
        y = _draw_table(
            c,
            warnings,
            x,
            y,
            width - inch,
            0.5 * inch,
            height,
            report_title,
            warnings_weights,
            warnings_right,
            warnings_trunc,
        )

    _draw_footer(c, width, f"{report_title} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    c.showPage()
    x = 0.5 * inch
    y = height - 0.5 * inch
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, "Detailed Report")
    y -= 0.3 * inch
    detailed_weights = {
        "trade_name": 1.8,
        "scientific_name": 1.6,
        "gtin": 1.1,
        "batch_lot": 1.1,
        "expiry_date": 1.1,
        "notes": 1.6,
    }
    detailed_right = ["gtin", "expiry_date", "scan_timestamp", "on_hand_count", "price"]
    detailed_trunc = {"trade_name": 36, "scientific_name": 30, "notes": 40}
    _draw_table(
        c,
        detailed,
        x,
        y,
        width - inch,
        0.5 * inch,
        height,
        report_title,
        detailed_weights,
        detailed_right,
        detailed_trunc,
    )
    _draw_footer(c, width, f"{report_title} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    c.showPage()
    x = 0.5 * inch
    y = height - 0.5 * inch
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, "Summary Report")
    y -= 0.3 * inch
    summary_weights = {
        "trade_name": 1.8,
        "scientific_name": 1.6,
        "gtin": 1.1,
        "batch_lot": 1.1,
        "expiry_date": 1.1,
        "notes": 1.6,
    }
    summary_right = ["gtin", "expiry_date", "total_count", "price"]
    summary_trunc = {"trade_name": 36, "scientific_name": 30, "notes": 40}
    _draw_table(
        c,
        summary,
        x,
        y,
        width - inch,
        0.5 * inch,
        height,
        report_title,
        summary_weights,
        summary_right,
        summary_trunc,
    )
    _draw_footer(c, width, f"{report_title} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    c.save()
    return path


def export_pdf(report_title: str, df: pd.DataFrame, filename: str) -> Path:
    ensure_exports_dir()
    path = EXPORTS_DIR / filename
    c = canvas.Canvas(str(path), pagesize=landscape(A4))
    width, height = landscape(A4)
    x = 0.5 * inch
    y = height - 0.5 * inch

    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, report_title)
    y -= 0.3 * inch
    _draw_table(c, df, x, y, width - inch, 0.5 * inch, height, report_title)
    _draw_footer(c, width, f"{report_title} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    c.save()
    return path
