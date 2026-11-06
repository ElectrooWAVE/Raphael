"""Hardware, model training, decision layer, and API latency benchmarks for Raphael (Phase 7 / Step 8).

Measures:
1. Detected hardware: CPU model, core count, RAM, GPU (informational, noting GPU is unused)
2. Python & key dependency library versions
3. Model fitting benchmarks:
   - Prophet fit for 3 sample pairs
   - Random Forest lead-time model training
   - Recommendations decision layer generation for 75 pairs
4. Real HTTP latency (p50, p95, mean) of /forecast, /reorder, /urgency over localhost with N=200 requests each
5. Artifact sizes in KB
Saves artifacts/benchmarks.json.
"""
import argparse
import io
import json
import logging
import os
import platform
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import psutil
from tqdm import tqdm

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [benchmark]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("benchmark")


def get_hardware_info() -> Dict[str, Any]:
    """Detect CPU model, core counts, RAM, and GPU."""
    logger.info("Detecting system hardware...")
    cpu_name = platform.processor()
    gpu_names = []

    # Windows PowerShell CIM query for clean hardware names
    if platform.system() == "Windows":
        try:
            cmd_cpu = ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"]
            out_cpu = subprocess.check_output(cmd_cpu, timeout=5).decode().strip()
            if out_cpu:
                cpu_name = out_cpu
        except Exception:
            pass

        try:
            cmd_gpu = ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController).Name"]
            out_gpu = subprocess.check_output(cmd_gpu, timeout=5).decode().strip()
            if out_gpu:
                gpu_names = [line.strip() for line in out_gpu.splitlines() if line.strip()]
        except Exception:
            pass
    elif platform.system() == "Linux":
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        cpu_name = line.split(":", 1)[1].strip()
                        break
        except Exception:
            pass

    mem = psutil.virtual_memory()
    ram_gb = round(mem.total / (1024 ** 3), 2)
    ram_available_gb = round(mem.available / (1024 ** 3), 2)

    primary_gpu = gpu_names[0] if gpu_names else "None / Undetected"
    if len(gpu_names) > 1:
        # Prefer dedicated NVIDIA/AMD over integrated
        for g in gpu_names:
            if "NVIDIA" in g.upper() or "RTX" in g.upper() or "RADEON RX" in g.upper():
                primary_gpu = g
                break

    return {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "platform_machine": platform.machine(),
        "cpu_model": cpu_name,
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "ram_total_gb": ram_gb,
        "ram_available_gb": ram_available_gb,
        "gpu_name": primary_gpu,
        "all_gpus_detected": gpu_names,
        "gpu_pipeline_usage": "NOT USED",
        "gpu_pipeline_disclosure": (
            "The Raphael forecasting, lead-time ML, and inventory decision pipeline is strictly CPU-based. "
            "The GPU is not utilized for model training, inference, or decision calculations."
        ),
    }


def get_library_versions() -> Dict[str, str]:
    """Retrieve installed versions of Python and core analytical dependencies."""
    versions = {
        "python": platform.python_version(),
    }
    packages = [
        "numpy",
        "pandas",
        "scipy",
        "sklearn",
        "prophet",
        "pydantic",
        "fastapi",
        "uvicorn",
        "joblib",
    ]
    for pkg in packages:
        try:
            mod = __import__(pkg)
            ver = getattr(mod, "__version__", "unknown")
            pkg_name = "scikit-learn" if pkg == "sklearn" else pkg
            versions[pkg_name] = str(ver)
        except ImportError:
            versions[pkg] = "not installed"
    return versions


