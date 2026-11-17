"""Single-run TEST window final report (last 28 days). Refuses to run twice.

Reads validation-selected settings from reports/experiments.csv (and
reports/covariates_best.csv if present), evaluates the chosen pipeline vs
default zero-shot Chronos-2 and baselines on [-28:], and writes:
  - reports/final_report.txt
  - reports/final_report.lock

Run:  .venv\\Scripts\\python.exe scripts/final_report.py
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for p in (SRC, SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import numpy as np
import pandas as pd

from eval_covariates_best import FUTURE_COV_COLS, load_best_config, load_series_with_covariates, safe_wape
from evaluate import baseline_forecasts
from rdf.forecaster import DENSE_QUANTILES, load_pipeline

HORIZON = 28
REPORTS_DIR = ROOT / "reports"
REPORT_TXT = REPORTS_DIR / "final_report.txt"
LOCK_FILE = REPORTS_DIR / "final_report.lock"
COV_BEST_CSV = REPORTS_DIR / "covariates_best.csv"


def should_use_covariates() -> bool:
    if not COV_BEST_CSV.exists():
        return False
    df = pd.read_csv(COV_BEST_CSV)
    overall = df[df["group"] == "Overall"]
    if overall.empty:
        return False
    r = overall.iloc[0]
    return bool(r["cov_median_wape"] < r["base_median_wape"])


def predict_test_window(
    pipeline,
    series_map: dict[str, pd.DataFrame],
    context_length: int | None,
    cross_learning: bool,
    use_covariates: bool,
) -> pd.DataFrame:
    q_cols = [str(q) for q in DENSE_QUANTILES]
    ctx_frames, fut_frames = [], []
    meta: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}

    for sid, s in series_map.items():
        train_df = s.iloc[:-HORIZON]
        test_df = s.iloc[-HORIZON:]
        mean_b, snaive_b = baseline_forecasts(train_df["sales"].to_numpy(dtype=np.float64), HORIZON)
        meta[sid] = (test_df["sales"].to_numpy(dtype=np.float64), mean_b, snaive_b)

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
                    "timestamp": test_df["date"].values,
                    **{col: test_df[col].values for col in FUTURE_COV_COLS},
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

    rows = []
    for sid, grp in out.groupby("item_id", sort=True):
        grp = grp.sort_values("timestamp")
        act, mean_b, snaive_b = meta[sid]
        med = grp["median"].to_numpy(dtype=np.float64)
        exp = grp["expected"].to_numpy(dtype=np.float64)
        q10 = grp["q10"].to_numpy(dtype=np.float64)
        q90 = grp["q90"].to_numpy(dtype=np.float64)
        for i in range(HORIZON):
            rows.append({
                "series_id": sid,
                "actual": float(act[i]),
                "median": float(med[i]),
                "expected": float(exp[i]),
                "q10": float(q10[i]),
                "q90": float(q90[i]),
                "mean28": float(mean_b[i]),
                "snaive": float(snaive_b[i]),
            })
    return pd.DataFrame(rows)


def summary_line(name: str, act: np.ndarray, pred: np.ndarray, q10: np.ndarray | None = None, q90: np.ndarray | None = None, tot_mae: float | None = None) -> str:
    err = pred - act
    mae = float(np.abs(err).mean())
    wape = safe_wape(float(np.abs(err).sum()), float(act.sum()))
    bias = float(err.mean())
    cov = f"{float(np.mean((act >= q10) & (act <= q90))):.1%}" if q10 is not None and q90 is not None else "n/a"
    tot_str = f"{tot_mae:6.2f}" if tot_mae is not None else "   n/a"
    return f"{name:<26} | MAE={mae:6.3f} | WAPE={wape:6.1%} | Bias={bias:+7.3f} | Cov80={cov:>5} | 28d-TotMAE={tot_str}"


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        print(f"Refusing to run twice: lock file already exists at {LOCK_FILE}", file=sys.stderr)
        return 1

    ctx_len, cross_learning, cfg_name = load_best_config()
    use_cov = should_use_covariates()
    series_map = load_series_with_covariates()
    pipeline, device = load_pipeline()

    chosen_df = predict_test_window(pipeline, series_map, ctx_len, cross_learning, use_cov)
    zs_df = predict_test_window(pipeline, series_map, None, False, False)

    act = chosen_df["actual"].to_numpy()
    ch_tot = chosen_df.groupby("series_id", as_index=False)[["actual", "median", "expected", "mean28", "snaive"]].sum()
    zs_tot = zs_df.groupby("series_id", as_index=False)[["actual", "median", "expected"]].sum()

    lines = [
        f"FINAL TEST WINDOW REPORT (last {HORIZON} days, {chosen_df['series_id'].nunique()} series, device={device})",
        f"Chosen pipeline: {cfg_name} | covariates={use_cov}",
        "=" * 96,
        "OVERALL",
        summary_line("Chosen (median)", act, chosen_df["median"].to_numpy(), chosen_df["q10"].to_numpy(), chosen_df["q90"].to_numpy(), float(np.abs(ch_tot["median"] - ch_tot["actual"]).mean())),
        summary_line("Chosen (expected)", act, chosen_df["expected"].to_numpy(), chosen_df["q10"].to_numpy(), chosen_df["q90"].to_numpy(), float(np.abs(ch_tot["expected"] - ch_tot["actual"]).mean())),
        summary_line("Zero-Shot (median)", act, zs_df["median"].to_numpy(), zs_df["q10"].to_numpy(), zs_df["q90"].to_numpy(), float(np.abs(zs_tot["median"] - zs_tot["actual"]).mean())),
        summary_line("Zero-Shot (expected)", act, zs_df["expected"].to_numpy(), zs_df["q10"].to_numpy(), zs_df["q90"].to_numpy(), float(np.abs(zs_tot["expected"] - zs_tot["actual"]).mean())),
        summary_line("28-day mean baseline", act, chosen_df["mean28"].to_numpy(), None, None, float(np.abs(ch_tot["mean28"] - ch_tot["actual"]).mean())),
        summary_line("Seasonal naive baseline", act, chosen_df["snaive"].to_numpy(), None, None, float(np.abs(ch_tot["snaive"] - ch_tot["actual"]).mean())),
        "",
        "PER-SERIES (Chosen expected vs Zero-Shot expected)",
    ]

    for sid, g_ch in chosen_df.groupby("series_id", sort=True):
        g_zs = zs_df[zs_df["series_id"] == sid]
        s_act = g_ch["actual"].to_numpy()
        s_sum = float(s_act.sum())
        ch_mae = float(np.abs(g_ch["expected"].to_numpy() - s_act).mean())
        zs_mae = float(np.abs(g_zs["expected"].to_numpy() - s_act).mean())
        ch_wape = safe_wape(float(np.abs(g_ch["expected"].to_numpy() - s_act).sum()), s_sum)
        ch_bias = float((g_ch["expected"].to_numpy() - s_act).mean())
        ch_cov = float(np.mean((s_act >= g_ch["q10"].to_numpy()) & (s_act <= g_ch["q90"].to_numpy())))
        tot_err = float(g_ch["expected"].sum() - s_sum)
        w_str = f"{ch_wape:.1%}" if np.isfinite(ch_wape) else "n/a"
        lines.append(
            f"  {sid:<38} | MAE={ch_mae:5.2f} (ZS {zs_mae:5.2f}) | WAPE={w_str:>6} | Bias={ch_bias:+6.2f} | Cov80={ch_cov:5.1%} | TotErr={tot_err:+7.1f}"
        )

    report_text = "\n".join(lines) + "\n"
    REPORT_TXT.write_text(report_text, encoding="utf-8")
    LOCK_FILE.write_text(f"locked_at={dt.datetime.now().isoformat()}\nconfig={cfg_name}\ncovariates={use_cov}\n", encoding="utf-8")
    print("\n" + report_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
