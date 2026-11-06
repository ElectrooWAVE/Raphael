"""Train Prophet demand forecasting models for Raphael (Phase 2).

Fits Prophet per (material, area) pair in parallel across CPU cores with:
- US country holidays and is_promotion regressor
- Non-negative clipping at 0.0 for forecasts and prediction intervals (80% and 95%)
- Held-out test evaluation on the last test_days against Naive and Seasonal Naive baselines
- Multi-level evaluation metrics: Daily, Weekly, and Lead-Time Window
- Low-confidence flagging for intermittent pairs where Prophet loses to a baseline
- Checkpointing per pair with --force support and --limit option
- Silences cmdstanpy noise while maintaining a single, clean overall tqdm progress bar
"""
import argparse
import io
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import joblib
from joblib import Parallel, delayed
import numpy as np
import pandas as pd
import yaml

# Suppress cmdstanpy and prophet warnings before imports
_old_stderr = sys.stderr
sys.stderr = io.StringIO()
try:
    import cmdstanpy
    c_log = cmdstanpy.utils.get_logger()
    c_log.setLevel(logging.ERROR)
    for h in c_log.handlers[:]:
        c_log.removeHandler(h)
    c_log.addHandler(logging.NullHandler())
    logging.getLogger("prophet").setLevel(logging.ERROR)
finally:
    sys.stderr = _old_stderr

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.metrics import evaluate_forecast_multi_level
from src.models.baselines import NaiveModel, SeasonalNaiveModel
from src.models.demand_prophet import ProphetDemandModel
from src.utils.checkpoint import CheckpointManager
from src.utils.logger import setup_logger
from src.utils.progress import get_progress_bar, timed_block


def parse_args() -> argparse.Namespace:
    """Parse CLI options for Prophet demand model training."""
    parser = argparse.ArgumentParser(
        description="Train Prophet demand models per (material, area) pair."
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/raphael.yaml",
        help="Path to YAML configuration file (default: configs/raphael.yaml)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of pairs to run (e.g. --limit 3 for quick test, default: all 75)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force recomputation of all pairs, ignoring existing checkpoints",
    )
    parser.add_argument(
        "--n_jobs",
        type=int,
        default=-1,
        help="Number of parallel worker processes (-1 uses all logical cores)",
    )
    parser.add_argument(
        "--future-promo",
        type=str,
        choices=["zero", "deterministic"],
        default="zero",
        help="Future promotion regressor strategy: 'zero' (default) or 'deterministic' (SNAP calendar schedule)",
    )
    return parser.parse_args()


def load_config(config_path: str) -> dict:
    """Load configuration dictionary."""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_deterministic_promo_flag(area: str, dates: pd.Series) -> pd.Series:
    """Return 0 or 1 matching the verified SNAP distribution schedule for each state."""
    day_of_month = dates.dt.day
    if "California" in area:
        # CA: Days 1 to 10 of each month
        return day_of_month.isin(range(1, 11)).astype(int)
    elif "Texas" in area:
        # TX: Days 1, 3, 5, 6, 7, 9, 11, 12, 13, 15
        return day_of_month.isin([1, 3, 5, 6, 7, 9, 11, 12, 13, 15]).astype(int)
    elif "Wisconsin" in area:
        # WI: Days 2, 3, 5, 6, 8, 9, 11, 12, 14, 15
        return day_of_month.isin([2, 3, 5, 6, 8, 9, 11, 12, 14, 15]).astype(int)
    return pd.Series(0, index=dates.index)


