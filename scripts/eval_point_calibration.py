"""Validation-only comparison of median vs expected (dense quantile mean) and 80% interval calibration.

Split per series (test window [-28:] is NEVER touched):
  - val_end = len(s) - 28
  - 5 rolling 28-day origins ending at val_end (origins 0, 1, 2, 3, 4)
  - Calibration scale k is fit on the first 3 origins and checked honestly on the last 2 origins.

Output: reports/point_calibration.csv
Run:    .venv\\Scripts\\python.exe scripts/eval_point_calibration.py
"""
from __future__ import annotations

import sys
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


def safe_wape(abs_err_sum: float, actual_sum: float) -> float:
    return float(abs_err_sum / actual_sum) if actual_sum > 0 else float("nan")


def scaled_coverage(actual: np.ndarray, med: np.ndarray, q10: np.ndarray, q90: np.ndarray, k: float) -> float:
    low = np.clip(med - k * (med - q10), 0.0, None)
    high = np.clip(med + k * (q90 - med), 0.0, None)
    return float(np.mean((actual >= low) & (actual <= high)))


def fit_scale_factor(actual: np.ndarray, med: np.ndarray, q10: np.ndarray, q90: np.ndarray, target_cov: float = 0.80) -> float:
    lo, hi = 0.0, 10.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if scaled_coverage(actual, med, q10, q90, mid) < target_cov:
            lo = mid
        else:
            hi = mid
    return hi


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    sales = load_sales()
    series_map = {sid: get_series(sales, sid) for sid in list_series(sales)}
    pipeline, device = load_pipeline()

    q_cols = [str(q) for q in DENSE_QUANTILES]
    rows: list[dict] = []

    # 5 origins ending at val_end = len(s) - 28 (so k_idx=0 is earliest, k_idx=4 is [-56:-28])
    for origin_idx in tqdm(range(N_ORIGINS), desc="Validation origins", unit="origin"):
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
            for i in range(HORIZON):
                rows.append({
                    "origin_idx": origin_idx,
                    "series_id": sid,
                    "actual": float(act[i]),
                    "median": float(med[i]),
                    "expected": float(exp[i]),
                    "q10": float(q10[i]),
                    "q90": float(q90[i]),
                })

    df = pd.DataFrame(rows)
    df.to_csv(REPORTS_DIR / "point_calibration.csv", index=False)

    act = df["actual"].to_numpy()
    act_sum = float(act.sum())
    tot = df.groupby(["origin_idx", "series_id"], as_index=False)[["actual", "median", "expected"]].sum()

    print(f"\nVALIDATION POINT COMPARISON (5 origins x 28d x 75 series, device={device}):")
    for col in ("median", "expected"):
        pred = df[col].to_numpy()
        err = pred - act
        tot_err = tot[col].to_numpy() - tot["actual"].to_numpy()
        print(
            f"  {col:<8} | MAE={np.abs(err).mean():.3f} | WAPE={safe_wape(float(np.abs(err).sum()), act_sum):.1%} "
            f"| Bias={err.mean():+.3f} | 28d-Total MAE={np.abs(tot_err).mean():.2f} | 28d-Total Bias={tot_err.mean():+.2f}"
        )

    fit_df = df[df["origin_idx"] < 3]
    chk_df = df[df["origin_idx"] >= 3]
    k = fit_scale_factor(
        fit_df["actual"].to_numpy(),
        fit_df["median"].to_numpy(),
        fit_df["q10"].to_numpy(),
        fit_df["q90"].to_numpy(),
    )
    uncal_fit = scaled_coverage(fit_df["actual"].to_numpy(), fit_df["median"].to_numpy(), fit_df["q10"].to_numpy(), fit_df["q90"].to_numpy(), 1.0)
    uncal_chk = scaled_coverage(chk_df["actual"].to_numpy(), chk_df["median"].to_numpy(), chk_df["q10"].to_numpy(), chk_df["q90"].to_numpy(), 1.0)
    cal_chk = scaled_coverage(chk_df["actual"].to_numpy(), chk_df["median"].to_numpy(), chk_df["q10"].to_numpy(), chk_df["q90"].to_numpy(), k)

    print("\nINTERVAL CALIBRATION (fit on first 3 origins, checked on last 2 origins):")
    print(f"  Fitted scale factor k = {k:.3f} (target 80.0% on first 3 origins; uncalibrated={uncal_fit:.1%})")
    print(f"  Last 2 origins coverage: uncalibrated (k=1.0)={uncal_chk:.1%} -> calibrated (k={k:.3f})={cal_chk:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
