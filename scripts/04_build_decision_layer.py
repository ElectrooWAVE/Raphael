"""Build Raphael inventory decision layer and reorder table (Phase 4).

Executes pure arithmetic decision logic:
1. Calculates validation residual std (sigma_D) for each champion model without test leakage.
2. Sizes replenishment order quantity (cover_days default 14, clipped to historical p5-p95).
3. Evaluates lead-time model once at planned quantity for upcoming season (L, sigma_L).
4. Computes D over lead-time window, dual-variability Safety Stock (SS), Reorder Point (ROP), and EOQ.
5. Computes days_remaining via day-by-day forecast depletion.
6. Determines status (OK, REORDER, CRITICAL) without ever touching stock_status_simulated.
7. Ranks all 75 pairs by urgency.
8. Enforces loud sanity assertions.
9. Exports artifacts/inventory/reorder_table.parquet and summary artifacts.
"""
import argparse
from datetime import datetime
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd
import scipy.stats as stats
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.inventory.engine import (
    classify_inventory_status,
    compute_days_remaining,
    compute_eoq,
    compute_order_up_to_level,
    compute_planned_order_quantity,
    compute_recommended_order_quantity,
    compute_reorder_point,
    compute_safety_stock,
)
from src.models.baselines import (
    CrostonSBAModel,
    MovingAverage91DModel,
    SeasonalNaiveModel,
    WeekdayMean8WModel,
)
from src.models.leadtime_rf import LeadTimeRandomForestModel
from src.utils.logger import setup_logger
from src.utils.progress import get_progress_bar, timed_block


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 4: Build Inventory Decision Layer.")
    parser.add_argument("--config", type=str, default="configs/raphael.yaml")
    parser.add_argument("--assumptions", type=str, default="configs/assumptions.yaml")
    parser.add_argument("--cover-days", type=int, default=14)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def compute_champion_validation_sigma_d(
    df_demand: pd.DataFrame,
    champions_list: List[Dict[str, Any]],
    test_days: int = 84,
    val_days: int = 84,
) -> Dict[Tuple[str, str], float]:
    """Compute daily forecast-error standard deviation on the VALIDATION window (no test leakage)."""
    val_stds = {}
    for item in champions_list:
        mat = item["material"]
        area = item["area"]
        model_name = item["champion_model"]

        pair_df = df_demand[(df_demand["material"] == mat) & (df_demand["area"] == area)].sort_values("date").reset_index(drop=True)
        train_sub = pair_df.iloc[:-test_days - val_days].copy()
        val_sub = pair_df.iloc[-test_days - val_days:-test_days].copy()
        val_input = pd.DataFrame({"ds": val_sub["date"], "is_promotion": val_sub["is_promotion"]})

        if model_name == "weekday_mean_8w":
            p = WeekdayMean8WModel().fit(train_sub, target_col="quantity", date_col="date").predict(val_input, date_col="ds")
        elif model_name == "moving_average_91d":
            p = MovingAverage91DModel().fit(train_sub, target_col="quantity").predict(val_input)
        elif model_name == "croston_sba":
            p = CrostonSBAModel().fit(train_sub, target_col="quantity").predict(val_input)
        elif model_name == "seasonal_naive":
            p = SeasonalNaiveModel(season_length=7).fit(train_sub, target_col="quantity").predict(val_input)
        else:
            # Fallback for prophet/blend if needed: weekday mean or training residuals
            p = WeekdayMean8WModel().fit(train_sub, target_col="quantity", date_col="date").predict(val_input, date_col="ds")

        residuals = val_sub["quantity"].to_numpy() - p["yhat"].to_numpy()
        std_val = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else float(np.std(residuals))
        # Ensure positive non-zero floor
        val_stds[(mat, area)] = max(0.01, round(std_val, 4))

    return val_stds


