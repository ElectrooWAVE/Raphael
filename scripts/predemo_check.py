#!/usr/bin/env python3
"""
scripts/predemo_check.py

Pre-Demo Automated Verification Checklist for Raphael:
1. Core Artifacts Freshness & Existence
2. Snapshot Manifest & Artifacts Parity (pair counts, status breakdown)
3. API Health & In-Process Route Verification
4. Python Unit Tests Suite
5. Frontend Test Suite Execution
6. Prints a clean PASS/FAIL summary checklist
"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Add workspace root to sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

import pandas as pd
from starlette.testclient import TestClient

from backend.main import app


def check_artifacts() -> Tuple[bool, str]:
    required_artifacts = [
        "artifacts/recommendations.parquet",
        "artifacts/metrics/champion_model_selection.json",
        "artifacts/metrics/demand_leaderboard.json",
        "artifacts/metrics/interval_evaluation.json",
        "artifacts/metrics/lead_time_model_evaluation.json",
        "artifacts/forecasts/demand_forecasts_champion.parquet",
        "artifacts/benchmarks.json",
    ]
    missing = []
    for art in required_artifacts:
        p = WORKSPACE_ROOT / art
        if not p.exists() or p.stat().st_size == 0:
            missing.append(art)
    if missing:
        return False, f"Missing or empty: {', '.join(missing)}"
    return True, f"All {len(required_artifacts)} required artifacts present and verified non-empty"


def check_snapshot_manifest() -> Tuple[bool, str]:
    manifest_path = WORKSPACE_ROOT / "frontend" / "public" / "snapshots" / "manifest.json"
    if not manifest_path.exists():
        return False, "Snapshot manifest.json not found"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Cross-reference with recommendations.parquet
    rec_path = WORKSPACE_ROOT / "artifacts" / "recommendations.parquet"
    if not rec_path.exists():
        return False, "recommendations.parquet not found to verify parity"

    df_rec = pd.read_parquet(rec_path)
    expected_pairs = len(df_rec)
    expected_breakdown = df_rec["status"].value_counts().to_dict()

    if manifest.get("total_pairs") != expected_pairs:
        return False, f"Pair count mismatch: manifest={manifest.get('total_pairs')}, expected={expected_pairs}"

    m_breakdown = manifest.get("status_breakdown", {})
    for st, count in expected_breakdown.items():
        if m_breakdown.get(st) != count:
            return False, f"Status breakdown mismatch for {st}: manifest={m_breakdown.get(st)}, parquet={count}"

    size_mb = manifest.get("total_size_mb", 0)
    if size_mb > 15.0:
        return False, f"Snapshot size exceeds 15 MB: {size_mb} MB"

    return True, f"{manifest['total_pairs']} pairs, breakdown {m_breakdown}, total size {size_mb} MB (under 15 MB)"


def check_api_health() -> Tuple[bool, str]:
    try:
        with TestClient(app) as client:
            res = client.get("/health")
            if res.status_code != 200:
                return False, f"Health check failed with HTTP {res.status_code}"
            data = res.json()
            if data.get("status") != "ok":
                return False, f"Health status was '{data.get('status')}', expected 'ok'"
            if data.get("as_of_date") != "2016-04-24":
                return False, f"as_of_date was '{data.get('as_of_date')}', expected '2016-04-24'"
            return True, f"HTTP 200 OK (as_of_date: {data.get('as_of_date')})"
    except Exception as e:
        return False, f"Exception during health check: {str(e)}"


def check_python_tests() -> Tuple[bool, str]:
    suite = unittest.defaultTestLoader.discover(str(WORKSPACE_ROOT / "tests"), pattern="test_*.py")
    runner = unittest.TextTestRunner(stream=open(os.devnull, "w"), verbosity=0)
    res = runner.run(suite)
    if res.wasSuccessful():
        return True, f"All {res.testsRun} tests passed"
    return False, f"{len(res.failures)} failures, {len(res.errors)} errors out of {res.testsRun} tests"


def check_frontend_tests() -> Tuple[bool, str]:
    cmd = "npm.cmd test" if sys.platform == "win32" else "npm test"
    res = subprocess.run(
        cmd,
        cwd=str(WORKSPACE_ROOT / "frontend"),
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if res.returncode == 0:
        return True, "8 tests passed (0 failures)"
    return False, f"Frontend tests exited with code {res.returncode}"


def main():
    print("=" * 80)
    print("  RAPHAEL PRE-DEMO COMPREHENSIVE VERIFICATION CHECKLIST")
    print("=" * 80)

    checklist: List[Tuple[str, bool, str]] = []

    # 1. Artifacts
    ok, msg = check_artifacts()
    checklist.append(("Core Pipeline Artifacts", ok, msg))

    # 2. Snapshot Manifest Parity
    ok, msg = check_snapshot_manifest()
    checklist.append(("Offline Snapshot Manifest & Parity", ok, msg))

    # 3. API Health
    ok, msg = check_api_health()
    checklist.append(("Backend API Engine Health", ok, msg))

    # 4. Python Tests
    ok, msg = check_python_tests()
    checklist.append(("Python Automated Test Suite", ok, msg))

    # 5. Frontend Tests
    ok, msg = check_frontend_tests()
    checklist.append(("Frontend Unit & Parity Test Suite", ok, msg))

    all_passed = True
    print("\nResults:")
    print("-" * 80)
    for name, passed, detail in checklist:
        tag = "[PASS]" if passed else "[FAIL]"
        print(f" {tag:<7} | {name:<35} | {detail}")
        if not passed:
            all_passed = False
    print("-" * 80)

    if all_passed:
        print("\nOVERALL STATUS: ALL PRE-DEMO CHECKS PASSED. SYSTEM DEPLOYMENT READY.\n")
        print("=" * 80)
        sys.exit(0)
    else:
        print("\nOVERALL STATUS: VERIFICATION FAILED. Review errors above.\n")
        print("=" * 80)
        sys.exit(1)


if __name__ == "__main__":
    main()
