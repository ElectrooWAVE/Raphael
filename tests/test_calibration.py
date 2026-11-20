from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from rdf.calibration import (
    apply_interval_calibration,
    calibrate_series_validation,
    fit_interval_scale,
    get_series_calibration,
)
from server.main import app


def test_fit_interval_scale_reaches_target_coverage():
    rng = np.random.default_rng(42)
    median = np.full(200, 50.0)
    actual = median + rng.normal(0.0, 10.0, size=200)
    # Deliberately narrow raw 80% band (~38% coverage)
    q10 = median - 5.0
    q90 = median + 5.0

    raw_cov = float(np.mean((actual >= q10) & (actual <= q90)))
    assert raw_cov < 0.70

    k = fit_interval_scale(actual, median, q10, q90, target_cov=0.80)
    assert k > 1.0
    cal_q10, cal_q90 = apply_interval_calibration(median, q10, q90, k)
    cal_cov = float(
        np.mean((actual >= np.asarray(cal_q10)) & (actual <= np.asarray(cal_q90)))
    )
    assert cal_cov >= 0.80


def test_apply_interval_calibration_clips_at_zero():
    cal_q10, cal_q90 = apply_interval_calibration([2.0, 5.0], [1.0, 3.0], [4.0, 8.0], scale_k=3.5)
    assert cal_q10[0] == 0.0
    assert cal_q10[1] == 0.0
    assert cal_q90[0] >= 2.0
    assert cal_q90[1] >= 5.0


def test_calibration_excludes_test_window(tmp_path, monkeypatch):
    import rdf.calibration as cal_mod
    import rdf.db as db_mod

    test_db = tmp_path / "test_cal.db"
    monkeypatch.setattr(db_mod, "DB_PATH", test_db)
    monkeypatch.setattr(cal_mod, "get_db", db_mod.get_db)
    monkeypatch.setattr(cal_mod, "init_db", db_mod.init_db)

    dates = pd.date_range("2025-01-01", periods=180, freq="D")
    sales = [10.0 + (i % 7) for i in range(180)]
    # Inject extreme values strictly inside the final 28-day test window
    for i in range(180 - 28, 180):
        sales[i] = 9999.0

    df = pd.DataFrame({"date": dates, "sales": sales})
    res = calibrate_series_validation(
        df,
        series_id="TEST_SERIES_EXCL_WINDOW",
        model_type="baseline",
        dataset_id="test-ds",
        horizon=28,
        num_cutoffs=2,
    )
    assert res["calibrated"] is True
    assert res["mae"] < 10.0
    stored = get_series_calibration("TEST_SERIES_EXCL_WINDOW", "baseline", "test-ds")
    assert stored is not None
    assert stored["scale_k"] == res["scale_k"]


@pytest.mark.slow
def test_chronos_calibration_and_api_exposure():
    with TestClient(app) as client:
        series_res = client.get("/api/series")
        assert series_res.status_code == 200
        payload = series_res.json()
        series_list = payload if isinstance(payload, list) else payload.get("series", [])
        assert len(series_list) > 0
        series_id = series_list[0] if isinstance(series_list[0], str) else series_list[0]["series_id"]

        cal_res = client.post(
            "/api/calibration/run",
            json={"series_id": series_id, "model_type": "chronos", "horizon": 28},
        )
        assert cal_res.status_code == 200
        cal = cal_res.json()
        assert cal["calibrated"] is True
        assert cal["scale_k"] > 0
        assert 0.0 <= cal["raw_coverage_80"] <= 1.0
        assert 0.0 <= cal["calibrated_coverage_80"] <= 1.0

        fc_res = client.post(
            "/api/forecast",
            json={"series_id": series_id, "horizon": 28, "model_type": "chronos"},
        )
        assert fc_res.status_code == 200
        fc = fc_res.json()
        assert "expected" in fc and len(fc["expected"]) == 28
        assert "q10" in fc and "q90" in fc
        assert fc["calibration"]["calibrated"] is True
