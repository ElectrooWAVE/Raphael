"""Unified Forecasting and Comparison Service.

Coordinates Chronos-2, Custom Recursive LightGBM, and Seasonal-Naive models.
Guarantees consistent output schemas and persists all forecasting experiments to SQLite.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

import numpy as np
import pandas as pd

from .baseline import forecast_seasonal_naive
from .config import MODEL_ID
from .db import get_db, init_db, now_iso
from .evaluation import compute_metrics
from .forecaster import ForecastError, forecast as forecast_chronos, load_pipeline
from .lgbm_forecaster import LightGBMForecaster, list_trained_models, load_trained_forecaster


def generate_single_forecast(
    history_df: pd.DataFrame,
    horizon: int,
    model_type: str = "chronos",
    model_id: str | None = None,
    series_id: str = "item",
    chronos_pipeline_tuple: tuple[Any, str] | None = None,
    dataset_id: str = "default",
    version_id: str = "v1",
) -> dict[str, Any]:
    """Execute forecast using selected model engine and persist execution run."""
    init_db()
    start_time = time.time()
    run_id = f"fc-{uuid.uuid4().hex[:10]}"

    model_type_clean = model_type.lower().strip()
    is_custom_alias = model_type_clean in ("custom", "custom_model", "custom model")
    if is_custom_alias:
        model_type_clean = "lightgbm"

    device = "cpu"
    used_model_id = model_id or ("Custom Model" if is_custom_alias else model_type_clean)

    if model_type_clean == "chronos":
        if chronos_pipeline_tuple is None:
            pipeline, device = load_pipeline()
        else:
            pipeline, device = chronos_pipeline_tuple
        res_df = forecast_chronos(pipeline, history_df, horizon, series_id)
        used_model_id = MODEL_ID

    elif model_type_clean == "lightgbm":
        device = "cpu"
        if not model_id:
            models = list_trained_models(dataset_id)
            if not models:
                models = list_trained_models()
            if not models:
                # Auto-fit a default custom model so custom forecasting works immediately
                from .dataset_manager import load_dataset_data
                from .lgbm_forecaster import MODELS_DIR
                ds_data = load_dataset_data(dataset_id)
                auto_model = LightGBMForecaster(hyperparameters={"n_estimators": 50, "learning_rate": 0.08, "verbose": -1})
                auto_meta = auto_model.fit(ds_data, val_fraction=0.15)
                auto_id = f"custom-default-{dataset_id}"
                art_path = MODELS_DIR / auto_id / "model.pkl"
                auto_model.save(art_path)
                with get_db() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO models (id, name, model_type, dataset_id, version_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (auto_id, "Custom Model", "lightgbm", dataset_id, "v1", now_iso()),
                    )
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO model_training_runs (
                            id, model_id, dataset_id, version_id, status, duration_sec, num_samples, num_series,
                            validation_metrics_json, artifact_path, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            f"run-{auto_id}", auto_id, dataset_id, "v1", "COMPLETED",
                            auto_meta["duration_sec"], auto_meta["num_samples"], auto_meta["num_series"],
                            json.dumps(auto_meta["metrics"]), str(art_path), now_iso()
                        )
                    )
                model_id = auto_id
            else:
                model_id = models[0]["model_id"]
        used_model_id = "Custom Model" if is_custom_alias else model_id
        forecaster = load_trained_forecaster(model_id)
        res_df = forecaster.predict_recursive(history_df, horizon, series_id)

    elif model_type_clean == "baseline":
        device = "cpu"
        used_model_id = "seasonal-naive"
        res_df = forecast_seasonal_naive(history_df, horizon, frequency="D")

    else:
        raise ValueError(f"Unknown model_type '{model_type}'. Choose: chronos, lightgbm, baseline.")

    exec_duration = time.time() - start_time

    # Standardize result vectors
    dates = [pd.Timestamp(d).strftime("%Y-%m-%d") for d in res_df["date"]]
    median_vals = [float(v) for v in res_df["median"]]
    expected_vals = [float(v) for v in res_df.get("expected", res_df["median"])]
    q10_vals = [float(v) for v in res_df["q10"]]
    q50_vals = [float(v) for v in res_df["q50"]]
    q90_vals = [float(v) for v in res_df["q90"]]

    total_pred = float(np.sum(expected_vals))
    daily_avg = float(np.mean(expected_vals))

    # Persist into database
    hist_end = str(history_df["date"].max()) if "date" in history_df else ""
    fc_start = dates[0] if dates else ""

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO forecast_runs (
                id, dataset_id, version_id, series_id, model_type, model_id,
                horizon, context_end, forecast_start, execution_time_sec,
                metrics_json, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                dataset_id,
                version_id,
                series_id,
                model_type_clean,
                used_model_id,
                horizon,
                hist_end,
                fc_start,
                round(exec_duration, 3),
                None,
                "COMPLETED",
                now_iso(),
            ),
        )

        for d, m, exp, low, high in zip(dates, median_vals, expected_vals, q10_vals, q90_vals):
            conn.execute(
                """
                INSERT INTO forecast_values (
                    forecast_run_id, timestamp, predicted_median, lower_bound, upper_bound, expected
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, d, m, low, high, exp),
            )

    return {
        "run_id": run_id,
        "dates": dates,
        "median": median_vals,
        "expected": expected_vals,
        "q10": q10_vals,
        "q50": q50_vals,
        "q90": q90_vals,
        "total": total_pred,
        "daily_average": daily_avg,
        "device": device,
        "model": used_model_id,
        "model_type": "custom" if is_custom_alias else model_type_clean,
        "execution_time_sec": round(exec_duration, 3),
    }


