"""Custom Recursive LightGBM Multi-Quantile Forecasting Engine.

Features:
- Global LightGBM forecasting across multi-series or single-series datasets.
- Three quantile models: Q10 (10th percentile), Q50 (median), Q90 (90th percentile).
- Recursive multi-step forecasting with quantile crossing correction and retail non-negativity.
- Asynchronous training job runner with progress tracking and persistent artifacts.
"""
from __future__ import annotations

import json
import pickle
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from .config import MODELS_DIR
from .db import get_db, init_db, now_iso
from .features import build_multi_series_dataset, build_series_features, get_default_feature_config


class LightGBMForecaster:
    """Multi-quantile recursive LightGBM forecaster."""

    def __init__(
        self,
        feature_config: dict[str, Any] | None = None,
        hyperparameters: dict[str, Any] | None = None,
        frequency: str = "D",
    ):
        self.frequency = frequency or "D"
        self.feature_config = feature_config or get_default_feature_config(self.frequency)
        self.hyperparameters = {
            "n_estimators": 100,
            "learning_rate": 0.05,
            "max_depth": 6,
            "num_leaves": 31,
            "min_child_samples": 20,
            "random_state": 42,
            "n_jobs": -1,
            "verbose": -1,
        }
        if hyperparameters:
            self.hyperparameters.update(hyperparameters)

        self.model_q10: lgb.LGBMRegressor | None = None
        self.model_q50: lgb.LGBMRegressor | None = None
        self.model_q90: lgb.LGBMRegressor | None = None
        self.feature_cols: list[str] = []
        self.series_encoder: dict[str, int] = {}
        self.metadata: dict[str, Any] = {}

    def fit(
        self,
        df: pd.DataFrame,
        val_fraction: float = 0.15,
    ) -> dict[str, Any]:
        """Train Q10, Q50, and Q90 models on long-format DataFrame [series_id, timestamp, target]."""
        start_time = time.time()
        long_df = df.sort_values(by=["series_id", "timestamp"]).copy()

        # Build feature dataset
        feat_df, raw_cols = build_multi_series_dataset(long_df, self.feature_config, drop_na=True)
        if feat_df.empty or len(feat_df) < 50:
            raise ValueError(f"Insufficient training observations after feature engineering: {len(feat_df)} rows.")

        # Series encoding
        unique_series = sorted(feat_df["series_id"].unique())
        self.series_encoder = {sid: idx for idx, sid in enumerate(unique_series)}
        feat_df["series_code"] = feat_df["series_id"].map(self.series_encoder).astype(int)

        self.feature_cols = ["series_code"] + raw_cols

        # Chronological train/validation split
        unique_timestamps = sorted(feat_df["timestamp"].unique())
        split_idx = max(1, int(len(unique_timestamps) * (1.0 - val_fraction)))
        cutoff_date = unique_timestamps[split_idx]

        train_mask = feat_df["timestamp"] < cutoff_date
        val_mask = feat_df["timestamp"] >= cutoff_date

        if val_mask.sum() == 0:
            train_mask = np.ones(len(feat_df), dtype=bool)
            val_mask = train_mask

        X_train = feat_df.loc[train_mask, self.feature_cols]
        y_train = feat_df.loc[train_mask, "target"].astype(float)
        X_val = feat_df.loc[val_mask, self.feature_cols]
        y_val = feat_df.loc[val_mask, "target"].astype(float)

        # Train 3 quantile models
        params_base = dict(self.hyperparameters)

        self.model_q10 = lgb.LGBMRegressor(**params_base, objective="quantile", alpha=0.10)
        self.model_q50 = lgb.LGBMRegressor(**params_base, objective="quantile", alpha=0.50)
        self.model_q90 = lgb.LGBMRegressor(**params_base, objective="quantile", alpha=0.90)

        self.model_q10.fit(X_train, y_train)
        self.model_q50.fit(X_train, y_train)
        self.model_q90.fit(X_train, y_train)

        # Validate on hold-out validation set
        val_preds_q10 = np.clip(self.model_q10.predict(X_val), 0, None)
        val_preds_q50 = np.clip(self.model_q50.predict(X_val), 0, None)
        val_preds_q90 = np.clip(self.model_q90.predict(X_val), 0, None)

        # Enforce quantile monotonicity
        val_preds_q10 = np.minimum(val_preds_q10, val_preds_q50)
        val_preds_q90 = np.maximum(val_preds_q90, val_preds_q50)

        mae = float(np.mean(np.abs(y_val - val_preds_q50)))
        rmse = float(np.sqrt(np.mean((y_val - val_preds_q50) ** 2)))
        sum_actual = float(np.sum(np.abs(y_val)))
        wape = float(np.sum(np.abs(y_val - val_preds_q50)) / sum_actual) if sum_actual > 0 else 0.0

        # Prediction interval coverage & width
        coverage = float(np.mean((y_val >= val_preds_q10) & (y_val <= val_preds_q90)))
        interval_width = float(np.mean(val_preds_q90 - val_preds_q10))

        # Pinball loss
        diff = y_val - val_preds_q50
        pinball_q50 = float(np.mean(np.maximum(0.5 * diff, (0.5 - 1.0) * diff)))

        duration = time.time() - start_time
        self.metadata = {
            "num_samples": len(feat_df),
            "num_series": len(unique_series),
            "num_features": len(self.feature_cols),
            "train_samples": int(train_mask.sum()),
            "val_samples": int(val_mask.sum()),
            "duration_sec": round(duration, 2),
            "cutoff_date": str(cutoff_date),
            "metrics": {
                "mae": round(mae, 4),
                "rmse": round(rmse, 4),
                "wape": round(wape, 4),
                "coverage_80": round(coverage, 4),
                "mean_interval_width": round(interval_width, 4),
                "pinball_loss_q50": round(pinball_q50, 4),
            },
        }
        return self.metadata

    def predict_recursive(
        self,
        history_df: pd.DataFrame,
        horizon: int,
        series_id: str = "default_series",
    ) -> pd.DataFrame:
        """Generate recursive multi-step forecasts for a single series.

        history_df must contain:
          - date / timestamp: datetime-like
          - sales / target: float
        """
        if self.model_q50 is None:
            raise RuntimeError("Model has not been trained yet.")
        if horizon < 1:
            raise ValueError("Forecast horizon must be at least 1.")

        df = history_df.copy()
        if "timestamp" not in df.columns:
            if "date" in df.columns:
                df["timestamp"] = pd.to_datetime(df["date"])
            else:
                raise ValueError("History DataFrame must contain 'date' or 'timestamp' column.")

        if "target" not in df.columns:
            if "sales" in df.columns:
                df["target"] = pd.to_numeric(df["sales"], errors="coerce")
            else:
                raise ValueError("History DataFrame must contain 'sales' or 'target' column.")

        df = df.dropna(subset=["timestamp", "target"]).sort_values("timestamp").reset_index(drop=True)
        if len(df) < 14:
            raise ValueError(f"Need at least 14 historical observations for recursive forecasting; got {len(df)}.")

        # Series code
        series_code = self.series_encoder.get(series_id, 0)

        # Working history buffer for recursive updates
        working_timestamps = list(pd.to_datetime(df["timestamp"]))
        working_targets = list(df["target"].astype(float))

        # Detect step delta
        if len(working_timestamps) >= 2:
            step_delta = working_timestamps[-1] - working_timestamps[-2]
            if step_delta <= pd.Timedelta(0):
                step_delta = pd.Timedelta(days=1)
        else:
            step_delta = pd.Timedelta(days=1)

        forecast_dates: list[pd.Timestamp] = []
        forecast_q10: list[float] = []
        forecast_q50: list[float] = []
        forecast_q90: list[float] = []

        for step in range(horizon):
            next_ts = working_timestamps[-1] + step_delta
            forecast_dates.append(next_ts)

            # Build temporary dataframe for feature calculation
            tmp_df = pd.DataFrame({"timestamp": working_timestamps, "target": working_targets})
            feat_df, _ = build_series_features(tmp_df, self.feature_config)

            # We need the feature vector representing the next timestamp
            # To compute features for next_ts without leaking next_ts target:
            # We append a row with next_ts and target=0, and compute lagged features!
            future_row = pd.DataFrame({"timestamp": [next_ts], "target": [0.0]})
            comb = pd.concat([tmp_df, future_row], ignore_index=True)
            comb_feat, _ = build_series_features(comb, self.feature_config)

            feat_row = comb_feat.iloc[[-1]].copy()
            feat_row["series_code"] = series_code

            # Ensure all required columns are present
            for c in self.feature_cols:
                if c not in feat_row.columns:
                    feat_row[c] = 0.0

            X_step = feat_row[self.feature_cols]

            # Predict
            pred_10 = float(self.model_q10.predict(X_step)[0])
            pred_50 = float(self.model_q50.predict(X_step)[0])
            pred_90 = float(self.model_q90.predict(X_step)[0])

            # Non-negativity constraint for retail sales
            pred_10 = max(0.0, pred_10)
            pred_50 = max(0.0, pred_50)
            pred_90 = max(0.0, pred_90)

            # Quantile crossing resolution
            pred_10 = min(pred_10, pred_50)
            pred_90 = max(pred_90, pred_50)

            forecast_q10.append(pred_10)
            forecast_q50.append(pred_50)
            forecast_q90.append(pred_90)

            # Recursive feedback: append point forecast Q50
            working_timestamps.append(next_ts)
            working_targets.append(pred_50)

        # Expected demand: approximated by 0.5 * Q50 + 0.25 * Q10 + 0.25 * Q90
        expected = [
            0.5 * m + 0.25 * low + 0.25 * high
            for m, low, high in zip(forecast_q50, forecast_q10, forecast_q90)
        ]

        return pd.DataFrame({
            "date": forecast_dates,
            "median": forecast_q50,
            "expected": expected,
            "q10": forecast_q10,
            "q50": forecast_q50,
            "q90": forecast_q90,
        })

    def save(self, filepath: Path) -> None:
        """Persist model bundle to disk."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        bundle = {
            "frequency": self.frequency,
            "feature_config": self.feature_config,
            "hyperparameters": self.hyperparameters,
            "feature_cols": self.feature_cols,
            "series_encoder": self.series_encoder,
            "metadata": self.metadata,
            "model_q10": self.model_q10,
            "model_q50": self.model_q50,
            "model_q90": self.model_q90,
        }
        with open(filepath, "wb") as f:
            pickle.dump(bundle, f)

    @classmethod
    def load(cls, filepath: Path) -> LightGBMForecaster:
        """Load model bundle from disk."""
        with open(filepath, "rb") as f:
            bundle = pickle.load(f)
        forecaster = cls(
            feature_config=bundle["feature_config"],
            hyperparameters=bundle["hyperparameters"],
            frequency=bundle.get("frequency", "D"),
        )
        forecaster.feature_cols = bundle["feature_cols"]
        forecaster.series_encoder = bundle["series_encoder"]
        forecaster.metadata = bundle.get("metadata", {})
        forecaster.model_q10 = bundle["model_q10"]
        forecaster.model_q50 = bundle["model_q50"]
        forecaster.model_q90 = bundle["model_q90"]
        return forecaster


# --- Background Training Job Manager ---

_TRAINING_JOBS: dict[str, dict[str, Any]] = {}


def start_training_job(
    dataset_id: str,
    model_name: str,
    hyperparameters: dict[str, Any] | None = None,
    feature_config: dict[str, Any] | None = None,
    val_fraction: float = 0.15,
) -> str:
    """Launch training in a background thread and return job ID."""
    from .dataset_manager import get_dataset_version, load_dataset_data

    init_db()
    v_info = get_dataset_version(dataset_id)
    if not v_info:
        raise ValueError(f"Dataset '{dataset_id}' not found.")

    model_id = f"lgbm-{uuid.uuid4().hex[:8]}"
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    clean_name = model_name.strip() or f"LightGBM-{dataset_id}"

    # Insert initial DB records
    with get_db() as conn:
        conn.execute(
            "INSERT INTO models (id, name, model_type, dataset_id, version_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (model_id, clean_name, "lightgbm", dataset_id, v_info["id"], now_iso()),
        )
        conn.execute(
            """
            INSERT INTO model_training_runs (
                id, model_id, dataset_id, version_id, status, hyperparameters_json,
                feature_config_json, train_start, train_end, val_start, val_end,
                duration_sec, num_samples, num_series, validation_metrics_json,
                artifact_path, error_message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                model_id,
                dataset_id,
                v_info["id"],
                "RUNNING",
                json.dumps(hyperparameters or {}),
                json.dumps(feature_config or {}),
                v_info["date_start"],
                v_info["date_end"],
                None,
                None,
                0.0,
                0,
                0,
                None,
                None,
                None,
                now_iso(),
            ),
        )

    _TRAINING_JOBS[run_id] = {
        "run_id": run_id,
        "model_id": model_id,
        "dataset_id": dataset_id,
        "status": "RUNNING",
        "progress": "Training LightGBM models...",
        "start_time": time.time(),
        "error": None,
    }

    def _worker():
        try:
            df = load_dataset_data(dataset_id)
            forecaster = LightGBMForecaster(
                feature_config=feature_config,
                hyperparameters=hyperparameters,
                frequency=v_info["frequency"],
            )
            meta = forecaster.fit(df, val_fraction=val_fraction)

            # Persist artifact
            art_dir = MODELS_DIR / model_id
            art_dir.mkdir(parents=True, exist_ok=True)
            art_path = art_dir / "model.pkl"
            forecaster.save(art_path)

            duration = time.time() - _TRAINING_JOBS[run_id]["start_time"]
            with get_db() as conn:
                conn.execute(
                    """
                    UPDATE model_training_runs
                    SET status = ?, duration_sec = ?, num_samples = ?, num_series = ?,
                        validation_metrics_json = ?, artifact_path = ?
                    WHERE id = ?
                    """,
                    (
                        "COMPLETED",
                        round(duration, 2),
                        meta["num_samples"],
                        meta["num_series"],
                        json.dumps(meta["metrics"]),
                        str(art_path),
                        run_id,
                    ),
                )
            _TRAINING_JOBS[run_id]["status"] = "COMPLETED"
            _TRAINING_JOBS[run_id]["metrics"] = meta["metrics"]
            _TRAINING_JOBS[run_id]["artifact_path"] = str(art_path)
        except Exception as e:
            with get_db() as conn:
                conn.execute(
                    "UPDATE model_training_runs SET status = ?, error_message = ? WHERE id = ?",
                    ("FAILED", str(e), run_id),
                )
            _TRAINING_JOBS[run_id]["status"] = "FAILED"
            _TRAINING_JOBS[run_id]["error"] = str(e)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return run_id


