"""Ensemble blending utility for Raphael demand models.

Combines forecasts from distinct model paradigms (e.g. Prophet + Gradient Boosting
or Prophet + Weekday Mean) to reduce variance and improve forecast stability on
intermittent demand series.
"""
from typing import Dict, List, Optional
import numpy as np
import pandas as pd


def blend_predictions(
    df_pred_a: pd.DataFrame,
    df_pred_b: pd.DataFrame,
    weight_a: float = 0.5,
    weight_b: float = 0.5,
) -> pd.DataFrame:
    """Linearly blend two prediction DataFrames with convex weights.

    Args:
        df_pred_a: Prediction DataFrame from model A (contains yhat, bounds).
        df_pred_b: Prediction DataFrame from model B.
        weight_a: Weight applied to model A (default: 0.5).
        weight_b: Weight applied to model B (default: 0.5).

    Returns:
        Blended DataFrame with combined yhat and interval bounds, clipped at 0.0.
    """
    total_w = weight_a + weight_b
    wa = weight_a / total_w
    wb = weight_b / total_w

    res = df_pred_a[["ds"]].copy() if "ds" in df_pred_a.columns else pd.DataFrame(index=df_pred_a.index)
    if "material" in df_pred_a.columns:
        res["material"] = df_pred_a["material"].values
    if "area" in df_pred_a.columns:
        res["area"] = df_pred_a["area"].values

    res["yhat"] = np.maximum(0.0, wa * df_pred_a["yhat"].to_numpy() + wb * df_pred_b["yhat"].to_numpy())

    for bound in ["yhat_lower_80", "yhat_upper_80", "yhat_lower_95", "yhat_upper_95"]:
        if bound in df_pred_a.columns and bound in df_pred_b.columns:
            res[bound] = np.maximum(0.0, wa * df_pred_a[bound].to_numpy() + wb * df_pred_b[bound].to_numpy())

    return res
