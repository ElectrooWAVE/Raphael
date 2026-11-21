"""API tests for dataset upload, validation, versioning, deletion, and health endpoint."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rdf.config import DATA_DIR, PROCESSED_DIR
from server.main import app


def test_health_endpoint_matches_overview(client: TestClient):
    h_resp = client.get("/api/health")
    o_resp = client.get("/api/overview")
    assert h_resp.status_code == 200 and o_resp.status_code == 200
    health = h_resp.json()
    overview = o_resp.json()
    assert health["chronos_device"] == overview["chronos_device"]
    assert health["custom_device"] == overview["custom_device"] == "CPU"
    assert health["device_label"] == overview["device_label"] == overview["device"]


def test_upload_demand_history_csv_and_versioning(client: TestClient):
    csv_path = DATA_DIR / "demand_history.csv"
    ds_name = f"Upload Test {uuid.uuid4().hex[:8]}"
    dataset_id = None

    try:
        with csv_path.open("rb") as f:
            insp = client.post("/api/datasets/inspect", files={"file": ("demand_history.csv", f, "text/csv")})
        assert insp.status_code == 200
        meta = insp.json()
        assert meta["suggested_time_col"] == "date"
        assert meta["suggested_target_col"] == "quantity"
        assert "material" in meta["suggested_series_cols"]
        assert "area" in meta["suggested_series_cols"]
        assert meta["num_rows"] == 143475
        assert len(meta["sample_preview"]) == 10

        cov_payload = json.dumps([{"name": "is_promotion", "role": "past-only"}])
        with csv_path.open("rb") as f:
            val_resp = client.post(
                "/api/datasets/validate",
                files={"file": ("demand_history.csv", f, "text/csv")},
                data={
                    "time_col": "date",
                    "target_col": "quantity",
                    "series_cols": "material,area",
                    "covariates": cov_payload,
                    "frequency": "D",
                },
            )
        assert val_resp.status_code == 200
        val = val_resp.json()
        assert val["valid"] is True
        assert val["num_records"] == 143475
        assert val["num_series"] == 75
        assert val["date_start"] == "2011-01-29"
        assert val["date_end"] == "2016-04-24"
        assert val["duplicate_count"] == 0

        with csv_path.open("rb") as f:
            imp1 = client.post(
                "/api/datasets/import",
                files={"file": ("demand_history.csv", f, "text/csv")},
                data={
                    "dataset_name": ds_name,
                    "time_col": "date",
                    "target_col": "quantity",
                    "series_cols": "material,area",
                    "covariates": cov_payload,
                    "frequency": "D",
                },
            )
        assert imp1.status_code == 200
        res1 = imp1.json()
        dataset_id = res1["dataset_id"]
        assert res1["version_num"] == 1
        assert res1["quality_report"]["num_records"] == 143475
        assert res1["quality_report"]["num_series"] == 75
        v1_parquet = Path(res1["processed_file_path"])
        assert v1_parquet.exists()

        with csv_path.open("rb") as f:
            imp2 = client.post(
                "/api/datasets/import",
                files={"file": ("demand_history.csv", f, "text/csv")},
                data={
                    "dataset_name": ds_name,
                    "time_col": "date",
                    "target_col": "quantity",
                    "series_cols": "material,area",
                    "covariates": cov_payload,
                    "frequency": "D",
                },
            )
        assert imp2.status_code == 200
        res2 = imp2.json()
        assert res2["dataset_id"] == dataset_id
        assert res2["version_num"] == 2
        assert v1_parquet.exists()
        assert Path(res2["processed_file_path"]).exists()
        assert Path(res2["processed_file_path"]) != v1_parquet
    finally:
        if dataset_id:
            del_resp = client.delete(f"/api/datasets/{dataset_id}")
            assert del_resp.status_code == 200
            assert client.get(f"/api/datasets/{dataset_id}").status_code == 404
            assert not (PROCESSED_DIR / dataset_id).exists()


def test_upload_bad_files_return_4xx(client: TestClient):
    # 1. Wrong extension
    bad_ext = client.post("/api/datasets/inspect", files={"file": ("notes.txt", b"a,b\n1,2\n", "text/plain")})
    assert bad_ext.status_code == 400

    # 2. Empty file
    empty_resp = client.post("/api/datasets/inspect", files={"file": ("empty.csv", b"", "text/csv")})
    assert empty_resp.status_code == 400

    # 3. Missing date column
    no_date = b"item,quantity\nA,10\nB,20\n"
    val_missing = client.post(
        "/api/datasets/validate",
        files={"file": ("no_date.csv", no_date, "text/csv")},
        data={"time_col": "date", "target_col": "quantity", "series_cols": "item", "frequency": "D"},
    )
    assert val_missing.status_code == 200
    assert val_missing.json()["valid"] is False
    imp_missing = client.post(
        "/api/datasets/import",
        files={"file": ("no_date.csv", no_date, "text/csv")},
        data={"dataset_name": "Bad Missing Date", "time_col": "date", "target_col": "quantity", "series_cols": "item"},
    )
    assert imp_missing.status_code == 400

    # 4. Duplicate (series, date) rows
    dup_csv = b"date,item,quantity\n2024-01-01,A,10\n2024-01-01,A,15\n2024-01-02,A,12\n"
    val_dup = client.post(
        "/api/datasets/validate",
        files={"file": ("dups.csv", dup_csv, "text/csv")},
        data={"time_col": "date", "target_col": "quantity", "series_cols": "item", "frequency": "D"},
    )
    assert val_dup.status_code == 200
    assert val_dup.json()["valid"] is False
    assert val_dup.json()["duplicate_count"] == 2
    imp_dup = client.post(
        "/api/datasets/import",
        files={"file": ("dups.csv", dup_csv, "text/csv")},
        data={"dataset_name": "Bad Dup Rows", "time_col": "date", "target_col": "quantity", "series_cols": "item"},
    )
    assert imp_dup.status_code == 400

    # 5. Oversized file
    prev_limit = getattr(app.state, "max_upload_bytes", None)
    app.state.max_upload_bytes = 64
    try:
        big_csv = b"date,quantity\n" + b"2024-01-01,10\n" * 10
        over_resp = client.post("/api/datasets/inspect", files={"file": ("big.csv", big_csv, "text/csv")})
        assert over_resp.status_code == 413
    finally:
        if prev_limit is None:
            delattr(app.state, "max_upload_bytes")
        else:
            app.state.max_upload_bytes = prev_limit