def benchmark_prophet_sample(data_path: Path, sample_pairs: List[Tuple[str, str]]) -> Dict[str, Any]:
    """Benchmark fitting Prophet on 3 sample pairs."""
    logger.info(f"Benchmarking Prophet fit time on {len(sample_pairs)} sample pairs...")
    if not data_path.exists():
        return {"status": "skipped", "reason": f"Data file {data_path} not found"}

    df_demand = pd.read_parquet(data_path)

    from src.models.demand_prophet import ProphetDemandModel

    pair_timings = {}
    total_start = time.perf_counter()

    for mat, area in sample_pairs:
        p_df = df_demand[(df_demand["material"] == mat) & (df_demand["area"] == area)].copy()
        if p_df.empty:
            continue
        p_df = p_df.sort_values("date").reset_index(drop=True)
        # Rename to Prophet convention ds, y, is_promotion
        p_df = p_df.rename(columns={"date": "ds", "quantity": "y"})
        # Use first 730 days (~2 years) as typical training set
        train_df = p_df.iloc[:730] if len(p_df) > 730 else p_df

        model = ProphetDemandModel(
            growth="linear",
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
        )

        p_start = time.perf_counter()
        try:
            model.fit(train_df, target_col="y", date_col="ds")
            p_elapsed = time.perf_counter() - p_start
            pair_timings[f"{mat}_{area}"] = {
                "fit_time_seconds": round(p_elapsed, 3),
                "train_rows": len(train_df),
            }
        except Exception as e:
            pair_timings[f"{mat}_{area}"] = {
                "error": str(e),
            }

    total_elapsed = time.perf_counter() - total_start
    fit_times = [v["fit_time_seconds"] for v in pair_timings.values() if "fit_time_seconds" in v]
    mean_fit = round(float(np.mean(fit_times)), 3) if fit_times else 0.0

    return {
        "status": "completed",
        "sample_pairs_count": len(sample_pairs),
        "total_elapsed_seconds": round(total_elapsed, 3),
        "mean_fit_seconds_per_pair": mean_fit,
        "pair_breakdown": pair_timings,
    }


def benchmark_rf_training(data_path: Path) -> Dict[str, Any]:
    """Benchmark Random Forest lead-time model training."""
    logger.info("Benchmarking Random Forest lead-time model training...")
    if not data_path.exists():
        return {"status": "skipped", "reason": f"Data file {data_path} not found"}

    from src.models.leadtime_rf import LeadTimeRandomForestModel

    df_lt = pd.read_parquet(data_path)
    # Use orders before split date 2015-04-11
    train_orders = df_lt[df_lt["order_date"] < "2015-04-11"].copy()
    if train_orders.empty:
        train_orders = df_lt.copy()

    rf_model = LeadTimeRandomForestModel(
        n_estimators=100,
        max_depth=12,
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
    )

    start = time.perf_counter()
    rf_model.fit(train_orders, target_col="lead_time_days")
    elapsed = time.perf_counter() - start

    return {
        "status": "completed",
        "train_rows": len(train_orders),
        "training_time_seconds": round(elapsed, 3),
        "n_estimators": 100,
        "max_depth": 12,
        "n_jobs": -1,
    }


def benchmark_recommendations_build() -> Dict[str, Any]:
    """Benchmark building inventory recommendations for all 75 pairs."""
    logger.info("Benchmarking decision layer recommendations generation...")
    rec_script = Path("scripts/04_build_decision_layer.py")
    if not rec_script.exists():
        return {"status": "skipped", "reason": "04_build_decision_layer.py not found"}

    start = time.perf_counter()
    res = subprocess.run([sys.executable, str(rec_script), "--force"], capture_output=True, text=True)
    elapsed = time.perf_counter() - start

    if res.returncode != 0:
        return {"status": "failed", "error": res.stderr[:500]}

    return {
        "status": "completed",
        "total_pairs": 75,
        "generation_time_seconds": round(elapsed, 3),
        "seconds_per_pair": round(elapsed / 75.0, 4),
    }


