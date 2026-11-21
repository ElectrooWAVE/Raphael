"""Excel (.xlsx) and PDF (.pdf) replenishment report generators (Stage 4)."""
from __future__ import annotations

import io
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font

from .db import now_iso
from .inventory import get_inventory_dashboard


def export_inventory_excel(dataset_id: str = "retail-demand-m5") -> bytes:
    """Generate a multi-sheet Excel replenishment report from stored inventory & forecasts."""
    data = get_inventory_dashboard(dataset_id=dataset_id)
    wb = Workbook()

    # Sheet 1: Summary
    ws_sum = wb.active
    ws_sum.title = "Summary"
    ws_sum.append(["Retail Demand Forecasting - Inventory & Reorder Report"])
    ws_sum["A1"].font = Font(bold=True, size=13)
    ws_sum.append(["Notice", "Simulated inventory (demo data) - Units only (no cost/price columns)"])
    ws_sum.append(["Generated At", now_iso()])
    ws_sum.append(["Dataset", dataset_id])
    ws_sum.append(["Snapshot Date", data.get("snapshot_date", "2016-04-24")])
    ws_sum.append(["Forecast Start", data.get("forecast_start", "2016-04-25")])
    ws_sum.append([])

    summary = data.get("summary", {})
    ws_sum.append(["Status", "SKU-Store Count"])
    for k in ("total", "critical", "low", "healthy", "excess", "needs_forecast"):
        ws_sum.append([k.upper(), summary.get(k, 0)])

    ws_sum.append([])
    ws_sum.append(["Engine Status \\ Simulated Label (File)", "critical", "low", "medium", "healthy"])
    matrix = data.get("agreement_matrix", {})
    for eng in ("CRITICAL", "LOW", "HEALTHY", "EXCESS"):
        row = matrix.get(eng, {})
        ws_sum.append([eng, row.get("critical", 0), row.get("low", 0), row.get("medium", 0), row.get("healthy", 0)])

    # Sheet 2: Reorder Plan
    ws_plan = wb.create_sheet("Reorder Plan")
    headers = [
        "Series ID", "Material", "Area", "Status", "Simulated Label (file)",
        "On-Hand (u)", "In-Transit (u)", "Inventory Position (u)",
        "L mean (d)", "L std (d)", "Orders", "Low Confidence LT",
        "Typical Order Qty (info)", "Avg Daily Demand (u/d)", "Safety Stock (u)",
        "ROP (u)", "Order-up-to S (u)", "R (d)", "Pack Size", "MOQ",
        "Recommended Order Qty (u)", "Runway ETA (d)", "Stockout Date",
    ]
    ws_plan.append(headers)
    for cell in ws_plan[1]:
        cell.font = Font(bold=True)

    for it in data.get("items", []):
        ws_plan.append([
            it.get("series_id"),
            it.get("material"),
            it.get("area"),
            it.get("status"),
            it.get("simulated_label"),
            it.get("on_hand"),
            it.get("in_transit"),
            it.get("inventory_position"),
            it.get("L_mean"),
            it.get("L_std"),
            it.get("order_count"),
            bool(it.get("low_confidence_lt")),
            it.get("median_order_qty"),
            it.get("avg_daily_demand"),
            it.get("safety_stock"),
            it.get("rop"),
            it.get("order_up_to_S"),
            it.get("review_period"),
            it.get("pack_size"),
            it.get("moq"),
            it.get("order_qty"),
            it.get("eta_expected_days"),
            it.get("stockout_date"),
        ])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_inventory_pdf(dataset_id: str = "retail-demand-m5") -> bytes:
    """Generate a PDF executive replenishment report using reportlab."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as e:
        raise RuntimeError(
            "reportlab is not installed. Run: .venv\\Scripts\\pip.exe install reportlab"
        ) from e

    data = get_inventory_dashboard(dataset_id=dataset_id)
    summary = data.get("summary", {})
    items = data.get("items", [])

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter), title="Inventory & Reorder Report")
    styles = getSampleStyleSheet()
    story: list[Any] = [
        Paragraph("Retail Demand Forecasting - Inventory & Reorder Report", styles["Title"]),
        Paragraph(
            f"Simulated inventory (demo data) | Units only | Dataset: {dataset_id} | Generated: {now_iso()}",
            styles["Normal"],
        ),
        Spacer(1, 10),
        Paragraph(
            f"Summary: Total={summary.get('total', 0)} | CRITICAL={summary.get('critical', 0)} | "
            f"LOW={summary.get('low', 0)} | HEALTHY={summary.get('healthy', 0)} | EXCESS={summary.get('excess', 0)}",
            styles["Heading3"],
        ),
        Spacer(1, 10),
    ]

    priority = [it for it in items if it.get("status") in ("CRITICAL", "LOW")] or items[:25]
    table_data = [[
        "Material", "Area", "Status", "On-Hand", "In-Transit", "L mean", "ROP", "S", "Order Qty", "ETA (d)"
    ]]
    for it in priority[:35]:
        table_data.append([
            it.get("material", ""),
            it.get("area", ""),
            it.get("status", ""),
            str(it.get("on_hand", "-")),
            str(it.get("in_transit", "-")),
            str(it.get("L_mean", "-")),
            str(it.get("rop", "-")),
            str(it.get("order_up_to_S", "-")),
            str(it.get("order_qty", "-")),
            str(it.get("eta_expected_days", "-")),
        ])

    tbl = Table(table_data, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
    ]))
    story.append(tbl)
    doc.build(story)
    return buf.getvalue()
