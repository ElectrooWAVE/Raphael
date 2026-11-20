"""Seasonal-naive baseline forecasting model.

Serves as the empirical benchmark to evaluate whether Chronos-2 and LightGBM
deliver meaningful improvements over simple seasonality.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def get_seasonal_period(frequency: str = "D") -> int:
    """Return default seasonal lag period based on frequency."""
    freq = (frequency or "D").upper()
    if freq in ("D", "DAILY"):
        return 7  # day-of-week seasonality
    elif freq in ("W", "WEEKLY"):
        return 52
    elif freq in ("M", "MS", "MONTHLY"):
        return 12
    elif freq in ("H", "HOURLY"):
        return 24
    return 7


def forecast_seasonal_naive(
    history_df: pd.DataFrame,
    horizon: int,
    frequency: str = "D",
) -> pd.DataFrame:
    """Generate seasonal naive forecasts for horizon steps."""
    if horizon < 1:
        raise ValueError("Horizon must be at least 1.")

    df = history_df.copy()
    if "timestamp" not in df.columns:
        if "date" in df.columns:
            df["timestamp"] = pd.to_datetime(df["date"])
        else:
            raise ValueError("History DataFrame must contain 'date' or 'timestamp' column.")

    if "target" not in df.columns:
        if "sales" in df.columns:
            df["target"] = pd.to_numeric(df["sales"], errors="coerce")
        else:
            raise ValueError("History DataFrame must contain 'sales' or 'target' column.")

    df = df.dropna(subset=["timestamp", "target"]).sort_values("timestamp").reset_index(drop=True)
    if df.empty:
        raise ValueError("Empty history provided to baseline forecaster.")

    ts_list = list(df["timestamp"])
    targets = list(df["target"].astype(float))
    n = len(targets)

    # Step delta
    if len(ts_list) >= 2:
        step_delta = ts_list[-1] - ts_list[-2]
        if step_delta <= pd.Timedelta(0):
            step_delta = pd.Timedelta(days=1)
    else:
        step_delta = pd.Timedelta(days=1)

    s = get_seasonal_period(frequency)
    if n < s:
        s = 1  # Fallback to naive last value

    # Calculate empirical seasonal absolute error for interval estimation
    residuals = []
    for i in range(s, n):
        residuals.append(abs(targets[i] - targets[i - s]))
    sigma = float(np.median(residuals)) if residuals else 1.0

    forecast_dates: list[pd.Timestamp] = []
    forecast_vals: list[float] = []

    last_ts = ts_list[-1]
    for h in range(1, horizon + 1):
        forecast_dates.append(last_ts + h * step_delta)
        # Seasonal index relative to end of history
        idx = n - s + ((h - 1) % s)
        val = max(0.0, targets[idx])
        forecast_vals.append(val)

    # 80% prediction interval using 1.28 * empirical seasonal error
    q10 = [max(0.0, v - 1.28 * sigma) for v in forecast_vals]
    q90 = [v + 1.28 * sigma for v in forecast_vals]

    return pd.DataFrame({
        "date": forecast_dates,
        "median": forecast_vals,
        "expected": forecast_vals,
        "q10": q10,
        "q50": forecast_vals,
        "q90": q90,
    })
