"""Forecasting evaluation metrics and multi-level temporal aggregation.

Supports:
- Pooled WAPE (sum|err| / sum actual across all series)
- Mean of per-pair WAPE (mean of pair-level WAPEs)
- Guarded MAPE (with zero guard)
- RMSE (Root Mean Squared Error)
- Forecast Bias (mean signed error: pred - actual)
- Empirical interval coverage (80% and 95%)
- Multi-level evaluation: Daily, Weekly (12 whole weeks), and Lead-Time Window
"""
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


def compute_wape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Calculate Weighted Absolute Percentage Error (WAPE = sum(|y - yhat|) / sum(y))."""
    sum_actual = float(np.sum(y_true))
    sum_abs_err = float(np.sum(np.abs(y_true - y_pred)))
    if sum_actual == 0:
        return 0.0 if sum_abs_err == 0 else 1.0
    return float(sum_abs_err / sum_actual)


def compute_mape_guarded(y_true: np.ndarray, y_pred: np.ndarray, epsilon: float = 1.0) -> float:
    """Calculate MAPE with an additive epsilon guard for zero-demand intermittent periods."""
    abs_errors = np.abs(y_true - y_pred)
    relative_errors = abs_errors / (y_true + epsilon)
    return float(np.mean(relative_errors))


def compute_rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Calculate Root Mean Squared Error."""
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def compute_bias(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Calculate Mean Forecast Bias (mean(y_pred - y_true)). Positive indicates over-forecast."""
    return float(np.mean(y_pred - y_true))


def compute_coverage(y_true: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> float:
    """Calculate empirical coverage percentage inside lower and upper prediction bands."""
    within_bounds = (y_true >= lower) & (y_true <= upper)
    return float(np.mean(within_bounds))


def evaluate_series(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    lower_80: Optional[np.ndarray] = None,
    upper_80: Optional[np.ndarray] = None,
    lower_95: Optional[np.ndarray] = None,
    upper_95: Optional[np.ndarray] = None,
) -> Dict[str, float]:
    """Compute standard metric suite for 1D arrays."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    metrics = {
        "wape": round(compute_wape(y_true, y_pred), 4),
        "mape_guarded": round(compute_mape_guarded(y_true, y_pred), 4),
        "rmse": round(compute_rmse(y_true, y_pred), 4),
        "bias": round(compute_bias(y_true, y_pred), 4),
    }

    if lower_80 is not None and upper_80 is not None:
        metrics["coverage_80"] = round(compute_coverage(y_true, lower_80, upper_80), 4)

    if lower_95 is not None and upper_95 is not None:
        metrics["coverage_95"] = round(compute_coverage(y_true, lower_95, upper_95), 4)

    return metrics


def evaluate_forecast_multi_level(
    df_eval: pd.DataFrame,
    lead_time_days: int = 5,
    actual_col: str = "y",
    pred_col: str = "yhat",
) -> Dict[str, Dict[str, float]]:
    """Evaluate forecasts at three levels: Daily, Weekly, and Lead-Time Window.

    Args:
        df_eval: DataFrame containing 'ds', 'y', 'yhat', and optional bounds.
        lead_time_days: Historical or predicted lead-time window in days.
        actual_col: Column name of ground truth actual demand.
        pred_col: Column name of predicted demand.

    Returns:
        Dict with keys: 'daily', 'weekly', 'lead_time_window'.
    """
    df = df_eval.sort_values("ds").reset_index(drop=True)
    y_true = df[actual_col].to_numpy(dtype=float)
    y_pred = df[pred_col].to_numpy(dtype=float)

    l80 = df["yhat_lower_80"].to_numpy(dtype=float) if "yhat_lower_80" in df.columns else None
    u80 = df["yhat_upper_80"].to_numpy(dtype=float) if "yhat_upper_80" in df.columns else None
    l95 = df["yhat_lower_95"].to_numpy(dtype=float) if "yhat_lower_95" in df.columns else None
    u95 = df["yhat_upper_95"].to_numpy(dtype=float) if "yhat_upper_95" in df.columns else None

    # 1. Daily Level
    daily_metrics = evaluate_series(y_true, y_pred, l80, u80, l95, u95)

    # 2. Weekly Level (7-day non-overlapping window sums)
    n_days = len(df)
    n_full_weeks = n_days // 7
    if n_full_weeks > 0:
        trunc_len = n_full_weeks * 7
        y_true_w = y_true[:trunc_len].reshape(-1, 7).sum(axis=1)
        y_pred_w = y_pred[:trunc_len].reshape(-1, 7).sum(axis=1)
        l80_w = l80[:trunc_len].reshape(-1, 7).sum(axis=1) if l80 is not None else None
        u80_w = u80[:trunc_len].reshape(-1, 7).sum(axis=1) if u80 is not None else None
        l95_w = l95[:trunc_len].reshape(-1, 7).sum(axis=1) if l95 is not None else None
        u95_w = u95[:trunc_len].reshape(-1, 7).sum(axis=1) if u95 is not None else None
        weekly_metrics = evaluate_series(y_true_w, y_pred_w, l80_w, u80_w, l95_w, u95_w)
    else:
        weekly_metrics = daily_metrics.copy()

    # 3. Lead-time Window Level (rolling sum of length = lead_time_days)
    window = max(1, int(round(lead_time_days)))
    if n_days >= window:
        s_true = pd.Series(y_true).rolling(window=window).sum().dropna().to_numpy()
        s_pred = pd.Series(y_pred).rolling(window=window).sum().dropna().to_numpy()
        s_l80 = pd.Series(l80).rolling(window=window).sum().dropna().to_numpy() if l80 is not None else None
        s_u80 = pd.Series(u80).rolling(window=window).sum().dropna().to_numpy() if u80 is not None else None
        s_l95 = pd.Series(l95).rolling(window=window).sum().dropna().to_numpy() if l95 is not None else None
        s_u95 = pd.Series(u95).rolling(window=window).sum().dropna().to_numpy() if u95 is not None else None
        lt_metrics = evaluate_series(s_true, s_pred, s_l80, s_u80, s_l95, s_u95)
    else:
        lt_metrics = daily_metrics.copy()

    return {
        "daily": daily_metrics,
        "weekly": weekly_metrics,
        "lead_time_window": lt_metrics,
    }