def benchmark_http_latency(
    base_url: str = "http://127.0.0.1:8000",
    n_requests: int = 200,
) -> Dict[str, Any]:
    """Benchmark live localhost HTTP endpoint latencies (p50, p95, mean)."""
    logger.info(f"Checking if API server is reachable at {base_url}...")
    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=2) as resp:
            if resp.status != 200:
                return {
                    "status": "skipped",
                    "reason": f"API server at {base_url} returned HTTP {resp.status}",
                }
    except Exception as e:
        return {
            "status": "skipped",
            "reason": f"API server is not running on {base_url} ({e}). Start backend with: python -m uvicorn backend.main:app --port 8000",
        }

    # URL-encode the area name for path parameter
    encoded_area = urllib.parse.quote("California - CA_1")

    endpoints = [
        ("forecast", f"{base_url}/forecast/FOODS_2_019/{encoded_area}"),
        ("reorder", f"{base_url}/reorder/FOODS_2_019/{encoded_area}"),
        ("urgency", f"{base_url}/urgency"),
    ]

    results = {}
    logger.info(f"Measuring real HTTP latency across {len(endpoints)} endpoints (N={n_requests} requests each)...")

    for name, url in endpoints:
        latencies_ms = []
        # Warmup 5 requests
        for _ in range(5):
            try:
                with urllib.request.urlopen(url, timeout=5) as r:
                    r.read()
            except Exception:
                pass

        pbar = tqdm(total=n_requests, desc=f"Latency {name}", unit="req")
        start_batch = time.perf_counter()
        for _ in range(n_requests):
            t0 = time.perf_counter()
            with urllib.request.urlopen(url, timeout=5) as r:
                r.read()
            t1 = time.perf_counter()
            latencies_ms.append((t1 - t0) * 1000.0)
            pbar.update(1)
        pbar.close()
        batch_duration = time.perf_counter() - start_batch

        results[name] = {
            "n_requests": n_requests,
            "p50_ms": round(float(np.percentile(latencies_ms, 50)), 2),
            "p95_ms": round(float(np.percentile(latencies_ms, 95)), 2),
            "p99_ms": round(float(np.percentile(latencies_ms, 99)), 2),
            "mean_ms": round(float(np.mean(latencies_ms)), 2),
            "min_ms": round(float(np.min(latencies_ms)), 2),
            "max_ms": round(float(np.max(latencies_ms)), 2),
            "throughput_req_per_sec": round(n_requests / max(1e-4, batch_duration), 1),
        }

    return {
        "status": "completed",
        "requests_per_endpoint": n_requests,
        "endpoints": results,
    }


def get_artifact_sizes(artifacts_dir: Path) -> Dict[str, Any]:
    """Measure exact sizes of precomputed Parquet and JSON artifacts in KB."""
    logger.info("Computing artifact file sizes...")
    target_files = [
        "recommendations.parquet",
        "meta.json",
        "forecasts/demand_forecasts_champion.parquet",
        "forecasts/demand_forecasts_champion.json",
        "metrics/demand_leaderboard.json",
        "metrics/champion_model_selection.json",
        "metrics/lead_time_model_evaluation.json",
        "metrics/interval_evaluation.json",
        "models/rf_lead_time_model.joblib",
        "inventory/reorder_table.parquet",
        "inventory/reorder_table.json",
        "promo_scenarios.parquet",
    ]

    sizes: Dict[str, float] = {}
    total_bytes = 0

    for rel_path in target_files:
        p = artifacts_dir / rel_path
        if p.exists():
            b = p.stat().st_size
            total_bytes += b
            sizes[rel_path] = round(b / 1024.0, 2)
        else:
            sizes[rel_path] = 0.0

    return {
        "files_kb": sizes,
        "total_selected_kb": round(total_bytes / 1024.0, 2),
        "total_selected_mb": round(total_bytes / (1024.0 * 1024.0), 3),
    }


