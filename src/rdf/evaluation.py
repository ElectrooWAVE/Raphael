"""Model Evaluation, Error Metrics, and Rolling-Origin Backtesting.

Implements rigorous chronological evaluation without future information leakage.
Supported metrics: MAE, RMSE, WAPE, MASE, Forecast Bias, Pinball Loss, PICP Coverage, Interval Width.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np
import pandas as pd


def compute_metrics(
    actual: Sequence[float],
    predicted_median: Sequence[float],
    q10: Sequence[float] | None = None,
    q90: Sequence[float] | None = None,
    in_sample_actual: Sequence[float] | None = None,
) -> dict[str, float]:
    """Compute standard retail demand forecasting metrics.

    Guards against division-by-zero on zero-demand days.
    """
    y = np.asarray(actual, dtype=float)
    y_hat = np.asarray(predicted_median, dtype=float)

    if len(y) == 0:
        return {}

    abs_err = np.abs(y - y_hat)
    sq_err = (y - y_hat) ** 2

    mae = float(np.mean(abs_err))
    rmse = float(np.sqrt(np.mean(sq_err)))

    sum_y = float(np.sum(y))
    sum_abs_err = float(np.sum(abs_err))
    wape = float(sum_abs_err / sum_y) if sum_y > 1e-8 else 0.0

    # Forecast bias: (sum(y_hat) - sum(y)) / sum(y)
    bias = float((np.sum(y_hat) - sum_y) / sum_y) if sum_y > 1e-8 else float(np.mean(y_hat - y))

    # MASE: scaled by in-sample 1-step naive difference
    mase = 0.0
    if in_sample_actual is not None and len(in_sample_actual) > 1:
        insample = np.asarray(in_sample_actual, dtype=float)
        denom = float(np.mean(np.abs(np.diff(insample))))
        if denom > 1e-8:
            mase = float(mae / denom)
        else:
            mase = float(mae)
    else:
        mase = float(mae)

    result = {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "wape": round(wape, 4),
        "mase": round(mase, 4),
        "bias": round(bias, 4),
    }

    # Probabilistic metrics
    if q10 is not None and q90 is not None:
        low = np.asarray(q10, dtype=float)
        high = np.asarray(q90, dtype=float)

        coverage = float(np.mean((y >= low) & (y <= high)))
        mean_width = float(np.mean(high - low))

        # Pinball loss for Q10, Q50, Q90
        diff_10 = y - low
        diff_50 = y - y_hat
        diff_90 = y - high

        pb_10 = np.mean(np.maximum(0.10 * diff_10, (0.10 - 1.0) * diff_10))
        pb_50 = np.mean(np.maximum(0.50 * diff_50, (0.50 - 1.0) * diff_50))
        pb_90 = np.mean(np.maximum(0.90 * diff_90, (0.90 - 1.0) * diff_90))
        mean_pb = float((pb_10 + pb_50 + pb_90) / 3.0)

        result["coverage_80"] = round(coverage, 4)
        result["mean_interval_width"] = round(mean_width, 4)
        result["pinball_loss"] = round(mean_pb, 4)

    return result


def generate_backtest_cutoffs(
    dates: Sequence[pd.Timestamp],
    horizon: int,
    num_cutoffs: int = 3,
    min_context: int = 30,
) -> list[int]:
    """Generate chronological historical cutoff indices for rolling-origin evaluation."""
    n = len(dates)
    if n < min_context + horizon:
        raise ValueError(
            f"Insufficient history ({n} observations) for context ({min_context}) + horizon ({horizon})."
        )

    # Cutoffs move backwards from (n - horizon)
    max_cutoff = n - horizon
    min_cutoff = min_context

    if max_cutoff <= min_cutoff:
        return [max_cutoff]

    if num_cutoffs <= 1:
        return [max_cutoff]

    step = max(1, (max_cutoff - min_cutoff) // (num_cutoffs - 1))
    cutoffs = []
    curr = min_cutoff
    while curr <= max_cutoff and len(cutoffs) < num_cutoffs:
        cutoffs.append(curr)
        curr += step

    if cutoffs[-1] != max_cutoff:
        cutoffs[-1] = max_cutoff

    return sorted(list(set(cutoffs)))
