from __future__ import annotations

import io

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from rdf.reporting import export_inventory_excel


def test_export_inventory_excel_workbook():
    xlsx_bytes = export_inventory_excel("retail-demand-m5")
    assert len(xlsx_bytes) > 1000
    wb = load_workbook(io.BytesIO(xlsx_bytes))
    assert "Summary" in wb.sheetnames
    assert "Reorder Plan" in wb.sheetnames
    ws_plan = wb["Reorder Plan"]
    # 1 header row + 75 SKU-store rows
    assert ws_plan.max_row == 76


def test_reporting_and_automation_endpoints(client: TestClient):
    xlsx_resp = client.get("/api/reports/inventory.xlsx")
    assert xlsx_resp.status_code == 200
    assert "spreadsheetml" in xlsx_resp.headers["content-type"]

    # Create, run (export_report), and delete an automation schedule
    create_resp = client.post(
        "/api/automation/schedules",
        json={
            "name": "Test Snapshot Export",
            "job_type": "export_report",
            "cron_expr": "0 6 * * *",
        },
    )
    assert create_resp.status_code == 200
    sid = create_resp.json()["id"]
    try:
        run_resp = client.post(f"/api/automation/schedules/{sid}/run")
        assert run_resp.status_code == 200
        assert run_resp.json()["status"] == "completed"

        listed = client.get("/api/automation/schedules").json()
        assert any(s["id"] == sid for s in listed["schedules"])
    finally:
        del_resp = client.delete(f"/api/automation/schedules/{sid}")
        assert del_resp.status_code == 200
