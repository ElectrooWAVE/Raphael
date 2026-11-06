"""Smoke test script for Raphael API (Phase 6).

Calls every endpoint and prints:
- HTTP status
- Response size in KB
- Latency in milliseconds

Performs exact consistency checks:
- Verifies that /reorder/{material}/{area} and /urgency values exactly match
  the ground-truth artifacts/recommendations.parquet for 5 random pairs.

Can run either:
- Against an active live server: python scripts/smoke_test_api.py --base-url http://127.0.0.1:8000
- In-process via TestClient: python scripts/smoke_test_api.py
"""
import argparse
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple
import pandas as pd
import httpx
from starlette.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import app


class EndpointCaller:
    """Dispatches requests to either a live HTTP server or an in-process TestClient."""

    def __init__(self, base_url: str = None):
        self.base_url = base_url
        self.test_client = None
        self.http_client = None
        if self.base_url:
            self.http_client = httpx.Client(base_url=self.base_url)
        else:
            self.test_client = TestClient(app)
            self.test_client.__enter__()

    def close(self):
        if self.test_client:
            self.test_client.__exit__(None, None, None)
        if self.http_client:
            self.http_client.close()

    def get(self, path: str):
        t0 = time.perf_counter()
        if self.http_client:
            resp = self.http_client.get(path)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return resp.status_code, resp.content, elapsed_ms, resp
        else:
            resp = self.test_client.get(path)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return resp.status_code, resp.content, elapsed_ms, resp

    def post(self, path: str, json_data: dict):
        t0 = time.perf_counter()
        if self.http_client:
            resp = self.http_client.post(path, json=json_data)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return resp.status_code, resp.content, elapsed_ms, resp
        else:
            resp = self.test_client.post(path, json=json_data)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return resp.status_code, resp.content, elapsed_ms, resp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Raphael API Smoke Test Suite.")
    parser.add_argument("--base-url", type=str, default=None, help="Live server URL (e.g. http://127.0.0.1:8000). If omitted, tests in-process.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for consistency check sampling.")
    return parser.parse_args()


def main():
    args = parse_args()
    caller = EndpointCaller(base_url=args.base_url)

    target_desc = args.base_url if args.base_url else "In-Process TestClient (zero overhead)"
    print("=" * 90)
    print(f" Raphael API Smoke Test Suite - Target: {target_desc}")
    print("=" * 90)

    # 1. Endpoint Smoke Tests
    endpoints = [
        ("GET", "/health", None),
        ("GET", "/meta", None),
        ("GET", "/materials", None),
        ("GET", "/areas", None),
        ("GET", "/areas?material=FOODS_2_019", None),
        ("GET", "/forecast/FOODS_3_099/California - CA_1", None),
        ("GET", "/reorder/FOODS_3_099/California - CA_1", None),
        ("GET", "/urgency", None),
        ("GET", "/urgency?status=CRITICAL", None),
        ("GET", "/urgency?status=REORDER", None),
        ("GET", "/accuracy", None),
        ("GET", "/leadtime/FOODS_3_099/California - CA_1", None),
        ("POST", "/whatif", {
            "demand_rate": 10.0,
            "demand_std": 2.0,
            "lead_time": 4.0,
            "lead_time_std": 1.0,
            "service_level": 0.95,
            "current_stock": 80.0,
        }),
        ("GET", "/export/recommendations.csv", None),
        ("GET", "/benchmarks", None),
    ]

    print(f"{'Method':<6} | {'Endpoint':<45} | {'Status':<8} | {'Size':<10} | {'Latency':<10}")
    print("-" * 90)

    all_passed = True
    total_latency_ms = 0.0

    for method, path, body in endpoints:
        if method == "GET":
            status_code, content, ms, _ = caller.get(path)
        else:
            status_code, content, ms, _ = caller.post(path, body)

        size_kb = len(content) / 1024.0
        total_latency_ms += ms
        passed = (status_code == 200)
        status_str = f"{status_code} OK" if passed else f"{status_code} ERR"
        if not passed:
            all_passed = False

        print(f"{method:<6} | {path:<45} | {status_str:<8} | {size_kb:>7.2f} KB | {ms:>7.2f} ms")

    avg_latency = total_latency_ms / len(endpoints)
    print("-" * 90)
    print(f"Smoke Test Completed: {len(endpoints)} endpoints | Average Latency: {avg_latency:.2f} ms")
    print("=" * 90)

    # 2. Consistency Verification against Parquet Ground Truth (5 Random Pairs)
    rec_path = Path("artifacts/recommendations.parquet")
    if not rec_path.exists():
        rec_path = Path("artifacts/inventory/reorder_table.parquet")

    df_gt = pd.read_parquet(rec_path)
    rng = random.Random(args.seed)
    sampled_indices = rng.sample(range(len(df_gt)), 5)
    sampled_rows = df_gt.iloc[sampled_indices]

    print("\n" + "=" * 90)
    print(" GROUND-TRUTH CONSISTENCY VERIFICATION (5 Random Pairs vs artifacts/recommendations.parquet)")
    print("=" * 90)
    print(f"{'Material':<16} | {'Area':<18} | {'Field':<15} | {'Parquet Value':<15} | {'API Value':<15} | {'Match'}")
    print("-" * 90)

    consistency_passed = True
    fields_to_check = [
        ("reorder_point_rop", 1),
        ("safety_stock_ss", 1),
        ("days_remaining", 1),
        ("status", None),
        ("predicted_lead_time_days", 1),
        ("recommended_order_quantity", 1),
        ("urgency_rank", None),
    ]

    for _, row in sampled_rows.iterrows():
        mat = row["material"]
        area = row["area"]

        # Call /reorder
        status_code, content, ms, resp = caller.get(f"/reorder/{mat}/{area}")
        if status_code != 200:
            print(f"FAILED to fetch /reorder/{mat}/{area}: {status_code}")
            consistency_passed = False
            continue

        api_data = resp.json()

        for field, precision in fields_to_check:
            parquet_val = row[field]
            api_val = api_data.get(field)

            if precision is not None:
                matches = abs(float(parquet_val) - float(api_val)) < 0.05
                parquet_str = f"{float(parquet_val):.2f}"
                api_str = f"{float(api_val):.2f}"
            else:
                matches = (str(parquet_val) == str(api_val))
                parquet_str = str(parquet_val)
                api_str = str(api_val)

            match_icon = "[OK]" if matches else "[MISMATCH]"
            if not matches:
                consistency_passed = False

            print(f"{mat:<16} | {area:<18} | {field:<15} | {parquet_str:<15} | {api_str:<15} | {match_icon}")
        print("-" * 90)

    caller.close()

    print("=" * 90)
    if all_passed and consistency_passed:
        print(" [PASSED] ALL ENDPOINTS RESPONDED WITH 200 AND ALL 5 RANDOM PAIRS MATCHED PARQUET 100%.")
    else:
        print(" [FAILED] Some endpoints or consistency checks did not match.")
        sys.exit(1)
    print("=" * 90)


if __name__ == "__main__":
    main()