def get_training_job_status(run_id: str) -> dict[str, Any]:
    """Retrieve status of training run."""
    if run_id in _TRAINING_JOBS:
        return _TRAINING_JOBS[run_id]

    init_db()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM model_training_runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        raise KeyError(f"Training run '{run_id}' not found.")
    d = dict(row)
    if d.get("validation_metrics_json"):
        d["metrics"] = json.loads(d["validation_metrics_json"])
    return d


def list_trained_models(dataset_id: str | None = None) -> list[dict[str, Any]]:
    """List all trained LightGBM models with latest run metrics."""
    init_db()
    with get_db() as conn:
        query = """
            SELECT m.id as model_id, m.name, m.model_type, m.dataset_id, m.created_at,
                   mtr.id as run_id, mtr.status, mtr.duration_sec, mtr.validation_metrics_json,
                   mtr.artifact_path, mtr.num_samples, mtr.num_series
            FROM models m
            JOIN model_training_runs mtr ON m.id = mtr.model_id
            WHERE m.model_type = 'lightgbm' AND mtr.status = 'COMPLETED'
        """
        params: list[Any] = []
        if dataset_id:
            query += " AND m.dataset_id = ?"
            params.append(dataset_id)
        query += " ORDER BY m.created_at DESC"
        rows = conn.execute(query, params).fetchall()

    result = []
    for r in rows:
        item = dict(r)
        if item.get("validation_metrics_json"):
            try:
                item["metrics"] = json.loads(item["validation_metrics_json"])
            except Exception:
                item["metrics"] = None
        result.append(item)
    return result


def load_trained_forecaster(model_id: str) -> LightGBMForecaster:
    """Load trained LightGBMForecaster artifact by model_id."""
    art_path = MODELS_DIR / model_id / "model.pkl"
    if not art_path.exists():
        # Look in db for artifact path
        init_db()
        with get_db() as conn:
            row = conn.execute(
                "SELECT artifact_path FROM model_training_runs WHERE model_id = ? AND status = 'COMPLETED' ORDER BY created_at DESC LIMIT 1",
                (model_id,),
            ).fetchone()
        if row and row["artifact_path"] and Path(row["artifact_path"]).exists():
            art_path = Path(row["artifact_path"])
        else:
            raise FileNotFoundError(f"Model artifact not found for model_id '{model_id}' at {art_path}")

    return LightGBMForecaster.load(art_path)
