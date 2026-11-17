"""Timed end-to-end verification for GPU, Chronos-2 inference, and FastAPI tests.

Run:  .venv\\Scripts\\python.exe scripts/run_checks.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def timed(label: str):
    print(f"\n==> {label}...", flush=True)
    return time.perf_counter()


def main() -> int:
    t0 = timed("1. Checking PyTorch & CUDA")
    import torch

    cuda_ok = torch.cuda.is_available()
    gpu_name = torch.cuda.get_device_name(0) if cuda_ok else "CPU only"
    print(f"   torch={torch.__version__} | cuda_available={cuda_ok} | device={gpu_name} ({time.perf_counter() - t0:.2f}s)", flush=True)

    t1 = timed("2. Loading sales data & Chronos-2 pipeline")
    import numpy as np
    from rdf.data_loader import get_series, load_sales
    from rdf.forecaster import forecast, load_pipeline

    sales = load_sales()
    pipeline, device = load_pipeline()
    print(f"   Loaded {sales['series_id'].nunique()} series and Chronos-2 on [{device}] ({time.perf_counter() - t1:.2f}s)", flush=True)

    t2 = timed("3. Running 2 real Chronos-2 backtest forecasts (horizon=28)")
    horizon = 28
    for sid in ["HOUSEHOLD_1_517 | California - CA_1", "FOODS_3_080 | Texas - TX_1"]:
        s = get_series(sales, sid)
        train, actual = s.iloc[:-horizon], s.iloc[-horizon:]["sales"].to_numpy()
        f = forecast(pipeline, train, horizon, sid)
        assert len(f) == horizon and np.isfinite(f["median"]).all() and np.isfinite(f["expected"]).all()
        mae = float(np.abs(f["median"].to_numpy() - actual).mean())
        naive = float(np.abs(train["sales"].tail(horizon).mean() - actual).mean())
        print(f"   [{device}] {sid}: Chronos-2 MAE={mae:.2f} | baseline MAE={naive:.2f}", flush=True)
    print(f"   Forecasts complete ({time.perf_counter() - t2:.2f}s)", flush=True)

    t3 = timed("4. Running pytest on tests/test_api.py")
    cmd = [sys.executable, "-m", "pytest", "tests/test_api.py", "-q", "-x", "--durations=5"]
    res = subprocess.run(cmd, cwd=ROOT)
    print(f"   pytest finished with code {res.returncode} ({time.perf_counter() - t3:.2f}s)", flush=True)
    return res.returncode


if __name__ == "__main__":
    raise SystemExit(main())