def compute_fleet_wapes(
    df_eval_all: pd.DataFrame,
    pred_col: str,
    actual_col: str = "y",
    lead_time_map: Optional[Dict[Tuple[str, str], float]] = None,
) -> Dict[str, Dict[str, float]]:
    """Compute BOTH Pooled WAPE and Mean-Pair WAPE at Daily, Weekly, and Lead-Time Window levels across all pairs.

    Returns:
        Dict with keys: 'daily', 'weekly', 'lead_time_window', each containing:
        {'pooled_wape': float, 'mean_pair_wape': float}
    """
    groups = df_eval_all.groupby(["material", "area"])

    # 1. Daily Level
    total_abs_err_daily = float(np.sum(np.abs(df_eval_all[actual_col] - df_eval_all[pred_col])))
    total_actual_daily = float(np.sum(df_eval_all[actual_col]))
    pooled_daily_wape = (total_abs_err_daily / total_actual_daily) if total_actual_daily > 0 else 0.0

    pair_daily_wapes = []
    for _, grp in groups:
        act = float(grp[actual_col].sum())
        err = float(np.abs(grp[actual_col] - grp[pred_col]).sum())
        pair_daily_wapes.append((err / act) if act > 0 else 0.0)
    mean_pair_daily_wape = float(np.mean(pair_daily_wapes))

    # 2. Weekly Level (7-day non-overlapping sums)
    weekly_actuals = []
    weekly_preds = []
    pair_weekly_wapes = []

    for _, grp in groups:
        g = grp.sort_values("ds")
        y_act = g[actual_col].to_numpy(dtype=float)
        y_p = g[pred_col].to_numpy(dtype=float)
        n_w = len(y_act) // 7
        if n_w > 0:
            act_w = y_act[:n_w * 7].reshape(-1, 7).sum(axis=1)
            p_w = y_p[:n_w * 7].reshape(-1, 7).sum(axis=1)
            weekly_actuals.extend(act_w)
            weekly_preds.extend(p_w)
            pair_act_sum = float(np.sum(act_w))
            pair_err_sum = float(np.sum(np.abs(act_w - p_w)))
            pair_weekly_wapes.append((pair_err_sum / pair_act_sum) if pair_act_sum > 0 else 0.0)

    total_act_w = float(np.sum(weekly_actuals))
    total_err_w = float(np.sum(np.abs(np.array(weekly_actuals) - np.array(weekly_preds))))
    pooled_weekly_wape = (total_err_w / total_act_w) if total_act_w > 0 else 0.0
    mean_pair_weekly_wape = float(np.mean(pair_weekly_wapes))

    # 3. Lead-time Window Level
    lt_actuals = []
    lt_preds = []
    pair_lt_wapes = []

    for (mat, area), grp in groups:
        g = grp.sort_values("ds")
        window = 5
        if lead_time_map and (mat, area) in lead_time_map:
            window = max(1, int(round(lead_time_map[(mat, area)])))
        s_act = g[actual_col].rolling(window=window).sum().dropna().to_numpy()
        s_p = g[pred_col].rolling(window=window).sum().dropna().to_numpy()
        if len(s_act) > 0:
            lt_actuals.extend(s_act)
            lt_preds.extend(s_p)
            pair_act_lt = float(np.sum(s_act))
            pair_err_lt = float(np.sum(np.abs(s_act - s_p)))
            pair_lt_wapes.append((pair_err_lt / pair_act_lt) if pair_act_lt > 0 else 0.0)

    total_act_lt = float(np.sum(lt_actuals))
    total_err_lt = float(np.sum(np.abs(np.array(lt_actuals) - np.array(lt_preds))))
    pooled_lt_wape = (total_err_lt / total_act_lt) if total_act_lt > 0 else 0.0
    mean_pair_lt_wape = float(np.mean(pair_lt_wapes))

    return {
        "daily": {
            "pooled_wape": round(pooled_daily_wape, 4),
            "mean_pair_wape": round(mean_pair_daily_wape, 4),
        },
        "weekly": {
            "pooled_wape": round(pooled_weekly_wape, 4),
            "mean_pair_wape": round(mean_pair_weekly_wape, 4),
        },
        "lead_time_window": {
            "pooled_wape": round(pooled_lt_wape, 4),
            "mean_pair_wape": round(mean_pair_lt_wape, 4),
        },
    }
