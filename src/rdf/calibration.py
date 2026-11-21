"""Validation-only interval calibration and per-series forecast-error statistics.

Never touches the final `horizon`-day test window: all rolling backtest cutoffs
are drawn from `history_df.iloc[:-horizon]`. Reuses `compute_metrics` and
`generate_backtest_cutoffs` from `rdf.evaluation`.
"""
from __future__ import annotations

import json
import math
from typing import Any, Sequence

import numpy as np
import pandas as pd

from .baseline import forecast_seasonal_naive
from .db import get_db, init_db, now_iso
from .evaluation import compute_metrics, generate_backtest_cutoffs
from .forecaster import forecast as forecast_chronos, load_pipeline
from .lgbm_forecaster import list_trained_models, load_trained_forecaster


def fit_interval_scale(
    actual: Sequence[float],
    median: Sequence[float],
    q10: Sequence[float],
    q90: Sequence[float],
    target_cov: float = 0.80,
    k_min: float = 0.25,
    k_max: float = 4.0,
) -> float:
    """Find scale factor k so [med - k*(med-q10), med + k*(q90-med)] covers ~target_cov."""
    y = np.asarray(actual, dtype=float)
    med = np.asarray(median, dtype=float)
    low = np.asarray(q10, dtype=float)
    high = np.asarray(q90, dtype=float)
    if len(y) == 0:
        return 1.0

    def cov_at(k: float) -> float:
        lo = np.clip(med - k * np.maximum(0.0, med - low), 0.0, None)
        hi = np.maximum(med, med + k * np.maximum(0.0, high - med))
        return float(np.mean((y >= lo) & (y <= hi)))

    if cov_at(k_min) >= target_cov:
        return k_min
    if cov_at(k_max) < target_cov:
        return k_max

    lo_k, hi_k = k_min, k_max
    for _ in range(40):
        mid = 0.5 * (lo_k + hi_k)
        if cov_at(mid) < target_cov:
            lo_k = mid
        else:
            hi_k = mid
    return round(hi_k, 4)


def apply_interval_calibration(
    median: Sequence[float],
    q10: Sequence[float],
    q90: Sequence[float],
    scale_k: float,
) -> tuple[list[float], list[float]]:
    """Scale [q10, q90] around median by `scale_k` and clip at 0."""
    k = float(scale_k)
    cal_q10: list[float] = []
    cal_q90: list[float] = []
    for m, l, h in zip(median, q10, q90):
        m_f, l_f, h_f = float(m), float(l), float(h)
        lo = max(0.0, m_f - k * max(0.0, m_f - l_f))
        hi = max(m_f, m_f + k * max(0.0, h_f - m_f))
        cal_q10.append(lo)
        cal_q90.append(hi)
    return cal_q10, cal_q90


def get_series_calibration(
    series_id: str,
    model_type: str = "chronos",
    dataset_id: str = "retail-demand-m5",
) -> dict[str, Any] | None:
    """Fetch stored calibration parameters and error statistics for a series."""
    init_db()
    mt = (model_type or "chronos").lower().strip()
    if mt in ("custom", "custom_model"):
        mt = "lightgbm"
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM series_calibration WHERE series_id = ? AND model_type = ? AND dataset_id = ?",
            (series_id, mt, dataset_id),
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["calibrated"] = True
    return d


