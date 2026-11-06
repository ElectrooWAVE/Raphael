"""Inventory decision engine for Raphael (Phase 4).

Pure arithmetic decision layer for inventory replenishment:
- Safety Stock (SS) with dual uncertainty (demand variance and lead-time variance)
- Reorder Point (ROP)
- Economic Order Quantity (EOQ) and Days-of-Cover replenishment sizing
- Day-by-day forecast demand depletion for days_remaining
- Inventory status classification (OK, REORDER, CRITICAL)
- Extrapolation and assumption tracking

All formulas are pure arithmetic (no machine learning) and fully testable.
"""
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import scipy.stats as stats


def compute_safety_stock(
    demand_rate: float,
    demand_std: float,
    lead_time: float,
    lead_time_std: float,
    service_level: float = 0.95,
    z_score: Optional[float] = None,
) -> float:
    """Compute safety stock considering both demand and lead-time variability.

    Formula:
        SS = Z * sqrt(L * sigma_D^2 + D^2 * sigma_L^2)

    Args:
        demand_rate (D): Mean daily demand rate over the lead time window.
        demand_std (sigma_D): Standard deviation of daily forecast errors.
        lead_time (L): Expected supplier lead time in days.
        lead_time_std (sigma_L): Calibrated standard deviation of lead time in days.
        service_level: Target cycle service level (e.g. 0.95).
        z_score: Optional explicit inverse normal CDF value. If None, computed from service_level.

    Returns:
        Safety stock units (float >= 0.0).
    """
    if z_score is None:
        z_score = float(stats.norm.ppf(service_level))

    D = max(0.0, float(demand_rate))
    sigma_D = max(0.0, float(demand_std))
    L = max(0.0, float(lead_time))
    sigma_L = max(0.0, float(lead_time_std))

    variance_term = (L * (sigma_D ** 2)) + ((D ** 2) * (sigma_L ** 2))
    ss = z_score * np.sqrt(max(0.0, variance_term))
    return float(max(0.0, ss))


def compute_reorder_point(
    demand_rate: float,
    lead_time: float,
    safety_stock: float,
) -> float:
    """Compute reorder point (ROP).

    Formula:
        ROP = D * L + SS

    Args:
        demand_rate (D): Mean daily demand rate over lead time window.
        lead_time (L): Expected supplier lead time in days.
        safety_stock (SS): Calculated safety stock.

    Returns:
        Reorder point in units (float >= 0.0).
    """
    D = max(0.0, float(demand_rate))
    L = max(0.0, float(lead_time))
    ss = max(0.0, float(safety_stock))
    return float(max(0.0, (D * L) + ss))


def compute_eoq(
    annual_demand: float,
    ordering_cost_fixed: float = 50.0,
    holding_cost_annual_unit: float = 2.0,
) -> float:
    """Compute Economic Order Quantity (EOQ).

    Formula:
        EOQ = sqrt((2 * S * D_annual) / H)

    Args:
        annual_demand: Expected annual demand in units.
        ordering_cost_fixed (S): Fixed cost per purchase order ($).
        holding_cost_annual_unit (H): Annual cost to hold 1 unit ($).

    Returns:
        Economic order quantity units (float >= 0.0).
    """
    if annual_demand <= 0.0 or ordering_cost_fixed <= 0.0 or holding_cost_annual_unit <= 0.0:
        return 0.0
    val = (2.0 * ordering_cost_fixed * annual_demand) / holding_cost_annual_unit
    return float(np.sqrt(max(0.0, val)))


def compute_planned_order_quantity(
    forecast_daily_demands: List[float],
    cover_days: int = 14,
    hist_p5: Optional[float] = None,
    hist_p95: Optional[float] = None,
) -> Tuple[float, float, bool]:
    """Compute replenishment order size based on cover days and historical bounds.

    Args:
        forecast_daily_demands: Future daily forecast quantities.
        cover_days: Target days of demand to cover (default 14).
        hist_p5: Historical 5th percentile order quantity for the pair.
        hist_p95: Historical 95th percentile order quantity for the pair.

    Returns:
        Tuple of (unconstrained_qty, clipped_qty, is_extrapolation).
    """
    if not forecast_daily_demands:
        return 0.0, 0.0, False

    window = forecast_daily_demands[:cover_days]
    raw_qty = float(np.sum(np.maximum(0.0, window)))

    # Determine historical range
    min_bound = hist_p5 if hist_p5 is not None else 1.0
    max_bound = hist_p95 if hist_p95 is not None else max(100.0, raw_qty)

    if min_bound > max_bound:
        min_bound, max_bound = max_bound, min_bound

    clipped_qty = float(np.clip(raw_qty, min_bound, max_bound))
    is_extrapolation = bool(raw_qty < min_bound or raw_qty > max_bound)

    return raw_qty, clipped_qty, is_extrapolation


