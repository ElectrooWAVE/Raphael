"""Comprehensive data validator for Raphael against Section 3 specifications.

Verifies schemas, pair consistency, temporal continuity, statistical properties
(zero-demand share, ADI/CV^2 intermittency, promotion lift, lead-time correlations),
and computes Raphael stock cover without using stock_status_simulated.
"""
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd


def compute_intermittency_metrics(series: pd.Series) -> Dict[str, float]:
    """Calculate ADI (Average Demand Interval) and CV^2 (Squared Coefficient of Variation).

    Classification rules (Syntetos-Boylan / Kostenko-Hyndman):
    - Smooth: ADI < 1.32 and CV^2 < 0.49
    - Intermittent: ADI >= 1.32 and CV^2 < 0.49
    - Erratic: ADI < 1.32 and CV^2 >= 0.49
    - Lumpy: ADI >= 1.32 and CV^2 >= 0.49
    """
    total_periods = len(series)
    non_zero_vals = series[series > 0]
    non_zero_count = len(non_zero_vals)

    if non_zero_count == 0:
        return {
            "adi": float("inf"),
            "cv2": 0.0,
            "category": "Intermittent (All Zeros)",
        }

    adi = total_periods / non_zero_count
    mean_nz = non_zero_vals.mean()
    std_nz = non_zero_vals.std(ddof=1) if non_zero_count > 1 else 0.0
    cv = (std_nz / mean_nz) if mean_nz > 0 else 0.0
    cv2 = cv ** 2

    if adi < 1.32 and cv2 < 0.49:
        category = "Smooth"
    elif adi >= 1.32 and cv2 < 0.49:
        category = "Intermittent"
    elif adi < 1.32 and cv2 >= 0.49:
        category = "Erratic"
    else:
        category = "Lumpy"

    return {
        "adi": round(float(adi), 3),
        "cv2": round(float(cv2), 3),
        "category": category,
    }


def validate_schema_and_integrity(
    df_demand: pd.DataFrame,
    df_lead_time: pd.DataFrame,
    df_inventory: pd.DataFrame,
    df_calendar: pd.DataFrame,
    config: dict,
) -> Dict[str, Any]:
    """Validate schemas, dates, missing values, and pair alignments across all 4 datasets."""
    errors = []
    warnings = []

    # 1. Column presence check
    expected_cols = {
        "demand": ["date", "material", "area", "quantity", "is_promotion"],
        "lead_time": ["material", "area", "order_date", "order_quantity", "lead_time_days"],
        "inventory": ["material", "area", "current_stock", "last_updated", "stock_status_simulated"],
        "calendar": ["date", "event_name_1", "event_type_1", "event_name_2", "event_type_2"],
    }

    dfs = {
        "demand": df_demand,
        "lead_time": df_lead_time,
        "inventory": df_inventory,
        "calendar": df_calendar,
    }

    for name, cols in expected_cols.items():
        missing = [c for c in cols if c not in dfs[name].columns]
        if missing:
            errors.append(f"Dataset '{name}' missing required columns: {missing}")

    if errors:
        return {"valid": False, "errors": errors, "warnings": warnings}

    # 2. Check nulls / NaNs
    for name, df in dfs.items():
        # In calendar, event columns can be null on non-event days
        cols_to_check = [c for c in df.columns if not (name == "calendar" and "event" in c)]
        null_counts = df[cols_to_check].isnull().sum()
        if null_counts.sum() > 0:
            errors.append(f"Null values detected in '{name}': {null_counts[null_counts > 0].to_dict()}")

    # 3. Check negative values
    if (df_demand["quantity"] < 0).any():
        errors.append("Negative demand quantity detected.")
    if (df_lead_time["order_quantity"] <= 0).any():
        errors.append("Non-positive lead time order_quantity detected.")
    if (df_lead_time["lead_time_days"] < 0).any():
        errors.append("Negative lead_time_days detected.")
    if (df_inventory["current_stock"] < 0).any():
        errors.append("Negative current_stock detected in inventory.")

    # 4. Check Pair Alignments across demand, lead time, and inventory
    demand_pairs = set(zip(df_demand["material"], df_demand["area"]))
    lead_time_pairs = set(zip(df_lead_time["material"], df_lead_time["area"]))
    inventory_pairs = set(zip(df_inventory["material"], df_inventory["area"]))

    pair_count_demand = len(demand_pairs)
    pair_count_lt = len(lead_time_pairs)
    pair_count_inv = len(inventory_pairs)

    if not (pair_count_demand == pair_count_lt == pair_count_inv == 75):
        errors.append(
            f"Pair count mismatch: Demand={pair_count_demand}, LeadTime={pair_count_lt}, Inventory={pair_count_inv} (expected 75)"
        )

    if demand_pairs != lead_time_pairs:
        diff = demand_pairs.symmetric_difference(lead_time_pairs)
        errors.append(f"Mismatch between Demand and Lead Time pairs: {len(diff)} discrepancies")

    if demand_pairs != inventory_pairs:
        diff = demand_pairs.symmetric_difference(inventory_pairs)
        errors.append(f"Mismatch between Demand and Inventory pairs: {len(diff)} discrepancies")

    # 5. Check Materials and Areas
    materials = sorted(df_demand["material"].unique().tolist())
    areas = sorted(df_demand["area"].unique().tolist())

    expected_areas = ["California - CA_1", "Texas - TX_1", "Wisconsin - WI_1"]
    if sorted(areas) != sorted(expected_areas):
        errors.append(f"Areas mismatch. Found: {areas}, Expected: {expected_areas}")
    if len(materials) != 25:
        errors.append(f"Expected 25 distinct materials, found: {len(materials)}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "pair_count": len(demand_pairs),
        "materials_count": len(materials),
        "areas": areas,
    }


