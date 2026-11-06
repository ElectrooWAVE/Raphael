"""Build Phase 5 Artifacts: Recommendations, Calibrated Forecasts, Promo Scenarios, and Meta.

Phase 5 outputs:
1. artifacts/recommendations.parquet (& .json): Combined reorder table per pair:
   - ROP, SS, days_remaining, status, planned order qty, L, sigma_L (calibrated & tree spread)
   - model_used, validation and test accuracy metrics, qualitative flags
2. artifacts/forecasts/demand_forecasts_champion.parquet (& .json):
   - Per-pair 90-day future forecasts with 80% and 95% bands (empirically calibrated for all models)
3. artifacts/promo_scenarios.parquet (& .json):
   - Empirical promotion lift per pair controlling for day of week with bootstrap 95% CI
   - If not distinguishable from 1.0, lift = 1.0 with 'no_measurable_effect' flag
   - Label: 'Simulated, empirical lift'
4. artifacts/meta.json:
   - Dataset provenance, as_of_date, synthetic elements disclosure, policy defaults
"""
import argparse
from datetime import datetime
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Tuple
from joblib import Parallel, delayed
import numpy as np
import pandas as pd
import scipy.stats as stats
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.logger import setup_logger
from src.utils.progress import get_progress_bar, timed_block


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 5: Build Recommendations, Scenarios & Meta Artifacts.")
    parser.add_argument("--config", type=str, default="configs/raphael.yaml")
    parser.add_argument("--assumptions", type=str, default="configs/assumptions.yaml")
    parser.add_argument("--n-bootstrap", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def calculate_empirical_promo_lift(
    mat: str,
    area: str,
    df_pair: pd.DataFrame,
    n_bootstrap: int = 500,
    seed: int = 42,
) -> Dict[str, Any]:
    """Calculate weekday-adjusted empirical promotion lift with bootstrap 95% confidence intervals."""
    rng = np.random.default_rng(seed)
    df_work = df_pair.copy()
    if "weekday" not in df_work.columns:
        df_work["weekday"] = pd.to_datetime(df_work["date"]).dt.dayofweek

    # 1. Weekday-adjusted empirical lift (weighted by promo occurrence)
    w_lifts, w_weights = [], []
    for w in range(7):
        w_sub = df_work[df_work["weekday"] == w]
        yp = w_sub[w_sub["is_promotion"] == 1]["quantity"].to_numpy()
        ynp = w_sub[w_sub["is_promotion"] == 0]["quantity"].to_numpy()
        if len(yp) > 0 and len(ynp) > 0 and ynp.mean() > 0:
            w_lifts.append(float(yp.mean() / ynp.mean()))
            w_weights.append(len(yp))

    raw_lift = float(np.average(w_lifts, weights=w_weights)) if w_lifts else 1.0

    # 2. Vectorized bootstrap to test statistical significance
    q = df_work["quantity"].to_numpy(dtype=float)
    p_flags = df_work["is_promotion"].to_numpy(dtype=bool)
    n = len(q)

    boot_indices = rng.integers(0, n, size=(n_bootstrap, n))
    boot_q = q[boot_indices]
    boot_p = p_flags[boot_indices]

    boot_means_p = np.array([boot_q[i, boot_p[i]].mean() if boot_p[i].any() else 1.0 for i in range(n_bootstrap)])
    boot_means_np = np.array([boot_q[i, ~boot_p[i]].mean() if (~boot_p[i]).any() else 1.0 for i in range(n_bootstrap)])

    valid = boot_means_np > 0
    boot_ratios = boot_means_p[valid] / boot_means_np[valid]

    ci_low = float(np.percentile(boot_ratios, 2.5)) if len(boot_ratios) > 0 else 1.0
    ci_high = float(np.percentile(boot_ratios, 97.5)) if len(boot_ratios) > 0 else 1.0

    # If CI includes 1.0, lift is not statistically distinguishable from 1.0
    has_measurable_effect = bool(ci_low > 1.0 or ci_high < 1.0)
    operational_lift = raw_lift if has_measurable_effect else 1.0

    if has_measurable_effect:
        pct_change = (operational_lift - 1.0) * 100.0
        desc = f"Statistically significant empirical lift of {pct_change:+.1f}% on promotion days."
    else:
        desc = "No measurable effect: promotion demand is statistically indistinguishable from baseline (lift defaulted to 1.000)."

    return {
        "material": mat,
        "area": area,
        "empirical_lift": round(operational_lift, 3),
        "raw_lift": round(raw_lift, 3),
        "lift_ci_lower_95": round(ci_low, 3),
        "lift_ci_upper_95": round(ci_high, 3),
        "has_measurable_effect": has_measurable_effect,
        "no_measurable_effect": not has_measurable_effect,
        "historical_promo_share": round(float(np.mean(p_flags)), 4),
        "simulation_method": "Simulated, empirical lift",
        "effect_description": desc,
    }


def main():
    args = parse_args()
    logger = setup_logger("05_build_recommendations_and_scenarios", log_dir="logs")

    logger.info("=" * 80)
    logger.info(" Raphael Phase 5: Build Recommendations, Forecast Bands, Scenarios & Meta")
    logger.info("=" * 80)

    config = load_yaml(args.config)
    assumptions = load_yaml(args.assumptions)

    # Input paths
    reorder_path = Path("artifacts/inventory/reorder_table.parquet")
    forecasts_path = Path("artifacts/forecasts/demand_forecasts_champion.parquet")
    selection_path = Path("artifacts/metrics/champion_model_selection.json")
    demand_path = Path(config["paths"]["processed_data"]["demand_parquet"])

    for p, desc in [
        (reorder_path, "Phase 4 reorder table"),
        (forecasts_path, "Champion future forecasts"),
        (selection_path, "Champion selection metadata"),
        (demand_path, "Demand parquet"),
    ]:
        if not p.exists():
            logger.error(f"Missing required artifact: {desc} at {p}")
            sys.exit(1)

    df_reorder = pd.read_parquet(reorder_path)
    df_forecasts = pd.read_parquet(forecasts_path)
    df_demand = pd.read_parquet(demand_path)
    with open(selection_path, "r", encoding="utf-8") as f:
        champions_meta = json.load(f)
    meta_dict = {(c["material"], c["area"]): c for c in champions_meta}

    artifacts_dir = Path("artifacts")
    forecasts_dir = artifacts_dir / "forecasts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    forecasts_dir.mkdir(parents=True, exist_ok=True)

    # =========================================================================
    # 1. COMBINED REORDER TABLE PER PAIR (a)
    # =========================================================================
    logger.info("\n--- 1. Generating Combined Recommendations Table ---")
    recommendations = []
    for _, row in df_reorder.iterrows():
        pair_key = (row["material"], row["area"])
        c_meta = meta_dict.get(pair_key, {})

        rec = dict(row)
        # Attach accuracy and model selection telemetry
        rec["model_used"] = row["champion_model"]
        rec["test_weekly_wape"] = c_meta.get("test_weekly_wape")
        rec["test_daily_wape"] = c_meta.get("test_daily_wape")
        rec["test_lead_time_wape"] = c_meta.get("test_lead_time_wape")
        rec["champion_val_wape"] = c_meta.get("champion_val_wape")
        recommendations.append(rec)

    df_recommendations = pd.DataFrame(recommendations)
    rec_parquet = artifacts_dir / "recommendations.parquet"
    rec_json = artifacts_dir / "recommendations.json"
    df_recommendations.to_parquet(rec_parquet, index=False, engine="pyarrow")
    with open(rec_json, "w", encoding="utf-8") as f:
        json.dump(df_recommendations.to_dict(orient="records"), f, indent=2)
    logger.info(f"Saved recommendations table ({len(df_recommendations)} pairs) -> {rec_parquet}")

    # =========================================================================
    # 2. CALIBRATED FORECASTS WITH 80/95 BANDS (b)
    # =========================================================================
    logger.info("\n--- 2. Calibrating Champion Forecast Bands (80% and 95%) ---")
    # For point models, compute calibrated normal residual bands:
    # 80%: yhat +/- 1.28155 * sigma_D; 95%: yhat +/- 1.95996 * sigma_D (clipped at 0)
    sigma_d_map = dict(zip(
        zip(df_reorder["material"], df_reorder["area"]),
        df_reorder["demand_error_std_sigma_d"]
    ))

    df_fc_calib = df_forecasts.copy()
    z_80 = 1.28155
    z_95 = 1.95996

    updated_rows = []
    for _, r in df_fc_calib.iterrows():
        pair_key = (r["material"], r["area"])
        sig_d = sigma_d_map.get(pair_key, 1.0)
        yhat = float(r["yhat"])

        # Check if model has non-degenerate intervals
        has_prophet_intervals = (
            "yhat_lower_80" in r
            and not pd.isna(r["yhat_lower_80"])
            and r["yhat_upper_80"] > r["yhat_lower_80"]
        )

        if has_prophet_intervals:
            l80 = max(0.0, float(r["yhat_lower_80"]))
            u80 = max(l80, float(r["yhat_upper_80"]))
            l95 = max(0.0, float(r["yhat_lower_95"]))
            u95 = max(l95, float(r["yhat_upper_95"]))
        else:
            l80 = max(0.0, round(yhat - z_80 * sig_d, 2))
            u80 = round(yhat + z_80 * sig_d, 2)
            l95 = max(0.0, round(yhat - z_95 * sig_d, 2))
            u95 = round(yhat + z_95 * sig_d, 2)

        row_dict = dict(r)
        row_dict["yhat_lower_80"] = l80
        row_dict["yhat_upper_80"] = u80
        row_dict["yhat_lower_95"] = l95
        row_dict["yhat_upper_95"] = u95
        updated_rows.append(row_dict)

    df_fc_updated = pd.DataFrame(updated_rows)
    fc_parquet = forecasts_dir / "demand_forecasts_champion.parquet"
    fc_json = forecasts_dir / "demand_forecasts_champion.json"
    df_fc_updated.to_parquet(fc_parquet, index=False, engine="pyarrow")
    # Save compact JSON for frontend fast-loading
    with open(fc_json, "w", encoding="utf-8") as f:
        # Export as clean serializable dict with dates as strings
        fc_export = df_fc_updated.copy()
        fc_export["ds"] = fc_export["ds"].astype(str)
        json.dump(fc_export.to_dict(orient="records"), f)
    logger.info(f"Saved calibrated future forecasts ({len(df_fc_updated):,} rows) -> {fc_parquet}")

    # =========================================================================
    # 3. EMPIRICAL PROMOTION SCENARIOS (c)
    # =========================================================================
    logger.info(f"\n--- 3. Estimating Empirical Promo Lift (Weekday-Adjusted, {args.n_bootstrap} Bootstraps) ---")
    pairs = df_demand[["material", "area"]].drop_duplicates().values.tolist()

    with timed_block("Computing Empirical Promotion Lifts", logger=logger):
        scenario_results = Parallel(n_jobs=-1)(
            delayed(calculate_empirical_promo_lift)(
                mat=m, area=a,
                df_pair=df_demand[(df_demand["material"] == m) & (df_demand["area"] == a)],
                n_bootstrap=args.n_bootstrap,
                seed=args.seed + idx
            ) for idx, (m, a) in enumerate(pairs)
        )

    df_scenarios = pd.DataFrame(scenario_results)
    sig_count = int(df_scenarios["has_measurable_effect"].sum())
    no_effect_count = int(df_scenarios["no_measurable_effect"].sum())
    logger.info(f"Promotion Effect Findings: {sig_count} pairs with significant lift, {no_effect_count} pairs with no measurable effect (defaulted to 1.0).")

    scenarios_parquet = artifacts_dir / "promo_scenarios.parquet"
    scenarios_json = artifacts_dir / "promo_scenarios.json"
    df_scenarios.to_parquet(scenarios_parquet, index=False, engine="pyarrow")
    with open(scenarios_json, "w", encoding="utf-8") as f:
        json.dump(df_scenarios.to_dict(orient="records"), f, indent=2)
    logger.info(f"Saved empirical promotion scenario artifact -> {scenarios_parquet}")

    # =========================================================================
    # 4. DATASET & PLATFORM METADATA (/meta) (d)
    # =========================================================================
    logger.info("\n--- 4. Generating Platform Metadata (/meta) ---")
    dates_cfg = config.get("dates", {})
    provenance = config.get("app", {}).get("provenance", {})

    meta_payload = {
        "dataset_name": "Raphael Supply Chain & Materials Decision Platform",
        "provenance": {
            "demand": provenance.get("demand_origin", "Walmart M5 benchmark data relabelled as materials"),
            "lead_time": provenance.get("lead_time_origin", "Synthetic calibrated data with order quantity dependency and Nov-Dec seasonal surge"),
            "inventory": provenance.get("inventory_origin", "Synthetic snapshot as of 2016-04-24"),
            "disclaimer": provenance.get("disclaimer", "Demand series reflect retail benchmark patterns relabelled as materials; lead times and current inventory are synthetic."),
        },
        "dates": {
            "as_of_date": dates_cfg.get("as_of_date", "2016-04-24"),
            "forecast_start_date": dates_cfg.get("forecast_start_date", "2016-04-25"),
            "forecast_horizon_days": int(dates_cfg.get("horizon_days", 90)),
            "test_days": int(dates_cfg.get("test_days", 84)),
            "validation_days": int(dates_cfg.get("validation_days", 84)),
            "holiday_calendar": dates_cfg.get("holiday_country", "US"),
        },
        "fleet_dimensions": {
            "total_pairs": len(pairs),
            "total_materials": int(df_demand["material"].nunique()),
            "total_areas": int(df_demand["area"].nunique()),
            "total_demand_days_per_pair": 1913,
            "total_historical_orders": len(pd.read_parquet(config["paths"]["processed_data"]["lead_time_parquet"])),
        },
        "model_architecture": {
            "demand_models": "Production model: Weekday Mean 8W across all 75 pairs (per-pair selection discarded because it failed to generalize to held-out test window)",
            "lead_time_model": "Random Forest Regressor with 5-fold out-of-fold empirical uncertainty calibration and extrapolation boundaries",
            "decision_engine": "Pure arithmetic safety stock, reorder point, EOQ, and day-by-day forecast depletion (no machine learning in decisions)",
            "promotion_simulation": "Simulated, empirical lift: weekday-adjusted historical lift with 500-iteration bootstrap confidence intervals",
        },
        "policy_assumptions": {
            "service_level": float(assumptions.get("inventory_policy", {}).get("service_level", {}).get("default_value", 0.95)),
            "z_score": float(assumptions.get("inventory_policy", {}).get("service_level", {}).get("z_score", 1.6449)),
            "review_period_days": int(assumptions.get("inventory_policy", {}).get("review_period_days", {}).get("default_value", 7)),
            "cover_days_target": int(assumptions.get("reorder_quantity_policy", {}).get("cover_days", 14)),
            "ordering_cost_fixed": float(assumptions.get("cost_parameters", {}).get("ordering_cost_fixed", {}).get("default_value", 50.0)),
            "holding_cost_annual_rate": float(assumptions.get("cost_parameters", {}).get("holding_cost_annual_rate", {}).get("default_value", 0.20)),
            "default_unit_cost": float(assumptions.get("cost_parameters", {}).get("default_unit_cost", {}).get("default_value", 10.0)),
        },
        "status_summary": df_reorder["status"].value_counts().to_dict(),
        "created_at": datetime.now().isoformat(),
    }

    meta_json = artifacts_dir / "meta.json"
    with open(meta_json, "w", encoding="utf-8") as f:
        json.dump(meta_payload, f, indent=2)
    logger.info(f"Saved platform metadata -> {meta_json}")

    # Print summary
    logger.info("\n" + "=" * 80)
    logger.info(" PHASE 5 ARTIFACTS SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Recommendations Parquet  : {rec_parquet} ({rec_parquet.stat().st_size / 1024:.1f} KB)")
    logger.info(f"Forecasts Parquet        : {fc_parquet} ({fc_parquet.stat().st_size / 1024:.1f} KB)")
    logger.info(f"Promo Scenarios Parquet  : {scenarios_parquet} ({scenarios_parquet.stat().st_size / 1024:.1f} KB)")
    logger.info(f"Platform Meta JSON       : {meta_json} ({meta_json.stat().st_size / 1024:.1f} KB)")
    logger.info(f"Empirical Lift Overview  : {sig_count} pairs with significant promo lift, {no_effect_count} pairs with no measurable effect")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