def compute_order_up_to_level(
    rop: float,
    demand_rate: float,
    review_period_days: int = 7,
    daily_forecasts: Optional[List[float]] = None,
) -> float:
    """Compute order-up-to level (S) under periodic review.

    Formula:
        order_up_to_level = ROP + demand over one review period (assumptions.yaml)

    Args:
        rop: Calculated reorder point.
        demand_rate: Mean daily demand rate over lead time window.
        review_period_days: Review cycle length in days (default 7 from assumptions.yaml).
        daily_forecasts: Optional daily forecast demands to sum over review window.

    Returns:
        Order-up-to level in units (float >= 0.0).
    """
    rop_val = max(0.0, float(rop))
    if daily_forecasts is not None and len(daily_forecasts) >= review_period_days:
        review_demand = float(np.sum(np.maximum(0.0, daily_forecasts[:review_period_days])))
    else:
        review_demand = float(max(0.0, demand_rate) * float(review_period_days))

    # Ensure minimum 1.0 unit replenishment horizon when review demand is 0
    # to guarantee order brings inventory strictly above ROP
    effective_review_demand = max(1.0 if review_demand <= 0.0 else review_demand, 0.0)
    return float(max(0.0, rop_val + effective_review_demand))


def compute_recommended_order_quantity(
    planned_quantity: float,
    order_up_to_level: float,
    current_stock: float,
    hist_p5: Optional[float] = None,
    hist_p95: Optional[float] = None,
) -> Tuple[float, bool]:
    """Compute recommended replenishment order quantity.

    Rule:
        recommended_order_quantity = max(planned_quantity, order_up_to_level - current_stock)
        where order_up_to_level = ROP + demand over one review period.

    Do NOT clip the recommendation to the historical range [hist_p5, hist_p95].
    If it exceeds that range, keep the larger number and set is_extrapolation = True.

    Args:
        planned_quantity: Unconstrained cover-days planned quantity (e.g. 14d cover).
        order_up_to_level: ROP + review period demand.
        current_stock: Current on-hand stock.
        hist_p5: Historical 5th percentile order quantity.
        hist_p95: Historical 95th percentile order quantity.

    Returns:
        Tuple of (recommended_order_quantity, is_extrapolation).
    """
    deficit = float(order_up_to_level) - float(current_stock)
    rec_qty = float(max(0.0, float(planned_quantity), deficit))

    is_extrap = False
    if hist_p5 is not None and rec_qty < hist_p5 and rec_qty > 0.0:
        is_extrap = True
    if hist_p95 is not None and rec_qty > hist_p95:
        is_extrap = True

    return round(rec_qty, 2), is_extrap


def compute_days_remaining(
    current_stock: float,
    daily_forecasts: List[float],
    max_horizon_days: int = 90,
) -> Tuple[float, bool, str]:
    """Calculate days of stock cover remaining by day-by-day depletion.

    Depletes actual daily forecast demand until cumulative demand exceeds current stock.

    Args:
        current_stock: On-hand stock count.
        daily_forecasts: List of non-negative daily forecast values.
        max_horizon_days: Forecast horizon ceiling (default 90 days).

    Returns:
        Tuple of (days_remaining, beyond_horizon_flag, description_label).
    """
    stock = float(current_stock)
    if stock <= 0.0:
        return 0.0, False, "depleted"

    daily_clean = [max(0.0, float(x)) for x in daily_forecasts[:max_horizon_days]]
    total_forecast_demand = sum(daily_clean)

    if total_forecast_demand == 0.0:
        return float(max_horizon_days), True, "no demand expected"

    cum_demand = 0.0
    for day_idx, d_val in enumerate(daily_clean):
        day_num = day_idx + 1
        cum_demand += d_val
        if cum_demand >= stock:
            # Interpolate exact fraction of the day
            prev_cum = cum_demand - d_val
            remaining_for_day = stock - prev_cum
            frac = (remaining_for_day / d_val) if d_val > 0.0 else 0.0
            exact_days = float(day_idx) + float(frac)
            return round(exact_days, 2), False, "within horizon"

    # Current stock exceeds entire 90-day forecast horizon
    return float(max_horizon_days), True, "beyond horizon"


def classify_inventory_status(
    current_stock: float,
    rop: float,
    days_remaining: float,
    lead_time: float,
) -> str:
    """Classify inventory replenishment status.

    Logic:
        1. CRITICAL: days_remaining < predicted lead time (stockout inevitable before replenishment arrival)
        2. REORDER: stock <= ROP (and days_remaining >= lead_time)
        3. OK: stock > ROP

    NEVER uses stock_status_simulated.

    Args:
        current_stock: Current on-hand inventory.
        rop: Reorder point threshold.
        days_remaining: Days before current stock is depleted.
        lead_time: Predicted supplier lead time in days.

    Returns:
        One of 'CRITICAL', 'REORDER', 'OK'.
    """
    stock = float(current_stock)
    r = float(rop)
    d_rem = float(days_remaining)
    lt = float(lead_time)

    # CRITICAL takes precedence when stock runs out faster than replenishment lead time
    if d_rem < lt or stock <= 0.0:
        return "CRITICAL"
    elif stock <= r:
        return "REORDER"
    else:
        return "OK"