def analyze_demand_properties(df_demand: pd.DataFrame, expected_as_of: str) -> Dict[str, Any]:
    """Verify section 3 facts regarding demand history."""
    results = {}
    pair_groups = df_demand.groupby(["material", "area"])

    # Row counts per pair
    counts_per_pair = pair_groups.size()
    min_rows = int(counts_per_pair.min())
    max_rows = int(counts_per_pair.max())
    all_exact_1913 = (min_rows == 1913 and max_rows == 1913)

    # Date ranges
    min_date = df_demand["date"].min().strftime("%Y-%m-%d")
    max_date = df_demand["date"].max().strftime("%Y-%m-%d")

    # Check for date continuity / gaps per pair
    expected_drange = pd.date_range(min_date, max_date, freq="D")
    has_gaps = False
    for _, group in pair_groups:
        if len(group) != len(expected_drange) or not (group["date"].values == expected_drange.values).all():
            has_gaps = True
            break

    # Zero-demand stats
    total_rows = len(df_demand)
    total_zeros = int((df_demand["quantity"] == 0).sum())
    overall_zero_share = total_zeros / total_rows

    zeros_per_pair = pair_groups["quantity"].apply(lambda s: (s == 0).mean())
    pairs_over_30_pct_zeros = int((zeros_per_pair > 0.30).sum())
    pairs_over_50_pct_zeros = int((zeros_per_pair > 0.50).sum())

    means_per_pair = pair_groups["quantity"].mean()
    min_pair_mean = float(means_per_pair.min())
    max_pair_mean = float(means_per_pair.max())

    # Promotion share and lift
    promo_share_per_pair = pair_groups["is_promotion"].mean()
    min_promo_share = float(promo_share_per_pair.min())
    max_promo_share = float(promo_share_per_pair.max())

    # Compute lift per pair: mean(demand | promo=1) / mean(demand | promo=0)
    def calc_lift(grp: pd.DataFrame) -> float:
        d_p1 = grp[grp["is_promotion"] == 1]["quantity"].mean()
        d_p0 = grp[grp["is_promotion"] == 0]["quantity"].mean()
        return (d_p1 / d_p0) if d_p0 > 0 else 1.0

    lifts = pair_groups.apply(calc_lift)
    mean_lift = float(lifts.mean())
    min_lift = float(lifts.min())
    max_lift = float(lifts.max())

    # Intermittency categorization breakdown
    intermittency_records = []
    category_counts = {"Smooth": 0, "Intermittent": 0, "Erratic": 0, "Lumpy": 0}
    for (mat, area), grp in pair_groups:
        metrics = compute_intermittency_metrics(grp["quantity"])
        metrics["material"] = mat
        metrics["area"] = area
        intermittency_records.append(metrics)
        cat = metrics["category"]
        if cat in category_counts:
            category_counts[cat] += 1

    results = {
        "total_rows": total_rows,
        "rows_per_pair_min": min_rows,
        "rows_per_pair_max": max_rows,
        "all_exact_1913": all_exact_1913,
        "min_date": min_date,
        "max_date": max_date,
        "as_of_date_matches": (max_date == expected_as_of),
        "has_date_gaps": has_gaps,
        "overall_zero_share": round(overall_zero_share, 4),
        "pairs_over_30_pct_zeros": pairs_over_30_pct_zeros,
        "pairs_over_50_pct_zeros": pairs_over_50_pct_zeros,
        "pair_mean_range": [round(min_pair_mean, 2), round(max_pair_mean, 2)],
        "promo_share_range": [round(min_promo_share, 4), round(max_promo_share, 4)],
        "promo_lift_mean": round(mean_lift, 3),
        "promo_lift_range": [round(min_lift, 3), round(max_lift, 3)],
        "category_counts": category_counts,
        "intermittency_details": intermittency_records,
    }
    return results