def main():
    parser = argparse.ArgumentParser(description="Raphael Benchmark Suite")
    parser.add_argument("--force", action="store_true", help="Overwrite existing benchmarks.json")
    parser.add_argument("--skip-prophet", action="store_true", help="Skip Prophet fit benchmark")
    parser.add_argument("--n-http", type=int, default=200, help="Number of HTTP latency requests")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    artifacts_dir = project_root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    bench_file = artifacts_dir / "benchmarks.json"

    if bench_file.exists() and not args.force:
        logger.info(f"Artifact {bench_file} already exists. Use --force to rerun.")
        return

    logger.info("=" * 80)
    logger.info(" Raphael Phase 7: Benchmark Suite (Hardware, ML Training, Decisions & Latency)")
    logger.info("=" * 80)

    # 1. Hardware Info
    hw_info = get_hardware_info()

    # 2. Dependency Versions
    lib_versions = get_library_versions()

    # 3. Model Training Benchmarks
    sample_pairs = [
        ("FOODS_2_019", "California - CA_1"),
        ("FOODS_2_197", "Texas - TX_1"),
        ("FOODS_3_099", "Wisconsin - WI_1"),
    ]
    demand_data_path = project_root / "data" / "processed" / "demand.parquet"
    if not args.skip_prophet:
        prophet_bench = benchmark_prophet_sample(demand_data_path, sample_pairs)
    else:
        prophet_bench = {"status": "skipped", "reason": "User specified --skip-prophet"}

    # 4. Random Forest Lead Time Training
    lt_data_path = project_root / "data" / "processed" / "lead_time.parquet"
    rf_bench = benchmark_rf_training(lt_data_path)

    # 5. Build Recommendations (Decision Layer)
    rec_bench = benchmark_recommendations_build()

    # 6. HTTP Latency Benchmark (N=200)
    http_bench = benchmark_http_latency(base_url="http://127.0.0.1:8000", n_requests=args.n_http)

    # 7. Artifact Sizes
    artifact_sizes = get_artifact_sizes(artifacts_dir)

    # Aggregate JSON Output
    benchmark_data = {
        "timestamp": datetime.now().isoformat(),
        "as_of_date": "2016-04-24",
        "benchmark_environment": hw_info,
        "library_versions": lib_versions,
        "model_timings": {
            "prophet_3_pairs": prophet_bench,
            "random_forest_lead_time": rf_bench,
            "decision_layer_75_pairs": rec_bench,
        },
        "http_latency_localhost": http_bench,
        "artifact_storage": artifact_sizes,
    }

    # Save to artifacts/benchmarks.json
    with open(bench_file, "w", encoding="utf-8") as f:
        json.dump(benchmark_data, f, indent=2)
    logger.info(f"Saved benchmark results -> {bench_file}")

    # Also save copy to benchmark_telemetry.json for backwards compatibility
    with open(artifacts_dir / "benchmark_telemetry.json", "w", encoding="utf-8") as f:
        json.dump(benchmark_data, f, indent=2)

    logger.info("=" * 80)
    logger.info(" BENCHMARK EXECUTION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"CPU Model         : {hw_info['cpu_model']} ({hw_info['physical_cores']}C / {hw_info['logical_cores']}T)")
    logger.info(f"System RAM        : {hw_info['ram_total_gb']} GB")
    logger.info(f"GPU Detected      : {hw_info['gpu_name']} [INFORMATIONAL ONLY: PIPELINE USES CPU]")
    logger.info(f"Prophet (3 pairs) : {prophet_bench.get('total_elapsed_seconds', 'N/A')}s (mean {prophet_bench.get('mean_fit_seconds_per_pair', 'N/A')}s/pair)")
    logger.info(f"Random Forest     : {rf_bench.get('training_time_seconds', 'N/A')}s")
    logger.info(f"Decision Layer    : {rec_bench.get('generation_time_seconds', 'N/A')}s")
    if http_bench.get("status") == "completed":
        for ep, stats in http_bench["endpoints"].items():
            logger.info(f"HTTP /{ep:12s}: p50={stats['p50_ms']}ms | p95={stats['p95_ms']}ms | throughput={stats['throughput_req_per_sec']} req/s")
    else:
        logger.info(f"HTTP Latency      : {http_bench.get('reason')}")
    logger.info(f"Total Artifacts   : {artifact_sizes['total_selected_kb']} KB ({artifact_sizes['total_selected_mb']} MB)")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