def process_single_pair(
    pair_info: Tuple[str, str],
    df_pair_demand: pd.DataFrame,
    lead_time_days: float,
    test_days: int,
    horizon_days: int,
    as_of_date_str: str,
    future_promo_mode: str,
) -> Dict[str, Any]:
    """Train, evaluate, and forecast for one (material, area) pair."""
    # Worker-level Stan silencing
    try:
        c_log = cmdstanpy.utils.get_logger()
        c_log.setLevel(logging.ERROR)
        for h in c_log.handlers[:]:
            c_log.removeHandler(h)
        c_log.addHandler(logging.NullHandler())
        logging.getLogger("prophet").setLevel(logging.ERROR)
    except Exception:
        pass

    material, area = pair_info
    df_pair = df_pair_demand.sort_values("date").reset_index(drop=True)

    # 1. Train / Test Split
    train_df = df_pair.iloc[:-test_days].copy()
    test_df = df_pair.iloc[-test_days:].copy()

    # Format for Prophet
    train_prophet = pd.DataFrame({
        "ds": train_df["date"],
        "y": train_df["quantity"],
        "is_promotion": train_df["is_promotion"],
    })
    test_prophet = pd.DataFrame({
        "ds": test_df["date"],
        "is_promotion": test_df["is_promotion"],
    })

    # 2. Fit and Evaluate on Held-out Test Set
    # A. Prophet
    m_eval = ProphetDemandModel(
        growth="linear",
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
        country_holidays="US",
        clip_lower_bound=0.0,
    )
    m_eval.fit(train_prophet)
    prophet_test_preds = m_eval.predict(test_prophet)

    # B. Baselines
    naive = NaiveModel().fit(train_prophet, target_col="y")
    naive_test_preds = naive.predict(test_prophet)

    snaive = SeasonalNaiveModel(season_length=7).fit(train_prophet, target_col="y")
    snaive_test_preds = snaive.predict(test_prophet)

    # Combine test predictions for evaluation
    eval_df = test_prophet.copy()
    eval_df["y"] = test_df["quantity"].values
    eval_df["yhat"] = prophet_test_preds["yhat"].values
    eval_df["yhat_lower_80"] = prophet_test_preds["yhat_lower_80"].values
    eval_df["yhat_upper_80"] = prophet_test_preds["yhat_upper_80"].values
    eval_df["yhat_lower_95"] = prophet_test_preds["yhat_lower_95"].values
    eval_df["yhat_upper_95"] = prophet_test_preds["yhat_upper_95"].values

    eval_naive_df = test_prophet.copy()
    eval_naive_df["y"] = test_df["quantity"].values
    eval_naive_df["yhat"] = naive_test_preds["yhat"].values

    eval_snaive_df = test_prophet.copy()
    eval_snaive_df["y"] = test_df["quantity"].values
    eval_snaive_df["yhat"] = snaive_test_preds["yhat"].values

    # Multi-level evaluation (Daily, Weekly, Lead-time window)
    window_days = max(1, int(round(lead_time_days)))
    metrics_prophet = evaluate_forecast_multi_level(eval_df, lead_time_days=window_days)
    metrics_naive = evaluate_forecast_multi_level(eval_naive_df, lead_time_days=window_days)
    metrics_snaive = evaluate_forecast_multi_level(eval_snaive_df, lead_time_days=window_days)

    # Compare Prophet against baselines
    weekly_wape_prophet = metrics_prophet["weekly"]["wape"]
    weekly_wape_naive = metrics_naive["weekly"]["wape"]
    weekly_wape_snaive = metrics_snaive["weekly"]["wape"]
    best_baseline_weekly_wape = min(weekly_wape_naive, weekly_wape_snaive)

    # Flag if Prophet loses to a baseline on primary weekly WAPE
    loses_to_baseline = weekly_wape_prophet > best_baseline_weekly_wape
    baseline_winner = "seasonal_naive" if weekly_wape_snaive <= weekly_wape_naive else "naive"

    # 3. Fit Final Production Model on FULL 1,913 days
    full_prophet_df = pd.DataFrame({
        "ds": df_pair["date"],
        "y": df_pair["quantity"],
        "is_promotion": df_pair["is_promotion"],
    })
    m_full = ProphetDemandModel(
        growth="linear",
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
        country_holidays="US",
        clip_lower_bound=0.0,
    )
    m_full.fit(full_prophet_df)

    # 4. Generate Future Forecast (90 days starting day after as_of_date)
    as_of_dt = pd.to_datetime(as_of_date_str)
    future_dates = pd.date_range(as_of_dt + timedelta(days=1), periods=horizon_days, freq="D")

    if future_promo_mode == "deterministic":
        future_promo = get_deterministic_promo_flag(area, pd.Series(future_dates))
    else:
        future_promo = pd.Series(0, index=range(horizon_days))

    future_df = pd.DataFrame({
        "ds": future_dates,
        "is_promotion": future_promo.values,
    })
    future_preds = m_full.predict(future_df)
    future_preds["material"] = material
    future_preds["area"] = area

    # Test predictions dataframe for artifact export
    test_export = eval_df.copy()
    test_export["material"] = material
    test_export["area"] = area
    test_export["yhat_naive"] = naive_test_preds["yhat"].values
    test_export["yhat_seasonal_naive"] = snaive_test_preds["yhat"].values

    return {
        "material": material,
        "area": area,
        "lead_time_days": lead_time_days,
        "window_days": window_days,
        "promo_coef": m_full.promo_coef,
        "residual_std": m_full.residual_std,
        "metrics": {
            "prophet": metrics_prophet,
            "naive": metrics_naive,
            "seasonal_naive": metrics_snaive,
        },
        "loses_to_baseline": loses_to_baseline,
        "baseline_winner": baseline_winner,
        "model_used": "prophet",
        "low_confidence": bool(loses_to_baseline),
        "future_forecast": future_preds,
        "test_eval": test_export,
    }


