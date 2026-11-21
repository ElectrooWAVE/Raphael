"""API tests for Forecasting History list, detail, delete, and re-run endpoints."""
from __future__ import annotations

import json
import math
import time

import pytest
from fastapi.testclient import TestClient

from rdf.config import MODEL_ID


def test_history_list_filter_sort_pagination(client: TestClient):
    sid_a = "FOODS_2_019 | California - CA_1"
    sid_b = "HOBBIES_1_048 | Texas - TX_1"

    r1 = client.post("/api/forecast", json={"series_id": sid_a, "horizon": 7, "model_type": "baseline"})
    r2 = client.post("/api/forecast", json={"series_id": sid_b, "horizon": 7, "model_type": "baseline"})
    assert r1.status_code == 200 and r2.status_code == 200
    id1, id2 = r1.json()["run_id"], r2.json()["run_id"]

    try:
        resp_newest = client.get(
            "/api/history/runs",
            params={"paginated": True, "sort": "newest", "model_type": "baseline", "limit": 2, "offset": 0},
        )
        assert resp_newest.status_code == 200
        page = resp_newest.json()
        assert page["total"] >= 2
        assert page["items"][0]["id"] == id2

        resp_series = client.get(
            "/api/history/runs",
            params={"paginated": True, "series_id": sid_a, "model_type": "baseline", "limit": 20, "offset": 0},
        )
        assert resp_series.status_code == 200
        s_items = resp_series.json()["items"]
        assert any(item["id"] == id1 for item in s_items)
        assert all(item["series_id"] == sid_a for item in s_items)

        bad_sort = client.get("/api/history/runs", params={"sort": "random"})
        assert bad_sort.status_code == 400
    finally:
        client.delete(f"/api/history/runs/{id1}")
        client.delete(f"/api/history/runs/{id2}")


def test_history_detail_delete_and_404(client: TestClient):
    sid = "FOODS_2_019 | California - CA_1"
    fc = client.post("/api/forecast", json={"series_id": sid, "horizon": 7, "model_type": "baseline"})
    assert fc.status_code == 200
    run_id = fc.json()["run_id"]

    detail_resp = client.get(f"/api/history/runs/{run_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    json.dumps(detail, allow_nan=False)

    assert detail["id"] == run_id
    assert detail["series_id"] == sid
    assert detail["engine_label"] == "Baseline (Seasonal-Naive)"
    assert detail["device"] == "cpu"
    assert len(detail["values"]) == 7
    assert "reproducibility" in detail
    assert detail["reproducibility"]["post_processing"] == "Clip negative values at 0"
    assert len(detail["history_tail"]["dates"]) > 0

    del_resp = client.delete(f"/api/history/runs/{run_id}")
    assert del_resp.status_code == 200
    assert del_resp.json() == {"deleted": True, "run_id": run_id}

    assert client.get(f"/api/history/runs/{run_id}").status_code == 404
    assert client.delete(f"/api/history/runs/{run_id}").status_code == 404


@pytest.mark.slow
def test_chronos2_run_inspect_and_rerun(client: TestClient):
    t0 = time.perf_counter()
    sid = "FOODS_3_080 | Texas - TX_1"
    created = client.post("/api/forecast", json={"series_id": sid, "horizon": 28, "model_type": "chronos"})
    assert created.status_code == 200
    fc = created.json()
    orig_id = fc["run_id"]
    rerun_id = None

    try:
        detail_resp = client.get(f"/api/history/runs/{orig_id}")
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        json.dumps(detail, allow_nan=False)

        assert detail["id"] == orig_id
        assert detail["model_type"] == "chronos"
        assert detail["engine_label"] == "Chronos-2"
        assert detail["model_id"] == MODEL_ID
        assert detail["device"] in ("cuda", "cpu")
        assert len(detail["values"]) == 28
        assert len(detail["history_tail"]["dates"]) > 0

        stored_med = [v["predicted_median"] for v in detail["values"]]
        assert all(math.isfinite(v) for v in stored_med)
        assert stored_med == pytest.approx(fc["median"], rel=1e-6)

        repro = detail["reproducibility"]
        assert repro["model_id"] == MODEL_ID
        assert repro["data_file"]
        assert repro["data_sha256"]
        assert len(repro["parameters"]["quantile_levels"]) == 19

        rerun_resp = client.post(f"/api/history/runs/{orig_id}/rerun")
        assert rerun_resp.status_code == 200
        rr = rerun_resp.json()
        rerun_id = rr["run_id"]
        assert rerun_id != orig_id
        assert rr["rerun_of"] == orig_id
        assert len(rr["dates"]) == 28

        assert client.get(f"/api/history/runs/{orig_id}").status_code == 200
        assert client.get(f"/api/history/runs/{rerun_id}").status_code == 200
    finally:
        client.delete(f"/api/history/runs/{orig_id}")
        if rerun_id:
            client.delete(f"/api/history/runs/{rerun_id}")
        print(f"[slow] Stage History Inspect & Re-run (Chronos-2) took {time.perf_counter() - t0:.2f}s")
