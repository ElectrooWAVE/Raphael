"""Shared session-scoped FastAPI TestClient fixture so Chronos-2 loads once per test run."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from server.main import app


@pytest.fixture(scope="session")
def client():
    t0 = time.perf_counter()
    with TestClient(app) as c:
        print(f"\n[conftest] FastAPI lifespan + Chronos-2 loaded in {time.perf_counter() - t0:.2f}s")
        yield c
