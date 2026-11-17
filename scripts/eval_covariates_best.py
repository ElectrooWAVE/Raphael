"""Validation-only covariate evaluation using the best config from reports/experiments.csv.

Compares no-covariates vs with-covariates on 5 rolling 28-day validation origins
(never touches the final 28-day test window), broken down overall and by:
  - Promotion days (is_promotion == 1 vs 0)
  - Event days (calendar event present vs none)
  - High-zero series (>60% zero-sales days vs <=60%)

Output: reports/covariates_best.csv
Run:    .venv\\Scripts\\python.exe scripts/eval_covariates_best.py
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
from rdf.forecaster import DENSE_QUANTILES, load_pipeline

HORIZON = 28
N_ORIGINS = 5
REPORTS_DIR = ROOT / "reports"
EXPERIMENTS_CSV = REPORTS_DIR / "experiments.csv"
EVENT_COLS = ["event_name_1", "event_type_1", "event_name_2", "event_type_2"]
FUTURE_COV_COLS = ["dayofweek", "is_weekend", *EVENT_COLS]


def safe_wape(abs_err_sum: float, actual_sum: float) -> float:
    return float(abs_err_sum / actual_sum) if actual_sum > 0 else float("nan")


def load_best_config() -> tuple[int | None, bool, str]:
    if not EXPERIMENTS_CSV.exists():
        raise FileNotFoundError(
            f"{EXPERIMENTS_CSV} not found. Run `.venv\\Scripts\\python.exe scripts/experiments.py` first."
        )
    df = pd.read_csv(EXPERIMENTS_CSV).sort_values("median_wape", ascending=True)
    best = df.iloc[0]
    ctx_raw = str(best["context_length"])
    ctx = None if ctx_raw == "all" else int(ctx_raw)
    cross = str(best["cross_learning"]).lower() == "true"
    return ctx, cross, str(best["config"])


def load_series_with_covariates() -> dict[str, pd.DataFrame]:
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
        series_map[sid] = s.join(calendar_df, how="left").reset_index().rename(columns={"quantity": "sales"})
    return series_map


def run_validation_origins(
    pipeline,
    series_map: dict[str, pd.DataFrame],
    context_length: int | None,
    cross_learning: bool,
    use_covariates: bool,
) -> pd.DataFrame:
    q_cols = [str(q) for q in DENSE_QUANTILES]
    zero_shares = {sid: float((s["sales"] == 0).mean()) for sid, s in series_map.items()}
    rows: list[dict] = []

    label = "With covariates" if use_covariates else "No covariates"
    for origin_idx in tqdm(range(N_ORIGINS), desc=label, unit="origin"):
        back = (N_ORIGINS - origin_idx) * HORIZON + HORIZON
        ctx_frames, fut_frames = [], []
        meta: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}

        for sid, s in series_map.items():
            start = len(s) - back
            end = start + HORIZON
            train_df = s.iloc[:start]
            fut_slice = s.iloc[start:end]

            meta[sid] = (
                fut_slice["sales"].to_numpy(dtype=np.float64),
                fut_slice["is_promotion"].to_numpy(dtype=np.float64),
                (fut_slice["event_name_1"] != "none").to_numpy(),
            )
            ctx_dict = {
                "item_id": sid,
                "timestamp": train_df["date"].values,
                "target": train_df["sales"].values,
            }
            if use_covariates:
                ctx_dict["is_promotion"] = train_df["is_promotion"].values
                for col in FUTURE_COV_COLS:
                    ctx_dict[col] = train_df[col].values
                fut_frames.append(
                    pd.DataFrame({
                        "item_id": sid,
                        "timestamp": fut_slice["date"].values,
                        **{col: fut_slice[col].values for col in FUTURE_COV_COLS},
                    })
                )
            ctx_frames.append(pd.DataFrame(ctx_dict))

        out = pipeline.predict_df(
            pd.concat(ctx_frames, ignore_index=True),
            future_df=pd.concat(fut_frames, ignore_index=True) if use_covariates else None,
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
            act, promo, has_event = meta[sid]
            med = grp["median"].to_numpy(dtype=np.float64)
            exp = grp["expected"].to_numpy(dtype=np.float64)
            q10 = grp["q10"].to_numpy(dtype=np.float64)
            q90 = grp["q90"].to_numpy(dtype=np.float64)
            hz = zero_shares[sid] > 0.60

            for i in range(HORIZON):
                rows.append({
                    "origin_idx": origin_idx,
                    "series_id": sid,
                    "is_promo": bool(promo[i] > 0),
                    "is_event": bool(has_event[i]),
                    "is_high_zero": hz,
                    "actual": float(act[i]),
                    "median": float(med[i]),
                    "expected": float(exp[i]),
                    "q10": float(q10[i]),
                    "q90": float(q90[i]),
                })

    return pd.DataFrame(rows)


def summarize_group(base: pd.DataFrame, cov: pd.DataFrame, mask: np.ndarray | None, label: str) -> dict:
    b = base if mask is None else base[mask]
    c = cov if mask is None else cov[mask]
    act = b["actual"].to_numpy()
    act_sum = float(act.sum())

    bm = b["median"].to_numpy() - act
    cm = c["median"].to_numpy() - act
    be = b["expected"].to_numpy() - act
    ce = c["expected"].to_numpy() - act

    return {
        "group": label,
        "rows": int(len(b)),
        "base_median_mae": float(np.abs(bm).mean()),
        "cov_median_mae": float(np.abs(cm).mean()),
        "base_median_wape": safe_wape(float(np.abs(bm).sum()), act_sum),
        "cov_median_wape": safe_wape(float(np.abs(cm).sum()), act_sum),
        "base_expected_mae": float(np.abs(be).mean()),
        "cov_expected_mae": float(np.abs(ce).mean()),
        "base_expected_wape": safe_wape(float(np.abs(be).sum()), act_sum),
        "cov_expected_wape": safe_wape(float(np.abs(ce).sum()), act_sum),
    }


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ctx_len, cross_learning, cfg_name = load_best_config()
    print(f"Using best config from {EXPERIMENTS_CSV.name}: {cfg_name} (context_length={ctx_len}, cross_learning={cross_learning})")

    series_map = load_series_with_covariates()
    pipeline, device = load_pipeline()

    base_df = run_validation_origins(pipeline, series_map, ctx_len, cross_learning, use_covariates=False)
    cov_df = run_validation_origins(pipeline, series_map, ctx_len, cross_learning, use_covariates=True)

    summary_rows = [
        summarize_group(base_df, cov_df, None, "Overall"),
        summarize_group(base_df, cov_df, base_df["is_promo"].to_numpy(), "Promotion days"),
        summarize_group(base_df, cov_df, ~base_df["is_promo"].to_numpy(), "Non-promotion days"),
        summarize_group(base_df, cov_df, base_df["is_event"].to_numpy(), "Event days"),
        summarize_group(base_df, cov_df, ~base_df["is_event"].to_numpy(), "Non-event days"),
        summarize_group(base_df, cov_df, base_df["is_high_zero"].to_numpy(), "High-zero series (>60%)"),
        summarize_group(base_df, cov_df, ~base_df["is_high_zero"].to_numpy(), "Other series (<=60%)"),
    ]
    out_df = pd.DataFrame(summary_rows)
    out_df.to_csv(REPORTS_DIR / "covariates_best.csv", index=False)

    print(f"\nCOVARIATES COMPARISON ON VALIDATION (config={cfg_name}, device={device}):")
    for _, r in out_df.iterrows():
        helped = "HELPED" if r["cov_median_wape"] < r["base_median_wape"] else "DID NOT HELP"
        print(
            f"  {r['group']:<24} (n={r['rows']:5d}): "
            f"Med WAPE {r['base_median_wape']:.1%} -> {r['cov_median_wape']:.1%} | "
            f"Exp WAPE {r['base_expected_wape']:.1%} -> {r['cov_expected_wape']:.1%} | "
            f"Med MAE {r['base_median_mae']:.3f} -> {r['cov_median_mae']:.3f} [{helped}]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
