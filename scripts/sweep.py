"""Hyperparameter sweep over scripts/finetune.py (validation window only).

Grid: steps in {250, 500, 1000} x lr in {1e-5, 5e-5} (mode=lora).
Skips runs already recorded in reports/finetune_runs.csv.

Run:  .venv\\Scripts\\python.exe scripts/sweep.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
RUNS_CSV = ROOT / "reports" / "finetune_runs.csv"
STEPS_GRID = [250, 500, 1000]
LR_GRID = [1e-5, 5e-5]


def completed_tags() -> set[str]:
    if not RUNS_CSV.exists():
        return set()
    df = pd.read_csv(RUNS_CSV)
    return set(df["tag"].astype(str).tolist()) if "tag" in df.columns else set()


def main() -> int:
    combos = [(s, lr, f"lora-s{s}-lr{lr:.0e}") for s in STEPS_GRID for lr in LR_GRID]
    done = completed_tags()

    for steps, lr, tag in tqdm(combos, desc="Sweep grid", unit="run"):
        if tag in done:
            print(f"Skipping already-completed run: {tag}", flush=True)
            continue
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "finetune.py"),
            "--steps",
            str(steps),
            "--lr",
            str(lr),
            "--mode",
            "lora",
            "--tag",
            tag,
        ]
        res = subprocess.run(cmd, cwd=ROOT)
        if res.returncode != 0:
            print(f"Run {tag} failed with code {res.returncode}", file=sys.stderr)
            return res.returncode

    if RUNS_CSV.exists():
        df = pd.read_csv(RUNS_CSV).sort_values("val_q50_wape", ascending=True)
        print("\nSweep results sorted by val_q50_wape:")
        print(df[["tag", "steps", "lr", "mode", "val_q50_wape", "val_q50_mae", "val_mean_wape", "val_mean_mae", "minutes"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
