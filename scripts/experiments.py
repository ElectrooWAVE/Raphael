"""Validation-only experiment grid: context_length x cross_learning.

Uses 5 rolling 28-day origins ending at the validation end (len(s) - 28).
Never touches the final 28-day test window.

Grid: context_length in {90, 180, 365, 730, all} x cross_learning in {False, True}
Output: reports/experiments.csv
Run:    .venv\\Scripts\\python.exe scripts/experiments.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import numpy as np
import pandas as pd
from tqdm import tqdm

from rdf.data_loader import get_series, list_series, load_sales
from rdf.forecaster import DENSE_QUANTILES, load_pipeline

HORIZON = 28
N_ORIGINS = 5
REPORTS_DIR = ROOT / "reports"
EXPERIMENTS_CSV = REPORTS_DIR / "experiments.csv"
CONTEXT_GRID: list[int | None] = [90, 180, 365, 730, None]
CROSS_GRID: list[bool] = [False, True]


def safe_wape(abs_err_sum: float, actual_sum: float) -> float:
    return float(abs_err_sum / actual_sum) if actual_sum > 0 else float("nan")


def completed_configs() -> set[str]:
    if not EXPERIMENTS_CSV.exists():
        return set()
    df = pd.read_csv(EXPERIMENTS_CSV)
    return set(df["config"].astype(str).tolist()) if "config" in df.columns else set()


def evaluate_config(
    pipeline,
    series_map: dict[str, pd.DataFrame],
    context_length: int | None,
    cross_learning: bool,
) -> dict:
    q_cols = [str(q) for q in DENSE_QUANTILES]
    all_act, all_med, all_exp, all_q10, all_q90 = [], [], [], [], []
    tot_med_err, tot_exp_err = [], []

    for origin_idx in range(N_ORIGINS):
        back = (N_ORIGINS - origin_idx) * HORIZON + HORIZON  # ends at len - 28 when origin_idx == 4
        ctx_frames = []
        actuals: dict[str, np.ndarray] = {}

        for sid, s in series_map.items():
            start = len(s) - back
            end = start + HORIZON
            train_df = s.iloc[:start]
            actuals[sid] = s.iloc[start:end]["sales"].to_numpy(dtype=np.float64)
            ctx_frames.append(
                pd.DataFrame({
                    "item_id": sid,
                    "timestamp": train_df["date"].values,
                    "target": train_df["sales"].values,
                })
            )

        out = pipeline.predict_df(
            pd.concat(ctx_frames, ignore_index=True),
            id_column="item_id",
            timestamp_column="timestamp",
            target="target",
            prediction_length=HORIZON,
            quantile_levels=DENSE_QUANTILES,
            context_length=context_length,
            cross_learning=cross_learning,
            freq="D",
        )
        dense_clipped = out[q_cols].clip(lower=0)
        out["median"] = out["predictions"].clip(lower=0)
        out["expected"] = dense_clipped.mean(axis=1)
        out["q10"] = out["0.1"].clip(lower=0)
        out["q90"] = out["0.9"].clip(lower=0)

        for sid, grp in out.groupby("item_id", sort=False):
            grp = grp.sort_values("timestamp")
            act = actuals[sid]
            med = grp["median"].to_numpy(dtype=np.float64)
            exp = grp["expected"].to_numpy(dtype=np.float64)
            q10 = grp["q10"].to_numpy(dtype=np.float64)
            q90 = grp["q90"].to_numpy(dtype=np.float64)

            all_act.append(act)
            all_med.append(med)
            all_exp.append(exp)
            all_q10.append(q10)
            all_q90.append(q90)
            tot_med_err.append(abs(float(med.sum() - act.sum())))
            tot_exp_err.append(abs(float(exp.sum() - act.sum())))

    a = np.concatenate(all_act)
    m = np.concatenate(all_med)
    e = np.concatenate(all_exp)
    ql = np.concatenate(all_q10)
    qh = np.concatenate(all_q90)
    a_sum = float(a.sum())

    return {
        "median_wape": safe_wape(float(np.abs(m - a).sum()), a_sum),
        "median_mae": float(np.abs(m - a).mean()),
        "median_bias": float((m - a).mean()),
        "median_total_mae": float(np.mean(tot_med_err)),
        "expected_wape": safe_wape(float(np.abs(e - a).sum()), a_sum),
        "expected_mae": float(np.abs(e - a).mean()),
        "expected_bias": float((e - a).mean()),
        "expected_total_mae": float(np.mean(tot_exp_err)),
        "coverage80": float(np.mean((a >= ql) & (a <= qh))),
    }


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    sales = load_sales()
    series_map = {sid: get_series(sales, sid) for sid in list_series(sales)}
    pipeline, device = load_pipeline()
    done = completed_configs()

    grid = [(ctx, cl) for ctx in CONTEXT_GRID for cl in CROSS_GRID]
    for ctx, cl in tqdm(grid, desc=f"Experiments ({device})", unit="cfg"):
        ctx_label = str(ctx) if ctx is not None else "all"
        cfg_name = f"ctx={ctx_label}|cross={cl}"
        if cfg_name in done:
            tqdm.write(f"Skipping {cfg_name} (already in {EXPERIMENTS_CSV.name})")
            continue

        t0 = time.perf_counter()
        metrics = evaluate_config(pipeline, series_map, ctx, cl)
        elapsed = round(time.perf_counter() - t0, 2)

        row = pd.DataFrame([{
            "config": cfg_name,
            "context_length": ctx_label,
            "cross_learning": cl,
            **metrics,
            "seconds": elapsed,
        }])
        row.to_csv(EXPERIMENTS_CSV, mode="a", header=not EXPERIMENTS_CSV.exists(), index=False)

    if EXPERIMENTS_CSV.exists():
        df = pd.read_csv(EXPERIMENTS_CSV).sort_values("median_wape", ascending=True)
        cols = [
            "config",
            "median_wape",
            "median_mae",
            "median_bias",
            "median_total_mae",
            "expected_wape",
            "expected_mae",
            "expected_bias",
            "expected_total_mae",
            "coverage80",
            "seconds",
        ]
        print("\nValidation experiments sorted by median_wape:")
        print(df[cols].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
