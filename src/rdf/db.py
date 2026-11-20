"""Relational metadata storage using SQLite.

Manages datasets, versions, models, training runs, forecast runs, and evaluations.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from .config import DB_PATH


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_db(db_path: Path = DB_PATH) -> Generator[sqlite3.Connection, None, None]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path = DB_PATH) -> None:
    """Initialize schema tables and indexes."""
    with get_db(db_path) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS datasets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS dataset_versions (
            id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
            version_num INTEGER NOT NULL,
            original_file_path TEXT,
            processed_file_path TEXT NOT NULL,
            file_format TEXT NOT NULL,
            num_records INTEGER NOT NULL,
            num_series INTEGER NOT NULL,
            date_start TEXT,
            date_end TEXT,
            frequency TEXT NOT NULL,
            target_col TEXT NOT NULL,
            time_col TEXT NOT NULL,
            series_cols_json TEXT,
            covariates_json TEXT,
            quality_report_json TEXT,
            import_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(dataset_id, version_num)
        );

        CREATE TABLE IF NOT EXISTS models (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            model_type TEXT NOT NULL,
            dataset_id TEXT,
            version_id TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS model_training_runs (
            id TEXT PRIMARY KEY,
            model_id TEXT NOT NULL REFERENCES models(id) ON DELETE CASCADE,
            dataset_id TEXT NOT NULL,
            version_id TEXT NOT NULL,
            status TEXT NOT NULL,
            hyperparameters_json TEXT,
            feature_config_json TEXT,
            train_start TEXT,
            train_end TEXT,
            val_start TEXT,
            val_end TEXT,
            duration_sec REAL,
            num_samples INTEGER,
            num_series INTEGER,
            validation_metrics_json TEXT,
            artifact_path TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS forecast_runs (
            id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL,
            version_id TEXT NOT NULL,
            series_id TEXT NOT NULL,
            model_type TEXT NOT NULL,
            model_id TEXT,
            horizon INTEGER NOT NULL,
            context_end TEXT,
            forecast_start TEXT,
            execution_time_sec REAL,
            metrics_json TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS forecast_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            forecast_run_id TEXT NOT NULL REFERENCES forecast_runs(id) ON DELETE CASCADE,
            timestamp TEXT NOT NULL,
            predicted_median REAL,
            lower_bound REAL,
            upper_bound REAL,
            expected REAL,
            actual REAL
        );

        CREATE TABLE IF NOT EXISTS evaluation_runs (
            id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL,
            version_id TEXT NOT NULL,
            series_id TEXT NOT NULL,
            horizon INTEGER NOT NULL,
            models_evaluated_json TEXT NOT NULL,
            summary_metrics_json TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS evaluation_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_run_id TEXT NOT NULL REFERENCES evaluation_runs(id) ON DELETE CASCADE,
            model_type TEXT NOT NULL,
            cutoff_date TEXT NOT NULL,
            horizon INTEGER NOT NULL,
            mae REAL,
            rmse REAL,
            wape REAL,
            mase REAL,
            bias REAL,
            pinball_loss REAL,
            coverage REAL,
            interval_width REAL
        );

        CREATE INDEX IF NOT EXISTS idx_dv_dataset ON dataset_versions(dataset_id);
        CREATE INDEX IF NOT EXISTS idx_mtr_model ON model_training_runs(model_id);
        CREATE INDEX IF NOT EXISTS idx_fr_dataset_series ON forecast_runs(dataset_id, series_id);
        CREATE INDEX IF NOT EXISTS idx_fv_run ON forecast_values(forecast_run_id);
        CREATE INDEX IF NOT EXISTS idx_er_run ON evaluation_results(evaluation_run_id);
        """)
