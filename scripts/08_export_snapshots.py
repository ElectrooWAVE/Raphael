#!/usr/bin/env python3
"""
scripts/08_export_snapshots.py

Exports all GET responses used by the frontend into frontend/public/snapshots/*.json
along with a manifest.json containing generation time, as-of date, pair count, and status breakdown.
Maintains total snapshot size well under 15 MB.
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from starlette.testclient import TestClient
from tqdm import tqdm

# Ensure workspace root is in python path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from backend.main import app
from src.utils.logger import setup_logger


def safe_area_slug(area: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "_", area)


def main():
    parser = argparse.ArgumentParser(description="Export frontend offline API snapshots.")
    parser.add_argument("--force", action="store_true", help="Force overwrite existing snapshots.")
    args = parser.parse_args()

    logger = setup_logger("08_export_snapshots", log_dir="logs")
    logger.info("=" * 80)
    logger.info(" Raphael Step 10: Exporting Offline Snapshots")
    logger.info("=" * 80)

    snapshots_dir = WORKSPACE_ROOT / "frontend" / "public" / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    total_files = 0
    total_bytes = 0

    with TestClient(app) as client:
        def save_json(filename: str, data: Any):
            nonlocal total_files, total_bytes
            file_path = snapshots_dir / filename
            if file_path.exists() and not args.force:
                logger.debug(f"File exists, skipping: {filename}")
                return
            content = json.dumps(data, separators=(",", ":"))
            file_path.write_text(content, encoding="utf-8")
            total_files += 1
            total_bytes += len(content.encode("utf-8"))

        # 1. Global Endpoints
        logger.info("Exporting global static endpoints...")
        global_endpoints = [
            ("/health", "health.json"),
            ("/meta", "meta.json"),
            ("/materials", "materials.json"),
            ("/areas", "areas.json"),
            ("/urgency", "urgency.json"),
            ("/urgency?status=CRITICAL", "urgency_CRITICAL.json"),
            ("/urgency?status=REORDER", "urgency_REORDER.json"),
            ("/accuracy", "accuracy.json"),
            ("/benchmarks", "benchmarks.json"),
            ("/metrics/intervals", "metrics_intervals.json"),
            ("/metrics/leadtime", "metrics_leadtime.json"),
        ]

        for endpoint, filename in global_endpoints:
            res = client.get(endpoint)
            if res.status_code != 200:
                logger.error(f"Failed to fetch {endpoint}: {res.status_code}")
                sys.exit(1)
            save_json(filename, res.json())

        # 2. Material-Specific Areas
        materials_res = client.get("/materials").json()
        materials = materials_res.get("materials", [])
        logger.info(f"Exporting area listings for {len(materials)} materials...")
        for mat in materials:
            res = client.get(f"/areas?material={mat}")
            if res.status_code == 200:
                save_json(f"areas_{mat}.json", res.json())

        # 3. Urgency Data & Pair Breakdown
        urgency_res = client.get("/urgency").json()
        urgency_items = urgency_res.get("items", [])
        pairs = [(item["material"], item["area"]) for item in urgency_items]

        status_breakdown: Dict[str, int] = {}
        for item in urgency_items:
            st = item.get("status", "UNKNOWN")
            status_breakdown[st] = status_breakdown.get(st, 0) + 1

        logger.info(f"Exporting pair-level forecasts, reorder policies, and lead times for {len(pairs)} pairs...")
        for mat, area in tqdm(pairs, desc="Exporting pairs", unit="pair"):
            slug_area = safe_area_slug(area)

            # Forecast
            res_fc = client.get(f"/forecast/{mat}/{area}")
            if res_fc.status_code == 200:
                save_json(f"forecast_{mat}__{slug_area}.json", res_fc.json())

            # Reorder
            res_ro = client.get(f"/reorder/{mat}/{area}")
            if res_ro.status_code == 200:
                save_json(f"reorder_{mat}__{slug_area}.json", res_ro.json())

            # Lead Time
            res_lt = client.get(f"/leadtime/{mat}/{area}")
            if res_lt.status_code == 200:
                save_json(f"leadtime_{mat}__{slug_area}.json", res_lt.json())

        # 4. Manifest
        now_iso = datetime.now(timezone.utc).isoformat()
        health_res = client.get("/health").json()
        as_of_date = health_res.get("as_of_date", "2016-04-24")

        manifest = {
            "generated_at": now_iso,
            "as_of_date": as_of_date,
            "total_pairs": len(pairs),
            "status_breakdown": status_breakdown,
            "total_files": total_files + 1,
            "total_size_bytes": total_bytes,
            "total_size_mb": round(total_bytes / (1024 * 1024), 2),
        }

        manifest_path = snapshots_dir / "manifest.json"
        manifest_content = json.dumps(manifest, indent=2)
        manifest_path.write_text(manifest_content, encoding="utf-8")
        total_bytes += len(manifest_content.encode("utf-8"))
        total_files += 1

    total_mb = total_bytes / (1024 * 1024)
    logger.info("-" * 80)
    logger.info(f"Snapshot Export Complete: {total_files} files written.")
    logger.info(f"Total Snapshot Size: {total_mb:.2f} MB (Limit: 15.0 MB)")
    logger.info(f"Status Breakdown: {status_breakdown}")
    logger.info(f"Manifest written to {manifest_path}")
    logger.info("=" * 80)

    if total_mb > 15.0:
        logger.error(f"Snapshot size exceeds 15 MB threshold: {total_mb:.2f} MB")
        sys.exit(1)


if __name__ == "__main__":
    main()
