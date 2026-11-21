"""Safeguard tests: every frontend API URL in web/app.js must exist in FastAPI OpenAPI routes."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.main import app

WEB_APP_JS = Path(__file__).resolve().parents[1] / "web" / "app.js"


def extract_frontend_api_paths(js_text: str) -> set[str]:
    """Extract literal and template-literal /api/... paths from web/app.js."""
    raw_matches = re.findall(r"""[`"'](/api/[^`"']+)[`"']""", js_text)
    normalized: set[str] = set()
    for raw in raw_matches:
        no_query = raw.split("?", 1)[0]
        # Convert JS ${expr} interpolation to OpenAPI {param} placeholder pattern
        path = re.sub(r"\$\{[^}]+\}", "{param}", no_query)
        normalized.add(path)
    return normalized


def _openapi_pattern(openapi_path: str) -> re.Pattern[str]:
    escaped = re.sub(r"\{[^}]+\}", r"[^/]+", openapi_path)
    return re.compile(f"^{escaped}$")


def test_all_frontend_api_routes_exist_in_openapi():
    js_text = WEB_APP_JS.read_text(encoding="utf-8")
    frontend_paths = extract_frontend_api_paths(js_text)
    assert len(frontend_paths) >= 12

    openapi_paths = list(app.openapi()["paths"].keys())
    patterns = [_openapi_pattern(p) for p in openapi_paths]

    missing = []
    for f_path in sorted(frontend_paths):
        sample = f_path.replace("{param}", "sample_id")
        if not any(pat.match(sample) for pat in patterns):
            missing.append(f_path)

    assert not missing, f"Frontend calls missing from FastAPI OpenAPI routes: {missing}"


@pytest.mark.slow
def test_all_tabs_endpoints_smoke(client: TestClient):
    import time

    t0 = time.perf_counter()
    # Overview & Health
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/overview").status_code == 200

    # Forecasting
    s_resp = client.get("/api/series")
    assert s_resp.status_code == 200
    sid = s_resp.json()[0]
    assert client.get("/api/history", params={"series_id": sid}).status_code == 200
    fc_resp = client.post("/api/forecast", json={"series_id": sid, "horizon": 28, "model_type": "chronos"})
    assert fc_resp.status_code == 200
    run_id = fc_resp.json()["run_id"]

    # Model Training & Datasets
    assert client.get("/api/datasets").status_code == 200
    assert client.get("/api/models").status_code == 200

    # Model Comparison
    assert client.post("/api/compare", json={"series_id": sid, "horizon": 14, "cutoff_index": 100}).status_code == 200

    # Forecasting History
    assert client.get("/api/history/runs", params={"paginated": True}).status_code == 200
    assert client.get(f"/api/history/runs/{run_id}").status_code == 200
    assert client.delete(f"/api/history/runs/{run_id}").status_code == 200
    print(f"[slow] Stage All-Tabs API Smoke (Chronos-2 + Compare) took {time.perf_counter() - t0:.2f}s")
