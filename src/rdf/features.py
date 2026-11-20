"""Frequency-aware feature engineering for recursive time-series forecasting.

Strictly avoids data leakage: all lag and rolling calculations strictly shift past values.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def get_default_feature_config(frequency: str = "D") -> dict[str, Any]:
    """Return sensible default lag and rolling configurations for a given frequency."""
    freq = (frequency or "D").upper()
    if freq in ("D", "DAILY"):
        return {
            "lags": [1, 2, 3, 7, 14, 28, 56],
            "rolling_means": [7, 14, 28],
            "rolling_stds": [7, 28],
            "calendar": ["dayofweek", "dayofmonth", "weekofyear", "month", "quarter", "is_weekend"],
        }
    elif freq in ("W", "WEEKLY", "W-SUN", "W-MON"):
        return {
            "lags": [1, 2, 4, 8, 12],
            "rolling_means": [4, 8, 12],
            "rolling_stds": [4, 12],
            "calendar": ["weekofyear", "month", "quarter", "year"],
        }
    elif freq in ("M", "MS", "MONTHLY"):
        return {
            "lags": [1, 2, 3, 6, 12],
            "rolling_means": [3, 6, 12],
            "rolling_stds": [6, 12],
            "calendar": ["month", "quarter", "year"],
        }
    elif freq in ("H", "HOURLY"):
        return {
            "lags": [1, 2, 24, 48, 168],
            "rolling_means": [24, 168],
            "rolling_stds": [24, 168],
            "calendar": ["hour", "dayofweek", "dayofmonth", "month", "is_weekend"],
        }
    else:  # Generic default
        return {
            "lags": [1, 2, 3, 7, 14],
            "rolling_means": [7, 14],
            "rolling_stds": [7],
            "calendar": ["dayofweek", "month"],
        }


def extract_calendar_features(dt_series: pd.Series, calendar_cols: list[str]) -> pd.DataFrame:
    """Extract standard calendar features from datetime series."""
    df_cal = pd.DataFrame(index=dt_series.index)
    dt = pd.to_datetime(dt_series)

    dow = getattr(dt.dt, "day_of_week", None)
    if dow is None:
        dow = dt.dt.dayofweek
    if "hour" in calendar_cols:
        df_cal["cal_hour"] = dt.dt.hour
    if "dayofweek" in calendar_cols:
        df_cal["cal_dayofweek"] = dow
    if "dayofmonth" in calendar_cols:
        df_cal["cal_dayofmonth"] = dt.dt.day
    if "weekofyear" in calendar_cols:
        df_cal["cal_weekofyear"] = dt.dt.isocalendar().week.astype(int)
    if "month" in calendar_cols:
        df_cal["cal_month"] = dt.dt.month
    if "quarter" in calendar_cols:
        df_cal["cal_quarter"] = dt.dt.quarter
    if "year" in calendar_cols:
        df_cal["cal_year"] = dt.dt.year
    if "is_weekend" in calendar_cols:
        df_cal["cal_is_weekend"] = dow.isin([5, 6]).astype(int)

    return df_cal


def build_series_features(
    history_df: pd.DataFrame,
    feature_config: dict[str, Any],
    include_target: bool = True,
) -> tuple[pd.DataFrame, list[str]]:
    """Generate lag, rolling, and calendar features for a single series.

    history_df must contain:
      - timestamp: datetime-like
      - target: float (sales/demand)

    Leakage prevention:
      - Lag 1 is target at t-1.
      - Rolling statistics compute over shifted target: shift(1).rolling(w).
    """
    df = history_df.sort_values(by="timestamp").copy()
    feature_cols: list[str] = []

    lags = feature_config.get("lags", [1, 2, 7, 14, 28])
    rolling_means = feature_config.get("rolling_means", [7, 14, 28])
    rolling_stds = feature_config.get("rolling_stds", [7, 28])
    calendar_cols = feature_config.get("calendar", ["dayofweek", "month"])

    # 1. Lags
    for lag in lags:
        col_name = f"lag_{lag}"
        df[col_name] = df["target"].shift(lag)
        feature_cols.append(col_name)

    # 2. Rolling statistics (shifted by 1 to never include current target)
    target_shifted = df["target"].shift(1)
    for w in rolling_means:
        col_name = f"rolling_mean_{w}"
        df[col_name] = target_shifted.rolling(window=w, min_periods=max(1, w // 2)).mean()
        feature_cols.append(col_name)

    for w in rolling_stds:
        col_name = f"rolling_std_{w}"
        df[col_name] = target_shifted.rolling(window=w, min_periods=max(2, w // 2)).std().fillna(0.0)
        feature_cols.append(col_name)

    # 3. Calendar features
    cal_df = extract_calendar_features(df["timestamp"], calendar_cols)
    for c in cal_df.columns:
        df[c] = cal_df[c]
        feature_cols.append(c)

    return df, feature_cols


def build_multi_series_dataset(
    long_df: pd.DataFrame,
    feature_config: dict[str, Any],
    drop_na: bool = True,
) -> tuple[pd.DataFrame, list[str]]:
    """Build feature dataset across multiple time series in long_df [series_id, timestamp, target]."""
    all_chunks = []
    feature_cols: list[str] = []

    for sid, group in long_df.groupby("series_id"):
        feat_df, cols = build_series_features(group, feature_config)
        feat_df["series_id"] = str(sid)
        all_chunks.append(feat_df)
        if not feature_cols:
            feature_cols = cols

    if not all_chunks:
        return pd.DataFrame(), []

    result = pd.concat(all_chunks, ignore_index=True)
    if drop_na:
        # Drop rows where lag features are NaN (warmup period)
        result = result.dropna(subset=feature_cols).reset_index(drop=True)

    return result, feature_cols
