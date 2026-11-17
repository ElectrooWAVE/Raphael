"""Covariate rolling-origin benchmark for Chronos-2 (mean & q50).

Covariates used:
  - Past-only covariates (in df only): is_promotion (from demand_history.csv)
  - Known-future covariates (in df and future_df): dayofweek, is_weekend,
    event_name_1, event_type_1, event_name_2, event_type_2 (from calendar_events_reference.csv)

Outputs:
  - reports/covariates_metrics.csv
  - Side-by-side table vs reports/zero_shot_metrics.csv (if present)

Run:  .venv\\Scripts\\python.exe scripts/eval_covariates.py
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
from rdf.forecaster import load_pipeline

HORIZON = 28
N_ORIGINS = 5
REPORTS_DIR = ROOT / "reports"
EVENT_COLS = ["event_name_1", "event_type_1", "event_name_2", "event_type_2"]


def safe_wape(abs_err_sum: float, actual_sum: float) -> float:
    return float(abs_err_sum / actual_sum) if actual_sum > 0 else float("nan")


def load_covariate_data() -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    raw = pd.read_csv(
        config.DATA_DIR / "demand_history.csv",
        usecols=["date", "material", "area", "quantity", "is_promotion"],
        parse_dates=["date"],
    )
    raw["series_id"] = raw["material"].astype(str) + " | " + raw["area"].astype(str)
    raw["is_promotion"] = raw["is_promotion"].fillna(0).astype(float)

    cal = pd.read_csv(config.DATA_DIR / "calendar_events_reference.csv", parse_dates=["date"])
    for col in EVENT_COLS:
        cal[col] = cal[col].fillna("none").astype(str)

    all_dates = pd.DataFrame({"date": pd.date_range(raw["date"].min(), raw["date"].max(), freq="D")})
    calendar_df = all_dates.merge(cal, on="date", how="left")
    for col in EVENT_COLS:
        calendar_df[col] = calendar_df[col].fillna("none").astype(str)
    calendar_df["dayofweek"] = calendar_df["date"].dt.dayofweek.astype(int)
    calendar_df["is_weekend"] = (calendar_df["dayofweek"] >= 5).astype(int)
    calendar_df = calendar_df.set_index("date")

    series_map: dict[str, pd.DataFrame] = {}
    for sid, grp in raw.groupby("series_id", sort=True):
        s = grp[["date", "quantity", "is_promotion"]].drop_duplicates("date", keep="last").set_index("date").sort_index()
        s = s.reindex(calendar_df.index)
        s.index.name = "date"
        s["is_promotion"] = s["is_promotion"].fillna(0.0)
        joined = s.join(calendar_df, how="left").reset_index().rename(columns={"quantity": "sales"})
        series_map[sid] = joined

    return series_map, calendar_df


def build_origin_with_covariates(
    series_map: dict[str, pd.DataFrame], origin_k: int
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, np.ndarray]]:
    ctx_frames: list[pd.DataFrame] = []
    fut_frames: list[pd.DataFrame] = []
    actuals: dict[str, np.ndarray] = {}
    future_cov_cols = ["dayofweek", "is_weekend", *EVENT_COLS]

    for sid, s in series_map.items():
        n = len(s)
        start = n - origin_k * HORIZON
        end = n - (origin_k - 1) * HORIZON
        train_df = s.iloc[:start]
        fut_slice = s.iloc[start:end]
        actuals[sid] = fut_slice["sales"].to_numpy(dtype=np.float64)

        ctx_frames.append(
            pd.DataFrame({
                "item_id": sid,
                "timestamp": train_df["date"].values,
                "target": train_df["sales"].values,
                "is_promotion": train_df["is_promotion"].values,
                **{c: train_df[c].values for c in future_cov_cols},
            })
        )
        fut_frames.append(
            pd.DataFrame({
                "item_id": sid,
                "timestamp": fut_slice["date"].values,
                **{c: fut_slice[c].values for c in future_cov_cols},
            })
        )

    return pd.concat(ctx_frames, ignore_index=True), pd.concat(fut_frames, ignore_index=True), actuals


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    print("Covariate configuration:")
    print("  - Past-only covariates (df only):       is_promotion (demand_history.csv)")
    print(f"  - Known-future covariates (df+future): dayofweek, is_weekend, {', '.join(EVENT_COLS)}")

    series_map, _ = load_covariate_data()
    pipeline, device = load_pipeline()
    all_rows: list[dict] = []

    origins = list(range(N_ORIGINS, 0, -1))
    for k in tqdm(origins, desc="Rolling origins (covariates)", unit="origin"):
        ctx_df, fut_df, actuals = build_origin_with_covariates(series_map, k)
        out = pipeline.predict_df(
            ctx_df,
            future_df=fut_df,
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
            actual = actuals[sid]
            preds = grp["predictions"].to_numpy(dtype=np.float64)
            q50 = grp["0.5"].to_numpy(dtype=np.float64)
            q10 = grp["0.1"].to_numpy(dtype=np.float64)
            q90 = grp["0.9"].to_numpy(dtype=np.float64)

            for i in range(HORIZON):
                all_rows.append({
                    "origin_k": k,
                    "series_id": sid,
                    "actual": float(actual[i]),
                    "cov_mean": float(preds[i]),
                    "cov_q50": float(q50[i]),
                    "q10": float(q10[i]),
                    "q90": float(q90[i]),
                })

    raw_df = pd.DataFrame(all_rows)
    per_series = []
    for sid, g in raw_df.groupby("series_id", sort=True):
        act = g["actual"].to_numpy()
        act_sum = float(np.nansum(act))
        m_err = g["cov_mean"].to_numpy() - act
        q_err = g["cov_q50"].to_numpy() - act
        per_series.append({
            "series_id": sid,
            "total_actual": act_sum,
            "cov_mean_mae": float(np.nanmean(np.abs(m_err))),
            "cov_mean_wape": safe_wape(float(np.nansum(np.abs(m_err))), act_sum),
            "cov_mean_bias": float(np.nanmean(m_err)),
            "cov_q50_mae": float(np.nanmean(np.abs(q_err))),
            "cov_q50_wape": safe_wape(float(np.nansum(np.abs(q_err))), act_sum),
            "cov_q50_bias": float(np.nanmean(q_err)),
            "cov_cov80": float(np.nanmean((act >= g["q10"].to_numpy()) & (act <= g["q90"].to_numpy()))),
        })
    metrics_df = pd.DataFrame(per_series)
    metrics_df.to_csv(REPORTS_DIR / "covariates_metrics.csv", index=False)

    act = raw_df["actual"].to_numpy()
    act_sum = float(np.nansum(act))
    cm_err = raw_df["cov_mean"].to_numpy() - act
    cq_err = raw_df["cov_q50"].to_numpy() - act
    cov80 = float(np.nanmean((act >= raw_df["q10"].to_numpy()) & (act <= raw_df["q90"].to_numpy())))

    print(f"\nWith-Covariates Overall (device={device}):")
    print(f"  Mean: MAE={np.nanmean(np.abs(cm_err)):.3f} | WAPE={safe_wape(float(np.nansum(np.abs(cm_err))), act_sum):.1%} | Bias={np.nanmean(cm_err):+.3f} | Cov80={cov80:.1%}")
    print(f"  Q50:  MAE={np.nanmean(np.abs(cq_err)):.3f} | WAPE={safe_wape(float(np.nansum(np.abs(cq_err))), act_sum):.1%} | Bias={np.nanmean(cq_err):+.3f} | Cov80={cov80:.1%}")

    zs_path = REPORTS_DIR / "zero_shot_metrics.csv"
    if zs_path.exists():
        zs = pd.read_csv(zs_path)
        merged = zs.merge(metrics_df, on="series_id", how="inner")
        print("\nZero-Shot vs With-Covariates (mean across 75 series):")
        print(f"  Mean MAE:  {merged['chronos2_mean_mae'].mean():.3f} -> {merged['cov_mean_mae'].mean():.3f}")
        print(f"  Mean WAPE: {merged['chronos2_mean_wape'].mean():.1%} -> {merged['cov_mean_wape'].mean():.1%}")
        print(f"  Q50 MAE:   {merged['chronos2_q50_mae'].mean():.3f} -> {merged['cov_q50_mae'].mean():.3f}")
        print(f"  Q50 WAPE:  {merged['chronos2_q50_wape'].mean():.1%} -> {merged['cov_q50_wape'].mean():.1%}")
        print(f"  Cov80:     {merged['chronos2_cov80'].mean():.1%} -> {merged['cov_cov80'].mean():.1%}")
    else:
        print("\nNote: reports/zero_shot_metrics.csv not found; run scripts/evaluate.py for side-by-side comparison.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