def main():
    args = parse_args()
    logger = setup_logger("04_build_decision_layer", log_dir="logs")

    logger.info("=" * 80)
    logger.info(" Raphael Phase 4: Inventory Decision Layer (Pure Arithmetic)")
    logger.info("=" * 80)

    config = load_yaml(args.config)
    assumptions = load_yaml(args.assumptions)

    # Paths
    inv_path = Path(config["paths"]["processed_data"]["inventory_parquet"])
    demand_path = Path(config["paths"]["processed_data"]["demand_parquet"])
    lt_path = Path(config["paths"]["processed_data"]["lead_time_parquet"])
    forecast_path = Path("artifacts/forecasts/demand_forecasts_champion.parquet")
    selection_path = Path("artifacts/metrics/champion_model_selection.json")
    rf_model_path = Path("artifacts/lead_time/lead_time_rf_model.pkl")

    # Verify input artifacts
    for p, desc in [
        (inv_path, "Inventory parquet"),
        (demand_path, "Demand parquet"),
        (lt_path, "Lead time parquet"),
        (forecast_path, "Champion demand forecasts"),
        (selection_path, "Champion selection metadata"),
        (rf_model_path, "Trained Random Forest lead-time model"),
    ]:
        if not p.exists():
            logger.error(f"Required input missing: {desc} at {p}")
            sys.exit(1)

    # 1. Load Data
    df_inv = pd.read_parquet(inv_path)
    df_demand = pd.read_parquet(demand_path).sort_values("date").reset_index(drop=True)
    df_lt = pd.read_parquet(lt_path)
    df_forecasts = pd.read_parquet(forecast_path).sort_values(["material", "area", "ds"]).reset_index(drop=True)
    with open(selection_path, "r", encoding="utf-8") as f:
        champions_meta = json.load(f)
    meta_by_pair = {(m["material"], m["area"]): m for m in champions_meta}

    rf_model = LeadTimeRandomForestModel.load(rf_model_path)
    logger.info(f"Loaded datasets: {len(df_inv)} inventory rows, {len(df_forecasts)} future forecast rows.")

    # 2. Extract Business Assumptions
    inv_pol = assumptions.get("inventory_policy", {})
    cost_params = assumptions.get("cost_parameters", {})
    service_level = float(inv_pol.get("service_level", {}).get("default_value", 0.95))
    z_score = float(inv_pol.get("service_level", {}).get("z_score", stats.norm.ppf(service_level)))
    cover_days = int(args.cover_days or assumptions.get("reorder_quantity_policy", {}).get("cover_days", 14))
    review_period_days = int(inv_pol.get("review_period_days", {}).get("default_value", 7))
    order_cost = float(cost_params.get("ordering_cost_fixed", {}).get("default_value", 50.0))
    holding_rate = float(cost_params.get("holding_cost_annual_rate", {}).get("default_value", 0.20))
    unit_cost = float(cost_params.get("default_unit_cost", {}).get("default_value", 10.0))
    annual_holding_cost_unit = holding_rate * unit_cost

    logger.info(f"Policy Parameters: Service Level = {service_level*100:.1f}% (Z={z_score:.4f}), Cover Days = {cover_days}, Review Period = {review_period_days}d")
    logger.info(f"Cost Parameters  : Ordering Cost = ${order_cost:.2f}, Annual Holding Cost/unit = ${annual_holding_cost_unit:.2f}")

    # 3. Compute Validation sigma_D (No Test Leakage!)
    test_days = int(config.get("dates", {}).get("test_days", 84))
    val_days = int(config.get("dates", {}).get("validation_days", 84))
    as_of_date_str = str(config.get("dates", {}).get("as_of_date", "2016-04-24"))

    with timed_block("Computing Champion Validation Residual Standard Deviations", logger=logger):
        val_sigmas = compute_champion_validation_sigma_d(
            df_demand=df_demand,
            champions_list=champions_meta,
            test_days=test_days,
            val_days=val_days,
        )
    logger.info(f"Validation sigma_D computed across {len(val_sigmas)} pairs.")

    # 4. Historical Order Quantity percentiles & Intermittency per pair
    lt_bounds = {}
    for (mat, area), grp in df_lt.groupby(["material", "area"]):
        p5 = float(np.percentile(grp["order_quantity"], 5))
        p95 = float(np.percentile(grp["order_quantity"], 95))
        lt_bounds[(mat, area)] = (p5, p95)

    intermittency_stats = {}
    for (mat, area), grp in df_demand.groupby(["material", "area"]):
        zero_share = float(np.mean(grp["quantity"] == 0))
        mean_q = float(np.mean(grp["quantity"]))
        intermittency_stats[(mat, area)] = {
            "zero_demand_share": round(zero_share, 4),
            "historical_mean_daily_demand": round(mean_q, 2),
            "weak_normal_assumption": bool(zero_share >= 0.30 or mean_q < 1.0),
        }

    # 5. Build Decision Records
    decision_rows = []
    pbar = get_progress_bar(total=len(df_inv), desc="Computing Inventory Decisions", unit="pair")

    for _, inv_row in df_inv.iterrows():
        mat = inv_row["material"]
        area = inv_row["area"]
        stock = float(inv_row["current_stock"])
        pair_key = (mat, area)

        # Meta & champion info
        c_meta = meta_by_pair.get(pair_key, {})
        champion_model = c_meta.get("champion_model", "weekday_mean_8w")
        is_low_conf = c_meta.get("low_confidence", False)

        # 90-day daily forecast values
        pair_fc = df_forecasts[(df_forecasts["material"] == mat) & (df_forecasts["area"] == area)].sort_values("ds")
        daily_forecasts = pair_fc["yhat"].tolist()

        # Planned order quantity sizing (cover_days default 14, clipped to historical p5-p95)
        p5, p95 = lt_bounds.get(pair_key, (1.0, 500.0))
        raw_order_qty, planned_order_qty, is_qty_extrap = compute_planned_order_quantity(
            forecast_daily_demands=daily_forecasts,
            cover_days=cover_days,
            hist_p5=p5,
            hist_p95=p95,
        )

        # Evaluate Random Forest Lead-Time model once at planned quantity
        rf_input = pd.DataFrame([{
            "material": mat,
            "area": area,
            "order_date": pd.to_datetime("2016-04-25"),
            "order_quantity": planned_order_qty,
        }])
        rf_pred = rf_model.predict(rf_input).iloc[0]

        L = float(rf_pred["predicted_lead_time"])
        sigma_L = float(rf_pred["calibrated_lead_time_std"])
        sigma_L_tree = float(rf_pred["tree_spread_std"])

        # Integer lead-time window for demand calculation
        window_days = max(1, int(round(L)))
        demand_window = daily_forecasts[:window_days]
        D_window_sum = float(sum(demand_window))
        D = float(D_window_sum / window_days) if window_days > 0 else float(daily_forecasts[0])

        # Forecast error std from VALIDATION residuals
        sigma_D = float(val_sigmas.get(pair_key, c_meta.get("residual_std", 1.0)))

        # Safety Stock & Reorder Point
        ss = compute_safety_stock(
            demand_rate=D,
            demand_std=sigma_D,
            lead_time=L,
            lead_time_std=sigma_L,
            service_level=service_level,
            z_score=z_score,
        )
        # Round D, L, ss to 2 decimals first to guarantee absolute mutual consistency:
        # rop = round(D * L + ss, 2) so that abs(rop - (D * L + ss)) < 0.01 for every pair.
        D_r = round(D, 2)
        L_r = round(L, 2)
        ss_r = round(ss, 2)
        rop_r = round((D_r * L_r) + ss_r, 2)

        # Order-up-to level (ROP + demand over one review period from assumptions.yaml)
        order_up_to = compute_order_up_to_level(
            rop=rop_r,
            demand_rate=D_r,
            review_period_days=review_period_days,
            daily_forecasts=daily_forecasts,
        )

        # New recommended order quantity rule: max(planned_quantity, order_up_to - current_stock)
        # Never clip recommendation to historical range; if it exceeds range, keep larger number & flag extrapolation
        rec_qty, is_rec_extrap = compute_recommended_order_quantity(
            planned_quantity=raw_order_qty,
            order_up_to_level=order_up_to,
            current_stock=stock,
            hist_p5=p5,
            hist_p95=p95,
        )

        # EOQ
        annual_demand = D_r * 365.0
        eoq = compute_eoq(
            annual_demand=annual_demand,
            ordering_cost_fixed=order_cost,
            holding_cost_annual_unit=annual_holding_cost_unit,
        )

        # Days remaining (day-by-day forecast depletion)
        days_rem, beyond_horizon, rem_label = compute_days_remaining(
            current_stock=stock,
            daily_forecasts=daily_forecasts,
            max_horizon_days=90,
        )

        # Status: OK / REORDER / CRITICAL (NEVER use stock_status_simulated)
        status = classify_inventory_status(
            current_stock=stock,
            rop=rop_r,
            days_remaining=days_rem,
            lead_time=L_r,
        )

        # Ensure recommended_order_quantity brings stock strictly above ROP for REORDER/CRITICAL
        rec_qty_rounded = round(rec_qty, 1)
        if status in ("CRITICAL", "REORDER") and (round(stock, 1) + rec_qty_rounded) <= rop_r:
            rec_qty_rounded = round(rec_qty_rounded + 0.1, 1)

        # Stock / ROP ratio for tie-breaking
        stock_to_rop_ratio = stock / max(rop_r, 1e-4)

        # Intermittency & assumptions
        i_stat = intermittency_stats.get(pair_key, {})
        zero_share = i_stat.get("zero_demand_share", 0.0)
        weak_normal = i_stat.get("weak_normal_assumption", False)

        decision_rows.append({
            "material": mat,
            "area": area,
            "as_of_date": as_of_date_str,
            "current_stock": round(stock, 1),
            "status": status,
            "days_remaining": round(days_rem, 2),
            "days_remaining_label": rem_label,
            "beyond_horizon": beyond_horizon,
            "reorder_point_rop": rop_r,
            "safety_stock_ss": ss_r,
            "demand_rate_d": D_r,
            "demand_window_days": window_days,
            "demand_error_std_sigma_d": round(sigma_D, 3),
            "predicted_lead_time_days": L_r,
            "calibrated_lead_time_std_sigma_l": round(sigma_L, 3),
            "tree_spread_lead_time_std": round(sigma_L_tree, 3),
            "recommended_order_quantity": rec_qty_rounded,
            "raw_order_quantity_14d": round(raw_order_qty, 1),
            "order_up_to_level": round(order_up_to, 1),
            "eoq_quantity": round(eoq, 1),
            "hist_p5_order_quantity": round(p5, 1),
            "hist_p95_order_quantity": round(p95, 1),
            "is_quantity_extrapolation": is_rec_extrap,
            "champion_model": champion_model,
            "low_confidence": is_low_conf,
            "zero_demand_share": zero_share,
            "weak_normal_assumption": weak_normal,
            "stock_to_rop_ratio": round(stock_to_rop_ratio, 4),
            # Assumption disclosures
            "service_level_assumed": True,
            "service_level_target": service_level,
            "costs_assumed": True,
            "cover_days_assumed": True,
            "cover_days_target": cover_days,
        })
        pbar.update(1)
    pbar.close()

    df_decisions = pd.DataFrame(decision_rows)

    # 6. Urgency Ranking
    # Primary: status priority (CRITICAL=1, REORDER=2, OK=3)
    # Secondary: days_remaining ascending
    # Tertiary: stock_to_rop_ratio ascending
    status_order = {"CRITICAL": 1, "REORDER": 2, "OK": 3}
    df_decisions["status_rank"] = df_decisions["status"].map(status_order)
    df_decisions = df_decisions.sort_values(
        by=["status_rank", "days_remaining", "stock_to_rop_ratio"],
        ascending=[True, True, True]
    ).reset_index(drop=True)
    df_decisions["urgency_rank"] = np.arange(1, len(df_decisions) + 1)
    df_decisions.drop(columns=["status_rank"], inplace=True)

    # =========================================================================
    # LOUD SANITY CHECKS (MUST FAIL WITH RUNTIMEERROR IF VIOLATED)
    # =========================================================================
    logger.info("\n--- Performing Loud Sanity Checks ---")

    # 1. Total count
    if len(df_decisions) != 75:
        raise RuntimeError(f"Sanity Check Failed: Expected 75 pairs, got {len(df_decisions)}")

    # 2. No NaN values in critical decision metrics
    critical_cols = [
        "current_stock", "reorder_point_rop", "safety_stock_ss",
        "demand_rate_d", "predicted_lead_time_days", "days_remaining", "urgency_rank"
    ]
    nan_counts = df_decisions[critical_cols].isna().sum().to_dict()
    if any(v > 0 for v in nan_counts.values()):
        raise RuntimeError(f"Sanity Check Failed: NaN values detected in critical columns: {nan_counts}")

    # 3. SS >= 0
    min_ss = df_decisions["safety_stock_ss"].min()
    if min_ss < 0.0:
        raise RuntimeError(f"Sanity Check Failed: Negative safety stock detected (min = {min_ss})")

    # 4. ROP >= D * L
    rop_diff = df_decisions["reorder_point_rop"] - (df_decisions["demand_rate_d"] * df_decisions["predicted_lead_time_days"])
    if (rop_diff < -0.05).any():
        worst = rop_diff.min()
        raise RuntimeError(f"Sanity Check Failed: ROP < D * L detected (worst difference = {worst})")

    # 5. Status distribution
    status_counts = df_decisions["status"].value_counts().to_dict()
    logger.info(f"Status distribution: {status_counts}")
    if set(status_counts.keys()) - {"OK", "REORDER", "CRITICAL"}:
        raise RuntimeError(f"Sanity Check Failed: Unknown status in {status_counts.keys()}")

    logger.info("  [OK] All sanity assertions passed successfully.")

    # 7. Save Artifacts
    artifacts_dir = Path("artifacts")
    inv_dir = artifacts_dir / "inventory"
    metrics_dir = artifacts_dir / "metrics"
    inv_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)

    parquet_out = inv_dir / "reorder_table.parquet"
    json_out = inv_dir / "reorder_table.json"
    summary_out = metrics_dir / "decision_layer_summary.json"

    df_decisions.to_parquet(parquet_out, index=False, engine="pyarrow")
    logger.info(f"Saved reorder decision table -> {parquet_out}")

    # JSON export with pretty structure
    decisions_list = df_decisions.to_dict(orient="records")
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(decisions_list, f, indent=2)
    logger.info(f"Saved JSON decision table -> {json_out}")

    summary_payload = {
        "timestamp": datetime.now().isoformat(),
        "total_pairs": len(df_decisions),
        "as_of_date": as_of_date_str,
        "status_breakdown": status_counts,
        "weak_normal_pairs_count": int(df_decisions["weak_normal_assumption"].sum()),
        "low_confidence_pairs_count": int(df_decisions["low_confidence"].sum()),
        "extrapolation_pairs_count": int(df_decisions["is_quantity_extrapolation"].sum()),
        "mean_lead_time_days": round(float(df_decisions["predicted_lead_time_days"].mean()), 2),
        "mean_safety_stock_units": round(float(df_decisions["safety_stock_ss"].mean()), 2),
        "policy_parameters": {
            "service_level": service_level,
            "z_score": round(z_score, 4),
            "cover_days": cover_days,
            "ordering_cost_fixed": order_cost,
            "holding_cost_annual_rate": holding_rate,
            "unit_cost": unit_cost,
        },
    }
    with open(summary_out, "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, indent=2)
    logger.info(f"Saved decision layer summary -> {summary_out}")

    # 8. Print Summary Table
    logger.info("\n" + "=" * 90)
    logger.info(" PHASE 4 INVENTORY DECISION LAYER SUMMARY")
    logger.info("=" * 90)
    logger.info(f"Status Counts: CRITICAL: {status_counts.get('CRITICAL', 0)} | REORDER: {status_counts.get('REORDER', 0)} | OK: {status_counts.get('OK', 0)}")
    logger.info(f"Special Flags: Weak Normal Assumption: {summary_payload['weak_normal_pairs_count']} | Low Confidence: {summary_payload['low_confidence_pairs_count']} | Qty Extrapolations: {summary_payload['extrapolation_pairs_count']}")
    logger.info("-" * 90)
    logger.info("TOP 5 MOST URGENT REORDER PAIRS (Immediate Stockout Risk):")
    logger.info(f"{'Rank':<5} | {'Material':<16} | {'Area':<18} | {'Stock':<7} | {'Days Rem':<9} | {'L':<5} | {'ROP':<7} | {'Status':<9}")
    logger.info("-" * 90)
    for _, r in df_decisions.head(5).iterrows():
        logger.info(f"{r['urgency_rank']:<5} | {r['material']:<16} | {r['area']:<18} | {r['current_stock']:>7.1f} | {r['days_remaining']:>7.1f} d | {r['predicted_lead_time_days']:>4.1f}d | {r['reorder_point_rop']:>7.1f} | {r['status']:<9}")

    logger.info("-" * 90)
    logger.info("TOP 5 LEAST URGENT PAIRS (Healthy Stock Buffer):")
    logger.info(f"{'Rank':<5} | {'Material':<16} | {'Area':<18} | {'Stock':<7} | {'Days Rem':<9} | {'L':<5} | {'ROP':<7} | {'Status':<9}")
    logger.info("-" * 90)
    for _, r in df_decisions.tail(5).iterrows():
        logger.info(f"{r['urgency_rank']:<5} | {r['material']:<16} | {r['area']:<18} | {r['current_stock']:>7.1f} | {r['days_remaining']:>7.1f} d | {r['predicted_lead_time_days']:>4.1f}d | {r['reorder_point_rop']:>7.1f} | {r['status']:<9}")
    logger.info("=" * 90)


if __name__ == "__main__":
    main()
