"""Integration tests for expanded Platform API endpoints."""
import pytest
from fastapi.testclient import TestClient

from server.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def test_api_overview(client: TestClient):
    resp = client.get("/api/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_datasets" in data
    assert "total_series" in data
    assert "total_models" in data
    assert "recent_runs" in data


def test_api_datasets(client: TestClient):
    resp = client.get("/api/datasets")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "name" in data[0]
    assert "num_series" in data[0]


def test_api_models_list(client: TestClient):
    resp = client.get("/api/models")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_api_baseline_forecast(client: TestClient):
    payload = {
        "series_id": "FOODS_2_019 | California - CA_1",
        "horizon": 14,
        "model_type": "baseline",
    }
    resp = client.post("/api/forecast", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["dates"]) == 14
    assert len(data["median"]) == 14
    assert data["model_type"] == "baseline"


def test_api_compare(client: TestClient):
    payload = {
        "series_id": "FOODS_2_019 | California - CA_1",
        "horizon": 14,
        "cutoff_index": 100,
    }
    resp = client.post("/api/compare", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["series_id"] == "FOODS_2_019 | California - CA_1"
    assert "baseline" in data["forecasts"]
    assert "metrics" in data


def test_api_history_runs(client: TestClient):
    resp = client.get("/api/history/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    run_id = data[0]["id"]

    # Test run details
    detail_resp = client.get(f"/api/history/runs/{run_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["id"] == run_id
    assert "values" in detail


def test_api_train_custom_model(client: TestClient):
    payload = {
        "dataset_id": "retail-demand-m5",
        "model_name": "Test-Custom-Model",
        "n_estimators": 20,
        "learning_rate": 0.1,
        "max_depth": 4,
        "num_leaves": 15,
        "min_child_samples": 10,
        "val_fraction": 0.1,
        "lags": [1, 7],
        "rolling_windows": [7],
    }
    resp = client.post("/api/models/train", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "run_id" in data
    assert data["status"] in ("QUEUED", "RUNNING")

    # Poll status
    status_resp = client.get(f"/api/models/train/{data['run_id']}")
    assert status_resp.status_code == 200
    s_data = status_resp.json()
    assert "status" in s_data
    assert s_data["status"] in ("QUEUED", "RUNNING", "COMPLETED")