def compare_models(
    history_df: pd.DataFrame,
    horizon: int,
    series_id: str,
    dataset_id: str = "default",
    version_id: str = "v1",
    cutoff_index: int | None = None,
    chronos_pipeline_tuple: tuple[Any, str] | None = None,
) -> dict[str, Any]:
    """Execute side-by-side comparison between Chronos-2, LightGBM, and Baseline."""
    df = history_df.sort_values(by="date").reset_index(drop=True)
    n = len(df)

    has_ground_truth = False
    test_actuals: list[float] = []

    if cutoff_index is not None and cutoff_index < n:
        context_df = df.iloc[:cutoff_index].copy()
        test_df = df.iloc[cutoff_index : min(n, cutoff_index + horizon)].copy()
        test_actuals = [float(v) for v in test_df["sales"]]
        has_ground_truth = len(test_actuals) == horizon
    else:
        context_df = df.copy()

    models_to_run = ["baseline", "chronos", "custom"]
    results: dict[str, Any] = {}
    metrics_by_model: dict[str, Any] = {}

    for mtype in models_to_run:
        try:
            fc = generate_single_forecast(
                history_df=context_df,
                horizon=horizon,
                model_type=mtype,
                series_id=series_id,
                dataset_id=dataset_id,
                version_id=version_id,
                chronos_pipeline_tuple=chronos_pipeline_tuple,
            )
            key_name = "custom" if mtype in ("custom", "lightgbm") else mtype
            results[key_name] = fc

            if has_ground_truth:
                m = compute_metrics(
                    actual=test_actuals,
                    predicted_median=fc["median"],
                    q10=fc["q10"],
                    q90=fc["q90"],
                    in_sample_actual=list(context_df["sales"]),
                )
                m["execution_time_sec"] = fc["execution_time_sec"]
                metrics_by_model[key_name] = m
            else:
                metrics_by_model[key_name] = {
                    "total_predicted": fc["total"],
                    "daily_average": fc["daily_average"],
                    "execution_time_sec": fc["execution_time_sec"],
                }
        except Exception as e:
            key_name = "custom" if mtype in ("custom", "lightgbm") else mtype
            results[key_name] = {"error": str(e)}

    # Determine best model per metric if ground truth exists
    best_models: dict[str, str] = {}
    if has_ground_truth and metrics_by_model:
        for metric in ["mae", "rmse", "wape", "mase", "pinball_loss"]:
            valid = {m: metrics_by_model[m][metric] for m in metrics_by_model if metric in metrics_by_model[m]}
            if valid:
                best_models[metric] = min(valid, key=valid.get)  # type: ignore

        if any("coverage_80" in metrics_by_model[m] for m in metrics_by_model):
            # Best coverage is closest to 0.80
            cov_diffs = {
                m: abs(metrics_by_model[m]["coverage_80"] - 0.80)
                for m in metrics_by_model
                if "coverage_80" in metrics_by_model[m]
            }
            if cov_diffs:
                best_models["coverage_80"] = min(cov_diffs, key=cov_diffs.get)  # type: ignore

    return {
        "series_id": series_id,
        "horizon": horizon,
        "has_ground_truth": has_ground_truth,
        "actual_test_dates": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in test_df["date"]] if has_ground_truth else [],
        "actual_test_values": test_actuals,
        "forecasts": results,
        "metrics": metrics_by_model,
        "best_models": best_models,
    }


def list_forecast_runs(
    dataset_id: str | None = None,
    series_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Query recent forecasting runs from database."""
    init_db()
    with get_db() as conn:
        query = """
            SELECT fr.*,
                   COUNT(fv.id) as point_count
            FROM forecast_runs fr
            LEFT JOIN forecast_values fv ON fr.id = fv.forecast_run_id
            WHERE 1=1
        """
        params: list[Any] = []
        if dataset_id:
            query += " AND fr.dataset_id = ?"
            params.append(dataset_id)
        if series_id:
            query += " AND fr.series_id = ?"
            params.append(series_id)

        query += " GROUP BY fr.id ORDER BY fr.created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()

    return [dict(r) for r in rows]


def get_forecast_run_details(run_id: str) -> dict[str, Any] | None:
    """Fetch complete details and curves of a specific forecast run."""
    init_db()
    with get_db() as conn:
        run = conn.execute("SELECT * FROM forecast_runs WHERE id = ?", (run_id,)).fetchone()
        if not run:
            return None
        res = dict(run)
        values = conn.execute(
            "SELECT * FROM forecast_values WHERE forecast_run_id = ? ORDER BY timestamp ASC",
            (run_id,),
        ).fetchall()
        res["values"] = [dict(v) for v in values]
    return res