def main():
    args = parse_args()
    logger = setup_logger("02_train_demand_prophet", log_dir="logs")

    logger.info("=" * 70)
    logger.info(" Raphael Phase 2: Demand Forecasting Model Training (Prophet)")
    logger.info("=" * 70)

    config = load_config(args.config)
    as_of_date = config["dates"]["as_of_date"]
    test_days = int(config["dates"].get("test_days", 90))
    horizon_days = int(config["dates"].get("horizon_days", 90))

    # Load preprocessed datasets
    demand_parquet = config["paths"]["processed_data"]["demand_parquet"]
    lead_time_parquet = config["paths"]["processed_data"]["lead_time_parquet"]

    if not Path(demand_parquet).exists():
        logger.error(f"Processed demand file missing: {demand_parquet}. Run Phase 1 first.")
        sys.exit(1)

    df_demand = pd.read_parquet(demand_parquet)
    df_lt = pd.read_parquet(lead_time_parquet)

    # Compute mean lead time per pair to set the lead-time evaluation window
    lt_means = df_lt.groupby(["material", "area"])["lead_time_days"].mean().to_dict()

    # Get unique pairs
    pairs = df_demand[["material", "area"]].drop_duplicates().values.tolist()
    if args.limit:
        pairs = pairs[:args.limit]
        logger.info(f"Limit applied: running on first {len(pairs)} pairs.")

    logger.info(f"Total pairs to process: {len(pairs)}")
    logger.info(f"Future promotion strategy: {args.future_promo}")
    logger.info(f"Parallel jobs (CPU cores): {args.n_jobs}")

    # Checkpointing
    chk = CheckpointManager(
        "02_train_demand_prophet",
        checkpoint_dir=config["paths"]["checkpoints"]["dir"],
        force=args.force,
        logger=logger,
    )

    completed_unit_ids = chk.get_completed_units()
    logger.info(f"Existing checkpoints: {len(completed_unit_ids)} pairs already completed.")

    pairs_to_run = []
    cached_results = []
    for mat, area in pairs:
        unit_id = f"{mat}_{area}"
        if chk.is_completed(unit_id):
            cached_results.append(chk.load_unit(unit_id))
        else:
            pairs_to_run.append((mat, area))

    logger.info(f"Pairs remaining to train: {len(pairs_to_run)}")

    new_results = []
    failed_pairs = []

    if pairs_to_run:
        # Wrap execution with unified tqdm progress bar
        with timed_block(f"Prophet Training ({len(pairs_to_run)} pairs)", logger=logger):
            pbar = get_progress_bar(total=len(pairs_to_run), desc="Fitting Prophet series", unit="pair")

            def worker_task(mat: str, area: str):
                unit_id = f"{mat}_{area}"
                try:
                    df_sub = df_demand[(df_demand["material"] == mat) & (df_demand["area"] == area)]
                    lt_val = lt_means.get((mat, area), 5.0)
                    res = process_single_pair(
                        pair_info=(mat, area),
                        df_pair_demand=df_sub,
                        lead_time_days=lt_val,
                        test_days=test_days,
                        horizon_days=horizon_days,
                        as_of_date_str=as_of_date,
                        future_promo_mode=args.future_promo,
                    )
                    chk.save_unit(unit_id, res)
                    return True, res, None
                except Exception as e:
                    return False, {"material": mat, "area": area}, str(e)

            # Parallel dispatch with generator
            parallel_runner = Parallel(n_jobs=args.n_jobs, return_as="generator")
            gen = parallel_runner(delayed(worker_task)(mat, area) for mat, area in pairs_to_run)

            for success, data, err_msg in gen:
                if success:
                    new_results.append(data)
                else:
                    failed_pairs.append({"pair": data, "error": err_msg})
                    logger.error(f"Failed pair {data}: {err_msg}")
                pbar.update(1)

            pbar.close()

    all_results = cached_results + new_results

    if failed_pairs:
        failed_path = Path("artifacts/failed_pairs.json")
        with open(failed_path, "w", encoding="utf-8") as f:
            json.dump(failed_pairs, f, indent=2)
        logger.error(f"{len(failed_pairs)} pairs failed. Written to {failed_path}")

    # Build and Save Artifacts
    artifacts_dir = Path("artifacts")
    forecasts_dir = artifacts_dir / "forecasts"
    metrics_dir = artifacts_dir / "metrics"
    forecasts_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)

    # 1. Stack Future Forecasts
    all_future_dfs = [r["future_forecast"] for r in all_results]
    if all_future_dfs:
        df_forecasts_stacked = pd.concat(all_future_dfs, ignore_index=True)
        forecasts_path = forecasts_dir / "demand_forecasts.parquet"
        df_forecasts_stacked.to_parquet(forecasts_path, index=False, engine="pyarrow")
        logger.info(f"Saved future forecasts ({len(df_forecasts_stacked):,} rows) -> {forecasts_path}")

    # 2. Stack Test Evaluations
    all_test_dfs = [r["test_eval"] for r in all_results]
    if all_test_dfs:
        df_test_stacked = pd.concat(all_test_dfs, ignore_index=True)
        test_eval_path = forecasts_dir / "demand_test_eval.parquet"
        df_test_stacked.to_parquet(test_eval_path, index=False, engine="pyarrow")
        logger.info(f"Saved test evaluation data ({len(df_test_stacked):,} rows) -> {test_eval_path}")

    # 3. Compile Metrics Summary & Leaderboard
    summary_records = []
    for r in all_results:
        m_prophet = r["metrics"]["prophet"]
        m_naive = r["metrics"]["naive"]
        m_snaive = r["metrics"]["seasonal_naive"]

        summary_records.append({
            "material": r["material"],
            "area": r["area"],
            "lead_time_days": round(float(r["lead_time_days"]), 2),
            "window_days": r["window_days"],
            "promo_coef": round(float(r["promo_coef"]), 4),
            "residual_std": round(float(r["residual_std"]), 4),
            "low_confidence": r["low_confidence"],
            "loses_to_baseline": r["loses_to_baseline"],
            "baseline_winner": r["baseline_winner"],
            "daily_wape": m_prophet["daily"]["wape"],
            "weekly_wape": m_prophet["weekly"]["wape"],
            "lead_time_window_wape": m_prophet["lead_time_window"]["wape"],
            "weekly_rmse": m_prophet["weekly"]["rmse"],
            "weekly_bias": m_prophet["weekly"]["bias"],
            "coverage_80": m_prophet["daily"].get("coverage_80"),
            "coverage_95": m_prophet["daily"].get("coverage_95"),
            "baseline_naive_weekly_wape": m_naive["weekly"]["wape"],
            "baseline_snaive_weekly_wape": m_snaive["weekly"]["wape"],
        })

    df_summary = pd.DataFrame(summary_records)
    avg_daily_wape = float(df_summary["daily_wape"].mean()) if not df_summary.empty else 0.0
    avg_weekly_wape = float(df_summary["weekly_wape"].mean()) if not df_summary.empty else 0.0
    avg_lt_wape = float(df_summary["lead_time_window_wape"].mean()) if not df_summary.empty else 0.0
    avg_naive_weekly_wape = float(df_summary["baseline_naive_weekly_wape"].mean()) if not df_summary.empty else 0.0
    avg_snaive_weekly_wape = float(df_summary["baseline_snaive_weekly_wape"].mean()) if not df_summary.empty else 0.0
    low_conf_count = int(df_summary["low_confidence"].sum()) if not df_summary.empty else 0

    evaluation_artifact = {
        "timestamp": datetime.now().isoformat(),
        "total_pairs_evaluated": len(df_summary),
        "test_days": test_days,
        "as_of_date": as_of_date,
        "overall_averages": {
            "prophet_daily_wape": round(avg_daily_wape, 4),
            "prophet_weekly_wape": round(avg_weekly_wape, 4),
            "prophet_lead_time_window_wape": round(avg_lt_wape, 4),
            "baseline_naive_weekly_wape": round(avg_naive_weekly_wape, 4),
            "baseline_seasonal_naive_weekly_wape": round(avg_snaive_weekly_wape, 4),
            "pairs_losing_to_baseline_count": low_conf_count,
            "pairs_losing_to_baseline_share": round(low_conf_count / max(1, len(df_summary)), 4),
        },
        "pairs_detail": summary_records,
    }

    metrics_file = metrics_dir / "demand_model_evaluation.json"
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(evaluation_artifact, f, indent=2)

    logger.info(f"Saved evaluation metrics artifact -> {metrics_file}")
    logger.info("\n" + "=" * 70)
    logger.info(f" PHASE 2 EVALUATION SUMMARY ({len(df_summary)} pairs)")
    logger.info("=" * 70)
    logger.info(f"  Prophet Daily WAPE              : {avg_daily_wape*100:.2f}%")
    logger.info(f"  Prophet Weekly WAPE (Primary)   : {avg_weekly_wape*100:.2f}%")
    logger.info(f"  Prophet Lead-Time Window WAPE   : {avg_lt_wape*100:.2f}%")
    logger.info(f"  Baseline Naive Weekly WAPE      : {avg_naive_weekly_wape*100:.2f}%")
    logger.info(f"  Baseline Seasonal Naive WAPE    : {avg_snaive_weekly_wape*100:.2f}%")
    logger.info(f"  Pairs flagged low_confidence    : {low_conf_count} / {len(df_summary)}")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
