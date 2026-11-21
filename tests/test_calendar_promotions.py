from __future__ import annotations

import time

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from rdf.calendar_events import (
    build_known_future_covariates,
    get_events_for_window,
    load_calendar_events,
)


def test_calendar_events_reference_loaded():
    events = load_calendar_events()
    assert len(events) >= 160
    window = get_events_for_window("2016-04-25", "2016-05-22")
    names = {e["event_name_1"] for e in window["calendar_events"]}
    assert "Pesach End" in names
    assert "Mother's day" in names


def test_build_known_future_covariates_alignment():
    hist_dates = pd.date_range("2016-04-01", "2016-04-24", freq="D")
    fut_dates = pd.date_range("2016-04-25", "2016-05-22", freq="D")
    hist_cov, fut_cov, _ = build_known_future_covariates(hist_dates, fut_dates)
    assert len(hist_cov) == len(hist_dates)
    assert len(fut_cov) == len(fut_dates)
    assert set(hist_cov.columns) == set(fut_cov.columns)
    assert fut_cov["is_event"].sum() >= 3


def test_promotions_crud_api(client: TestClient):
    res = client.post(
        "/api/promotions",
        json={
            "name": "Test Spring Promo",
            "start_date": "2016-04-28",
            "end_date": "2016-05-02",
            "series_id": "FOODS_2_019 | California - CA_1",
            "uplift_pct": 15.0,
            "notes": "Stage 2 API test",
        },
    )
    assert res.status_code == 200
    promo = res.json()
    pid = promo["id"]
    try:
        listed = client.get("/api/promotions").json()
        assert any(p["id"] == pid for p in listed)

        ev = client.get(
            "/api/calendar/events",
            params={
                "start_date": "2016-04-25",
                "end_date": "2016-05-22",
                "series_id": "FOODS_2_019 | California - CA_1",
            },
        )
        assert ev.status_code == 200
        assert any(p["id"] == pid for p in ev.json()["promotions"])
    finally:
        del_res = client.delete(f"/api/promotions/{pid}")
        assert del_res.status_code == 200


@pytest.mark.slow
def test_chronos_forecast_with_calendar_covariates(client: TestClient):
    t0 = time.perf_counter()
    sid = "FOODS_2_019 | California - CA_1"
    resp = client.post(
        "/api/forecast",
        json={
            "series_id": sid,
            "horizon": 28,
            "model_type": "chronos",
            "use_calendar_covariates": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["use_calendar_covariates"] is True
    assert len(data["events_in_horizon"]["calendar_events"]) >= 3
    assert len(data["median"]) == 28
    print(f"[slow] Stage 2 Chronos-2 + Calendar Covariates took {time.perf_counter() - t0:.2f}s")
