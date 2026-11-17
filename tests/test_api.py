"""API tests for server/main.py against the raw CSV and real Chronos-2 model."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rdf.config import DATA_DIR, MODEL_ID
from server.main import app

RAW = DATA_DIR / "demand_history.csv"


@pytest.fixture(scope="session")
def raw_df() -> pd.DataFrame:
    return pd.read_csv(RAW, parse_dates=["date"])


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def test_get_series_matches_raw_csv(client: TestClient, raw_df: pd.DataFrame):
    resp = client.get("/api/series")
    assert resp.status_code == 200
    got = resp.json()
    expected = sorted((raw_df["material"] + " | " + raw_df["area"]).unique().tolist())
    assert got == expected
    assert len(got) == 75


@pytest.mark.parametrize(
    "sid",
    [
        "FOODS_2_019 | Wisconsin - WI_1",
        "HOBBIES_1_048 | Texas - TX_1",
        "FOODS_3_080 | California - CA_1",
    ],
)
def test_get_history_matches_raw_csv(client: TestClient, raw_df: pd.DataFrame, sid: str):
    resp = client.get("/api/history", params={"series_id": sid})
    assert resp.status_code == 200
    data = resp.json()

    mat, area = sid.split(" | ")
    expect = raw_df[(raw_df.material == mat) & (raw_df.area == area)].sort_values("date")

    assert data["dates"] == [d.strftime("%Y-%m-%d") for d in expect["date"]]
    assert data["sales"] == [float(v) for v in expect["quantity"]]
    assert data["summary"]["days"] == len(expect)
    assert data["summary"]["zero_days"] == int((expect["quantity"] == 0).sum())
    assert data["summary"]["missing_days"] == 0


def test_history_error_responses(client: TestClient):
    assert client.get("/api/history", params={"series_id": "DOES_NOT_EXIST | XX_1"}).status_code == 404
    assert client.get("/api/history", params={"series_id": ""}).status_code == 400


def test_forecast_validation_and_unknown_series(client: TestClient):
    assert client.post("/api/forecast", json={"series_id": "DOES_NOT_EXIST | XX_1", "horizon": 28}).status_code == 404
    assert client.post("/api/forecast", json={"series_id": "FOODS_2_019 | Wisconsin - WI_1", "horizon": 3}).status_code == 400
    assert client.post("/api/forecast", json={"series_id": "FOODS_2_019 | Wisconsin - WI_1", "horizon": 91}).status_code == 400
    assert client.post("/api/forecast", json={"series_id": "", "horizon": 28}).status_code == 400


@pytest.mark.slow
def test_post_forecast_real_chronos2(client: TestClient, raw_df: pd.DataFrame):
    sid = "FOODS_3_080 | Texas - TX_1"
    mat, area = sid.split(" | ")
    last_history_date = raw_df[(raw_df.material == mat) & (raw_df.area == area)]["date"].max()

    resp = client.post("/api/forecast", json={"series_id": sid, "horizon": 28})
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["dates"]) == 28
    expected_first_date = (last_history_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    assert data["dates"][0] == expected_first_date
    assert data["model"] == MODEL_ID
    assert data["device"] in ("cuda", "cpu")

    for key in ("mean", "q10", "q50", "q90"):
        vals = data[key]
        assert len(vals) == 28
        assert all(math.isfinite(v) and v >= 0.0 for v in vals)

    assert math.isfinite(data["total"])
    assert math.isfinite(data["daily_average"])
    assert data["total"] == pytest.approx(sum(data["mean"]), rel=1e-6)
    assert data["daily_average"] == pytest.approx(sum(data["mean"]) / 28, rel=1e-6)