def calibrate_series_validation(
    history_df: pd.DataFrame,
    series_id: str,
    model_type: str = "chronos",
    dataset_id: str = "retail-demand-m5",
    horizon: int = 28,
    num_cutoffs: int = 3,
    chronos_pipeline_tuple: tuple[Any, str] | None = None,
) -> dict[str, Any]:
    """Run rolling validation backtests (excluding final `horizon` test days) and store calibration."""
    init_db()
    df = history_df.sort_values("date").reset_index(drop=True)
    if len(df) <= horizon + 30 + horizon:
        raise ValueError(
            f"Series '{series_id}' has {len(df)} rows; need > {2 * horizon + 30} rows for validation-only calibration."
        )

    # Strictly exclude the final `horizon` days (test window)
    val_df = df.iloc[:-horizon].copy().reset_index(drop=True)
    cutoffs = generate_backtest_cutoffs(list(val_df["date"]), horizon=horizon, num_cutoffs=num_cutoffs, min_context=30)

    mt = (model_type or "chronos").lower().strip()
    if mt in ("custom", "custom_model"):
        mt = "lightgbm"

    pipeline = None
    lgbm_forecaster = None
    if mt == "chronos":
        pipeline, _ = chronos_pipeline_tuple if chronos_pipeline_tuple is not None else load_pipeline()
    elif mt == "lightgbm":
        models = list_trained_models(dataset_id) or list_trained_models()
        if not models:
            raise ValueError("No trained Custom LightGBM model found for calibration.")
        lgbm_forecaster = load_trained_forecaster(models[0]["model_id"])
    elif mt != "baseline":
        raise ValueError(f"Unsupported model_type '{model_type}' for calibration.")

    all_act: list[float] = []
    all_med: list[float] = []
    all_exp: list[float] = []
    all_q10: list[float] = []
    all_q90: list[float] = []
    cutoff_errors: list[list[float]] = []

    for c_idx in cutoffs:
        ctx = val_df.iloc[:c_idx]
        target_slice = val_df.iloc[c_idx : c_idx + horizon]
        if len(target_slice) < horizon:
            continue

        if mt == "chronos":
            fc = forecast_chronos(pipeline, ctx, horizon, series_id)
        elif mt == "lightgbm":
            fc = lgbm_forecaster.predict_recursive(ctx, horizon, series_id)
        else:
            fc = forecast_seasonal_naive(ctx, horizon, frequency="D")

        act_vals = [float(v) for v in target_slice["sales"].to_numpy()]
        exp_col = fc["expected"] if "expected" in fc.columns else fc["median"]
        exp_vals = [float(v) for v in exp_col.to_numpy()]

        all_act.extend(act_vals)
        all_med.extend(float(v) for v in fc["median"].to_numpy())
        all_exp.extend(exp_vals)
        all_q10.extend(float(v) for v in fc["q10"].to_numpy())
        all_q90.extend(float(v) for v in fc["q90"].to_numpy())
        cutoff_errors.append([a - e for a, e in zip(act_vals, exp_vals)])

    metrics = compute_metrics(
        actual=all_act,
        predicted_median=all_med,
        q10=all_q10,
        q90=all_q90,
        in_sample_actual=list(val_df["sales"].dropna()),
    )

    scale_k = fit_interval_scale(all_act, all_med, all_q10, all_q90, target_cov=0.80)
    cal_q10, cal_q90 = apply_interval_calibration(all_med, all_q10, all_q90, scale_k)

    y_arr = np.asarray(all_act, dtype=float)
    exp_arr = np.asarray(all_exp, dtype=float)
    cal_lo = np.asarray(cal_q10, dtype=float)
    cal_hi = np.asarray(cal_q90, dtype=float)

    raw_cov = float(metrics.get("coverage_80", 0.0))
    cal_cov = round(float(np.mean((y_arr >= cal_lo) & (y_arr <= cal_hi))), 4)
    sigma_d = round(float(np.std(y_arr - exp_arr, ddof=1)) if len(y_arr) > 1 else 0.0, 4)
    val_end = pd.Timestamp(val_df["date"].iloc[-1]).strftime("%Y-%m-%d")
    updated = now_iso()
    val_errors_json = json.dumps(cutoff_errors)

    with get_db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO series_calibration (
                series_id, model_type, dataset_id, horizon, scale_k,
                raw_coverage_80, calibrated_coverage_80, sigma_d,
                mae, wape, bias, sample_points, val_window_end, val_errors_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                series_id,
                mt,
                dataset_id,
                horizon,
                scale_k,
                raw_cov,
                cal_cov,
                sigma_d,
                metrics.get("mae"),
                metrics.get("wape"),
                metrics.get("bias"),
                len(all_act),
                val_end,
                val_errors_json,
                updated,
            ),
        )

    return {
        "calibrated": True,
        "series_id": series_id,
        "model_type": mt,
        "dataset_id": dataset_id,
        "horizon": horizon,
        "scale_k": scale_k,
        "raw_coverage_80": raw_cov,
        "calibrated_coverage_80": cal_cov,
        "sigma_d": sigma_d,
        "mae": metrics.get("mae"),
        "wape": metrics.get("wape"),
        "bias": metrics.get("bias"),
        "sample_points": len(all_act),
        "val_window_end": val_end,
        "val_errors_json": val_errors_json,
        "updated_at": updated,
    }


def compute_lead_time_error_std(
    calibration: dict[str, Any] | None,
    lead_time_days: float,
) -> tuple[float, str]:
    """Compute sigma_D over a lead-time window from Stage 0 validation backtest errors.

    Sums contiguous daily errors over windows of continuous length `lead_time_days`
    across validation cutoffs. Falls back to `sigma_d * sqrt(L)` only if validation
    error arrays are unavailable or shorter than `lead_time_days`.
    """
    L = max(0.0, float(lead_time_days))
    if L == 0.0 or not calibration:
        return 0.0, "none"

    raw_json = calibration.get("val_errors_json")
    if raw_json:
        try:
            cutoffs = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
        except Exception:
            cutoffs = []
        full_days = int(math.floor(L))
        frac = L - full_days
        need_len = full_days + (1 if frac > 1e-9 else 0)
        window_sums: list[float] = []
        for errs in cutoffs or []:
            if not isinstance(errs, list) or len(errs) < need_len:
                continue
            for start in range(0, len(errs) - need_len + 1):
                total = sum(float(errs[start + j]) for j in range(full_days))
                if frac > 1e-9:
                    total += frac * float(errs[start + full_days])
                window_sums.append(total)
        if len(window_sums) >= 2:
            return float(np.std(np.asarray(window_sums, dtype=float), ddof=1)), "validation_windows"

    sigma_d = calibration.get("sigma_d")
    if sigma_d is not None:
        return float(sigma_d) * math.sqrt(L), "sigma_d_sqrt_L"
    return 0.0, "none"
