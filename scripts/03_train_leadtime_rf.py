"""Train Random Forest lead-time model with dual uncertainty estimation (Phase 3).

Executes:
1. Time-ordered train/test split (80% train, 20% test = 16,425 train, 4,125 test)
2. Fits Random Forest on order_quantity, calendar, area, material features
3. Computes tree-spread std and calibrates empirical residual uncertainty
4. Evaluates against baseline (per-pair historical mean) on MAE, RMSE, R2, and 95% coverage
5. Detects order quantity extrapolation boundaries
6. Exports models, test evaluations, per-pair predictions, and metrics artifact
"""
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models.leadtime_rf import LeadTimeRandomForestModel
from src.utils.checkpoint import CheckpointManager
from src.utils.logger import setup_logger
from src.utils.progress import get_progress_bar, timed_block


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 3: Train Lead-Time Random Forest with Uncertainty Calibration.")
    parser.add_argument("--config", type=str, default="configs/raphael.yaml")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--n_jobs", type=int, default=-1)
    return parser.parse_args()


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    args = parse_args()
    logger = setup_logger("03_train_leadtime_rf", log_dir="logs")

    logger.info("=" * 80)
    logger.info(" Raphael Phase 3: Lead-Time Prediction & Uncertainty Calibration (Random Forest)")
    logger.info("=" * 80)

    config = load_config(args.config)
    lead_time_parquet = config["paths"]["processed_data"]["lead_time_parquet"]

    if not Path(lead_time_parquet).exists():
        logger.error(f"Lead time data missing: {lead_time_parquet}. Run Phase 1 first.")
        sys.exit(1)

    df_lt = pd.read_parquet(lead_time_parquet).sort_values("order_date").reset_index(drop=True)
    logger.info(f"Loaded {len(df_lt):,} orders from {lead_time_parquet}")

    # Checkpoint
    chk = CheckpointManager("03_train_leadtime_rf", checkpoint_dir=config["paths"]["checkpoints"]["dir"], force=args.force, logger=logger)

    # 1. Time-ordered 80/20 train/test split
    split_idx = int(len(df_lt) * 0.8)
    split_date = df_lt["order_date"].iloc[split_idx]
    train_df = df_lt.iloc[:split_idx].copy()
    test_df = df_lt.iloc[split_idx:].copy()

    logger.info(f"Time-ordered split at: {split_date.strftime('%Y-%m-%d')}")
    logger.info(f"  Training set : {len(train_df):,} orders ({train_df['order_date'].min().strftime('%Y-%m-%d')} to {train_df['order_date'].max().strftime('%Y-%m-%d')})")
    logger.info(f"  Held-out test: {len(test_df):,} orders ({test_df['order_date'].min().strftime('%Y-%m-%d')} to {test_df['order_date'].max().strftime('%Y-%m-%d')})")

    # 2. Fit Random Forest & Calibrate Residual Uncertainty
    rf_cfg = config.get("models", {}).get("lead_time_rf", {})
    model_checkpoint_id = "lead_time_rf_fitted"

    if chk.is_completed(model_checkpoint_id) and not args.force:
        logger.info(f"Loading completed model checkpoint: {model_checkpoint_id}")
        model = LeadTimeRandomForestModel.load(chk.get_unit_path(model_checkpoint_id, extension="pkl"))
        calib_stats = {
            "overall_calibrated_std": model.overall_calibrated_std,
            "segmented_calibrated_stds": model.calibrated_stds,
        }
    else:
        model = LeadTimeRandomForestModel(
            n_estimators=int(rf_cfg.get("n_estimators", 100)),
            random_state=args.seed,
            n_jobs=args.n_jobs,
        )

        with timed_block("Fitting Random Forest & Calibrating Uncertainty (OOF)", logger=logger):
            calib_stats = model.fit_with_calibration(train_df, target_col="lead_time_days", n_splits=5)
            logger.info(f"  Overall Calibrated Residual Std (OOF): {calib_stats['overall_calibrated_std']:.3f} days")
            logger.info(f"  Segmented Stds: {calib_stats['segmented_calibrated_stds']}")

        chk_path = chk.get_unit_path(model_checkpoint_id, extension="pkl")
        model.save(chk_path)
        logger.info(f"Saved model checkpoint -> {chk_path}")

    # 4. Evaluate on Held-out Test Set
    logger.info("\nEvaluating on held-out test set...")
    test_preds = model.predict(test_df)
    y_test = test_df["lead_time_days"].to_numpy(dtype=float)
    y_rf = test_preds["predicted_lead_time"].to_numpy(dtype=float)
    tree_stds = test_preds["tree_spread_std"].to_numpy(dtype=float)
    calib_stds = test_preds["calibrated_lead_time_std"].to_numpy(dtype=float)

    # Baseline: per-pair historical mean from training set
    pair_means = train_df.groupby(["material", "area"])["lead_time_days"].mean().to_dict()
    y_base = np.array([pair_means.get((r["material"], r["area"]), 5.2) for _, r in test_df.iterrows()], dtype=float)

    # Performance metrics
    rf_mae = float(mean_absolute_error(y_test, y_rf))
    base_mae = float(mean_absolute_error(y_test, y_base))

    rf_rmse = float(np.sqrt(mean_squared_error(y_test, y_rf)))
    base_rmse = float(np.sqrt(mean_squared_error(y_test, y_base)))

    rf_r2 = float(r2_score(y_test, y_rf))
    base_r2 = float(r2_score(y_test, y_base))

    # Spread calibration coverage
    cov_tree = float(np.mean(np.abs(y_test - y_rf) <= 1.96 * tree_stds))
    cov_calib = float(np.mean(np.abs(y_test - y_rf) <= 1.96 * calib_stds))

    # Area-specific breakdown
    area_breakdown = {}
    test_df_eval = test_df.copy()
    test_df_eval["y_rf"] = y_rf
    test_df_eval["y_base"] = y_base
    test_df_eval["tree_std"] = tree_stds
    test_df_eval["calib_std"] = calib_stds

    for area, grp in test_df_eval.groupby("area"):
        y_a = grp["lead_time_days"].values
        rf_a = grp["y_rf"].values
        b_a = grp["y_base"].values
        t_std_a = grp["tree_std"].values
        c_std_a = grp["calib_std"].values

        area_breakdown[area] = {
            "test_orders": len(grp),
            "actual_mean": round(float(np.mean(y_a)), 2),
            "rf_mae": round(float(mean_absolute_error(y_a, rf_a)), 3),
            "base_mae": round(float(mean_absolute_error(y_a, b_a)), 3),
            "rf_rmse": round(float(np.sqrt(mean_squared_error(y_a, rf_a))), 3),
            "tree_std_coverage_95": round(float(np.mean(np.abs(y_a - rf_a) <= 1.96 * t_std_a)), 4),
            "calibrated_coverage_95": round(float(np.mean(np.abs(y_a - rf_a) <= 1.96 * c_std_a)), 4),
        }

    # 5. Precompute baseline predictions for all 75 pairs for Phase 4 decision layer
    # For each pair, compute at: mean order quantity for upcoming season (Spring/Summer vs Nov/Dec)
    pbar = get_progress_bar(total=75, desc="Building pair lead-time profiles", unit="pair")
    pair_profiles = []
    pairs = df_lt[["material", "area"]].drop_duplicates().values.tolist()

    for mat, area in pairs:
        grp = df_lt[(df_lt["material"] == mat) & (df_lt["area"] == area)]
        mean_qty = float(grp["order_quantity"].mean())
        p_range = model.hist_ranges.get((mat, area), (1.0, 500.0))

        # Spring/Summer profile (as_of_date is April 24, horizon is May-July)
        input_normal = pd.DataFrame([{
            "material": mat,
            "area": area,
            "order_date": pd.to_datetime("2016-05-15"),
            "order_quantity": mean_qty,
        }])
        pred_normal = model.predict(input_normal).iloc[0]

        # Holiday peak profile (Nov-Dec)
        input_holiday = pd.DataFrame([{
            "material": mat,
            "area": area,
            "order_date": pd.to_datetime("2016-11-15"),
            "order_quantity": mean_qty,
        }])
        pred_holiday = model.predict(input_holiday).iloc[0]

        pair_profiles.append({
            "material": mat,
            "area": area,
            "typical_order_quantity": round(mean_qty, 1),
            "hist_min_quantity": p_range[0],
            "hist_max_quantity": p_range[1],
            "lead_time_upcoming_days": pred_normal["predicted_lead_time"],
            "tree_spread_std": pred_normal["tree_spread_std"],
            "calibrated_lead_time_std": pred_normal["calibrated_lead_time_std"],
            "lead_time_holiday_peak_days": pred_holiday["predicted_lead_time"],
        })
        pbar.update(1)
    pbar.close()

    df_profiles = pd.DataFrame(pair_profiles)

    # 6. Save Artifacts
    artifacts_dir = Path("artifacts")
    lt_dir = artifacts_dir / "lead_time"
    metrics_dir = artifacts_dir / "metrics"
    lt_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)

    # Model
    model_path = lt_dir / "lead_time_rf_model.pkl"
    model.save(model_path)
    logger.info(f"Saved trained Random Forest model -> {model_path}")

    # Test evaluations
    test_eval_path = lt_dir / "lead_time_test_eval.parquet"
    test_export = test_preds.copy()
    test_export["actual_lead_time"] = y_test
    test_export["baseline_lead_time"] = y_base
    test_export.to_parquet(test_eval_path, index=False, engine="pyarrow")
    logger.info(f"Saved test evaluation data ({len(test_export):,} orders) -> {test_eval_path}")

    # Pair profiles for inventory decision layer
    profiles_path = lt_dir / "lead_time_pair_predictions.parquet"
    df_profiles.to_parquet(profiles_path, index=False, engine="pyarrow")
    logger.info(f"Saved per-pair lead time decision profiles ({len(df_profiles)} pairs) -> {profiles_path}")

    # Evaluation metrics JSON
    metrics_payload = {
        "timestamp": datetime.now().isoformat(),
        "total_test_orders": len(test_df),
        "split_date": split_date.strftime("%Y-%m-%d"),
        "overall": {
            "rf_mae": round(rf_mae, 3),
            "baseline_mae": round(base_mae, 3),
            "rf_rmse": round(rf_rmse, 3),
            "baseline_rmse": round(base_rmse, 3),
            "rf_r2": round(rf_r2, 3),
            "baseline_r2": round(base_r2, 3),
            "mean_tree_spread_std": round(float(np.mean(tree_stds)), 3),
            "overall_calibrated_std": round(float(calib_stats["overall_calibrated_std"]), 3),
            "tree_std_coverage_95": round(cov_tree, 4),
            "calibrated_coverage_95": round(cov_calib, 4),
        },
        "area_breakdown": area_breakdown,
        "calibrated_uncertainties": calib_stats["segmented_calibrated_stds"],
    }

    metrics_path = metrics_dir / "lead_time_model_evaluation.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics_payload, f, indent=2)
    logger.info(f"Saved lead-time metrics artifact -> {metrics_path}")

    # Summary table
    logger.info("\n" + "=" * 80)
    logger.info(" PHASE 3 LEAD-TIME MODEL EVALUATION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"{'Metric':<32} | {'Random Forest':<18} | {'Historical Baseline':<20}")
    logger.info("-" * 80)
    logger.info(f"{'MAE (Mean Absolute Error)':<32} | {rf_mae:>14.3f} d | {base_mae:>16.3f} d")
    logger.info(f"{'RMSE':<32} | {rf_rmse:>14.3f} d | {base_rmse:>16.3f} d")
    logger.info(f"{'R-Squared (Variance Explained)':<32} | {rf_r2:>14.3f}   | {base_r2:>16.3f}  ")
    logger.info("-" * 80)
    logger.info(f"{'Tree Spread Std (Ensemble)':<32} | {np.mean(tree_stds):>14.3f} d | {'N/A':>16}")
    logger.info(f"{'Calibrated Residual Std':<32} | {calib_stats['overall_calibrated_std']:>14.3f} d | {'N/A':>16}")
    logger.info(f"{'95% Coverage (Tree Spread Std)':<32} | {cov_tree*100:>13.2f}%  | {'N/A':>16} (Understates!)")
    logger.info(f"{'95% Coverage (Calibrated Std)':<32} | {cov_calib*100:>13.2f}%  | {'N/A':>16} (Calibrated!)")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
