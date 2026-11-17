"""Zero-shot rolling-origin benchmark for Chronos-2 (mean & q50) vs baselines.

Time-based split per series:
  - test       = last 28 days
  - validation = 28 days before test
  - train      = everything earlier

Rolling origins: 5 origins spaced 28 days apart, ending at the test window.
Outputs:
  - reports/zero_shot_metrics.csv
  - reports/zero_shot_summary.txt

Run:  .venv\\Scripts\\python.exe scripts/evaluate.py
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

from rdf import config
from rdf.data_loader import get_series, list_series, load_sales
from rdf.forecaster import load_pipeline

HORIZON = 28
N_ORIGINS = 5
REPORTS_DIR = ROOT / "reports"


def safe_wape(abs_err_sum: float, actual_sum: float) -> float:
    return float(abs_err_sum / actual_sum) if actual_sum > 0 else float("nan")


def zero_bucket(zero_share: float) -> str:
    if zero_share < 0.20:
        return "<20%"
    if zero_share <= 0.60:
        return "20-60%"
    return ">60%"


def baseline_forecasts(train_sales: np.ndarray, horizon: int) -> tuple[np.ndarray, np.ndarray]:
    tail28 = train_sales[-28:]
    mean_val = float(np.nanmean(tail28)) if np.isfinite(tail28).any() else 0.0
    mean_pred = np.full(horizon, max(0.0, mean_val), dtype=np.float64)

    last7 = np.nan_to_num(train_sales[-7:], nan=mean_val)
    snaive_pred = np.array([max(0.0, float(last7[h % len(last7)])) for h in range(horizon)], dtype=np.float64)
    return mean_pred, snaive_pred


def build_origin_frames(
    series_map: dict[str, pd.DataFrame], origin_k: int
) -> tuple[pd.DataFrame, dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]]:
    """origin_k=1 is the test window (last 28d), origin_k=2 is validation, etc."""
    ctx_frames: list[pd.DataFrame] = []
    targets_and_baselines: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}

    for sid, s in series_map.items():
        n = len(s)
        start = n - origin_k * HORIZON
        end = n - (origin_k - 1) * HORIZON
        if start < 30:
            raise ValueError(f"Series '{sid}' too short ({n} days) for origin k={origin_k}")

        train_df = s.iloc[:start]
        actual = s.iloc[start:end]["sales"].to_numpy(dtype=np.float64)
        mean_pred, snaive_pred = baseline_forecasts(train_df["sales"].to_numpy(dtype=np.float64), HORIZON)

        ctx_frames.append(
            pd.DataFrame({
                "item_id": sid,
                "timestamp": train_df["date"].values,
                "target": train_df["sales"].values,
            })
        )
        targets_and_baselines[sid] = (actual, mean_pred, snaive_pred)

    return pd.concat(ctx_frames, ignore_index=True), targets_and_baselines


def compute_metrics(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    grouped = []
    for sid, g in df.groupby("series_id", sort=True):
        actual = g["actual"].to_numpy()
        c_mean = g["chronos2_mean"].to_numpy()
        c_q50 = g["chronos2_q50"].to_numpy()
        q10 = g["q10"].to_numpy()
        q90 = g["q90"].to_numpy()
        m_pred = g["mean28"].to_numpy()
        s_pred = g["snaive"].to_numpy()

        actual_sum = float(np.nansum(actual))
        cm_err = c_mean - actual
        cq_err = c_q50 - actual
        m_err = m_pred - actual
        s_err = s_pred - actual

        grouped.append({
            "series_id": sid,
            "zero_share": float(g["zero_share"].iloc[0]),
            "zero_bucket": str(g["zero_bucket"].iloc[0]),
            "total_actual": actual_sum,
            "chronos2_mean_mae": float(np.nanmean(np.abs(cm_err))),
            "chronos2_mean_wape": safe_wape(float(np.nansum(np.abs(cm_err))), actual_sum),
            "chronos2_mean_bias": float(np.nanmean(cm_err)),
            "chronos2_q50_mae": float(np.nanmean(np.abs(cq_err))),
            "chronos2_q50_wape": safe_wape(float(np.nansum(np.abs(cq_err))), actual_sum),
            "chronos2_q50_bias": float(np.nanmean(cq_err)),
            "chronos2_cov80": float(np.nanmean((actual >= q10) & (actual <= q90))),
            "mean28_mae": float(np.nanmean(np.abs(m_err))),
            "mean28_wape": safe_wape(float(np.nansum(np.abs(m_err))), actual_sum),
            "mean28_bias": float(np.nanmean(m_err)),
            "snaive_mae": float(np.nanmean(np.abs(s_err))),
            "snaive_wape": safe_wape(float(np.nansum(np.abs(s_err))), actual_sum),
            "snaive_bias": float(np.nanmean(s_err)),
        })
    return pd.DataFrame(grouped)


def format_summary(raw_df: pd.DataFrame, per_series: pd.DataFrame, device: str) -> str:
    actual = raw_df["actual"].to_numpy()
    actual_sum = float(np.nansum(actual))

    def overall_row(name: str, col: str, cov_col: bool = False) -> str:
        err = raw_df[col].to_numpy() - actual
        mae = float(np.nanmean(np.abs(err)))
        wape = safe_wape(float(np.nansum(np.abs(err))), actual_sum)
        bias = float(np.nanmean(err))
        cov = (
            f"{float(np.nanmean((actual >= raw_df['q10'].to_numpy()) & (actual <= raw_df['q90'].to_numpy()))):.1%}"
            if cov_col
            else "n/a"
        )
        return f"{name:<20} | MAE={mae:6.3f} | WAPE={wape:6.1%} | Bias={bias:+7.3f} | Cov80={cov}"

    lines = [
        f"Chronos-2 Zero-Shot Rolling Evaluation ({N_ORIGINS} origins x {HORIZON} days, {len(per_series)} series, device={device})",
        "=" * 90,
        "OVERALL",
        overall_row("Chronos-2 (mean)", "chronos2_mean", cov_col=True),
        overall_row("Chronos-2 (q50)", "chronos2_q50", cov_col=True),
        overall_row("28-day mean", "mean28"),
        overall_row("Seasonal naive", "snaive"),
        "",
        "TOP 10 WORST SERIES BY CHRONOS-2 (mean) WAPE",
    ]

    worst = per_series.sort_values("chronos2_mean_wape", ascending=False, na_position="last").head(10)
    for _, r in worst.iterrows():
        w_str = f"{r['chronos2_mean_wape']:.1%}" if np.isfinite(r["chronos2_mean_wape"]) else "n/a"
        lines.append(
            f"  {r['series_id']:<38} | WAPE={w_str:>6} | MAE={r['chronos2_mean_mae']:6.3f} "
            f"| Bias={r['chronos2_mean_bias']:+7.3f} | Cov80={r['chronos2_cov80']:.1%} | Zeros={r['zero_share']:.1%}"
        )

    lines.append("")
    lines.append("ERROR BY ZERO-SALES SHARE")
    for bucket in ("<20%", "20-60%", ">60%"):
        sub = raw_df[raw_df["zero_bucket"] == bucket]
        if sub.empty:
            lines.append(f"  {bucket:<6} (0 series): no data")
            continue
        n_ser = sub["series_id"].nunique()
        sub_act = sub["actual"].to_numpy()
        sub_sum = float(np.nansum(sub_act))
        cm_err = sub["chronos2_mean"].to_numpy() - sub_act
        cq_err = sub["chronos2_q50"].to_numpy() - sub_act
        m_err = sub["mean28"].to_numpy() - sub_act
        s_err = sub["snaive"].to_numpy() - sub_act
        c_cov = float(np.nanmean((sub_act >= sub["q10"].to_numpy()) & (sub_act <= sub["q90"].to_numpy())))
        lines.append(
            f"  {bucket:<6} ({n_ser:2d} series): "
            f"Mean MAE={np.nanmean(np.abs(cm_err)):6.3f} WAPE={safe_wape(float(np.nansum(np.abs(cm_err))), sub_sum):6.1%} | "
            f"Q50 MAE={np.nanmean(np.abs(cq_err)):6.3f} WAPE={safe_wape(float(np.nansum(np.abs(cq_err))), sub_sum):6.1%} | "
            f"Cov80={c_cov:5.1%} | Mean28 MAE={np.nanmean(np.abs(m_err)):6.3f} | SNaive MAE={np.nanmean(np.abs(s_err)):6.3f}"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    sales = load_sales()
    sids = list_series(sales)
    series_map = {sid: get_series(sales, sid) for sid in sids}
    zero_shares = {sid: float((s["sales"] == 0).mean()) for sid, s in series_map.items()}

    pipeline, device = load_pipeline()
    all_rows: list[dict] = []

    origins = list(range(N_ORIGINS, 0, -1))
    for k in tqdm(origins, desc="Rolling origins", unit="origin"):
        ctx_df, targets = build_origin_frames(series_map, k)
        out = pipeline.predict_df(
            ctx_df,
            id_column="item_id",
            timestamp_column="timestamp",
            target="target",
            prediction_length=HORIZON,
            quantile_levels=config.QUANTILES,
            freq="D",
        )
        for col in ("predictions", "0.1", "0.5", "0.9"):
            out[col] = out[col].clip(lower=0)

        for sid, grp in out.groupby("item_id", sort=False):
            grp = grp.sort_values("timestamp")
            actual, mean_pred, snaive_pred = targets[sid]
            preds = grp["predictions"].to_numpy(dtype=np.float64)
            q50 = grp["0.5"].to_numpy(dtype=np.float64)
            q10 = grp["0.1"].to_numpy(dtype=np.float64)
            q90 = grp["0.9"].to_numpy(dtype=np.float64)
            z_share = zero_shares[sid]
            z_buck = zero_bucket(z_share)

            for i in range(HORIZON):
                all_rows.append({
                    "origin_k": k,
                    "series_id": sid,
                    "zero_share": z_share,
                    "zero_bucket": z_buck,
                    "actual": float(actual[i]),
                    "chronos2_mean": float(preds[i]),
                    "chronos2_q50": float(q50[i]),
                    "q10": float(q10[i]),
                    "q90": float(q90[i]),
                    "mean28": float(mean_pred[i]),
                    "snaive": float(snaive_pred[i]),
                })

    raw_df = pd.DataFrame(all_rows)
    per_series = compute_metrics(all_rows)
    per_series.to_csv(REPORTS_DIR / "zero_shot_metrics.csv", index=False)

    summary_text = format_summary(raw_df, per_series, device)
    (REPORTS_DIR / "zero_shot_summary.txt").write_text(summary_text, encoding="utf-8")
    print("\n" + summary_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