def analyze_lead_time_properties(df_lead_time: pd.DataFrame) -> Dict[str, Any]:
    """Verify section 3 facts regarding lead time history."""
    pair_groups = df_lead_time.groupby(["material", "area"])
    counts_per_pair = pair_groups.size()
    min_orders = int(counts_per_pair.min())
    max_orders = int(counts_per_pair.max())
    all_exact_274 = (min_orders == 274 and max_orders == 274)

    min_date = df_lead_time["order_date"].min().strftime("%Y-%m-%d")
    max_date = df_lead_time["order_date"].max().strftime("%Y-%m-%d")

    mean_lead_time = float(df_lead_time["lead_time_days"].mean())

    # Quantity correlation: overall and average within-pair
    overall_corr = float(df_lead_time["order_quantity"].corr(df_lead_time["lead_time_days"]))
    within_pair_corrs = pair_groups.apply(lambda g: g["order_quantity"].corr(g["lead_time_days"])).dropna()
    mean_within_pair_corr = float(within_pair_corrs.mean())

    # Nov-Dec effect
    df_lt = df_lead_time.copy()
    df_lt["month"] = df_lt["order_date"].dt.month
    df_lt["is_nov_dec"] = df_lt["month"].isin([11, 12])
    mean_nov_dec = float(df_lt[df_lt["is_nov_dec"]]["lead_time_days"].mean())
    mean_other_months = float(df_lt[~df_lt["is_nov_dec"]]["lead_time_days"].mean())
    nov_dec_diff = round(mean_nov_dec - mean_other_months, 2)

    # Area means
    area_means = df_lt.groupby("area")["lead_time_days"].mean().round(2).to_dict()

    return {
        "total_orders": len(df_lead_time),
        "orders_per_pair_min": min_orders,
        "orders_per_pair_max": max_orders,
        "all_exact_274": all_exact_274,
        "min_date": min_date,
        "max_date": max_date,
        "mean_lead_time": round(mean_lead_time, 2),
        "overall_corr_quantity": round(overall_corr, 3),
        "mean_within_pair_corr_quantity": round(mean_within_pair_corr, 3),
        "mean_nov_dec_lead_time": round(mean_nov_dec, 2),
        "mean_other_months_lead_time": round(mean_other_months, 2),
        "nov_dec_delta": nov_dec_diff,
        "area_means": area_means,
    }


def analyze_inventory_properties(df_inventory: pd.DataFrame, df_demand: pd.DataFrame, expected_as_of: str) -> Dict[str, Any]:
    """Verify inventory dates and compute Raphael stock cover without stock_status_simulated."""
    # Check last_updated date
    unique_dates = df_inventory["last_updated"].dt.strftime("%Y-%m-%d").unique()
    all_dates_match = (len(unique_dates) == 1 and unique_dates[0] == expected_as_of)

    stock_stats = {
        "min": float(df_inventory["current_stock"].min()),
        "q25": float(df_inventory["current_stock"].quantile(0.25)),
        "median": float(df_inventory["current_stock"].median()),
        "mean": round(float(df_inventory["current_stock"].mean()), 2),
        "q75": float(df_inventory["current_stock"].quantile(0.75)),
        "max": float(df_inventory["current_stock"].max()),
    }

    # Compute stock cover in days computed strictly by Raphael:
    # stock_cover_days = current_stock / mean_daily_demand
    demand_means = df_demand.groupby(["material", "area"])["quantity"].mean().reset_index()
    demand_means.rename(columns={"quantity": "mean_daily_demand"}, inplace=True)

    merged = pd.merge(df_inventory, demand_means, on=["material", "area"], how="left")
    # Avoid zero division guard
    merged["stock_cover_days"] = np.where(
        merged["mean_daily_demand"] > 0,
        merged["current_stock"] / merged["mean_daily_demand"],
        np.nan,
    )

    cover_stats = {
        "min_days": round(float(merged["stock_cover_days"].min()), 1),
        "q25_days": round(float(merged["stock_cover_days"].quantile(0.25)), 1),
        "median_days": round(float(merged["stock_cover_days"].median()), 1),
        "mean_days": round(float(merged["stock_cover_days"].mean()), 1),
        "q75_days": round(float(merged["stock_cover_days"].quantile(0.75)), 1),
        "max_days": round(float(merged["stock_cover_days"].max()), 1),
    }

    # Record distribution across spread buckets
    spread_buckets = {
        "critical_sub_7_days": int((merged["stock_cover_days"] < 7).sum()),
        "low_7_to_14_days": int(((merged["stock_cover_days"] >= 7) & (merged["stock_cover_days"] < 14)).sum()),
        "medium_14_to_30_days": int(((merged["stock_cover_days"] >= 14) & (merged["stock_cover_days"] < 30)).sum()),
        "well_stocked_30_plus_days": int((merged["stock_cover_days"] >= 30).sum()),
    }

    return {
        "unique_last_updated": unique_dates.tolist(),
        "all_match_as_of": bool(all_dates_match),
        "stock_stats": stock_stats,
        "stock_cover_stats": cover_stats,
        "stock_cover_buckets": spread_buckets,
    }
