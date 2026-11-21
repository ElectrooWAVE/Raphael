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
        CREATE INDEX IF NOT EXISTS idx_fr_created_at ON forecast_runs(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_fv_run ON forecast_values(forecast_run_id);
        CREATE INDEX IF NOT EXISTS idx_er_run ON evaluation_results(evaluation_run_id);

        CREATE TABLE IF NOT EXISTS series_calibration (
            series_id TEXT NOT NULL,
            model_type TEXT NOT NULL,
            dataset_id TEXT NOT NULL DEFAULT 'retail-demand-m5',
            horizon INTEGER NOT NULL DEFAULT 28,
            scale_k REAL NOT NULL DEFAULT 1.0,
            raw_coverage_80 REAL,
            calibrated_coverage_80 REAL,
            sigma_d REAL,
            mae REAL,
            wape REAL,
            bias REAL,
            sample_points INTEGER,
            val_window_end TEXT,
            val_errors_json TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (series_id, model_type, dataset_id)
        );

        CREATE TABLE IF NOT EXISTS inventory_overrides (
            series_id TEXT NOT NULL,
            dataset_id TEXT NOT NULL DEFAULT 'retail-demand-m5',
            on_hand REAL,
            in_transit REAL NOT NULL DEFAULT 0.0,
            review_period REAL NOT NULL DEFAULT 7.0,
            pack_size INTEGER NOT NULL DEFAULT 1,
            moq INTEGER NOT NULL DEFAULT 0,
            service_level REAL NOT NULL DEFAULT 0.95,
            excess_days_threshold REAL NOT NULL DEFAULT 60.0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (series_id, dataset_id)
        );

        CREATE TABLE IF NOT EXISTS inventory_batch_jobs (
            id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL,
            model_type TEXT NOT NULL,
            model_id TEXT,
            horizon INTEGER NOT NULL DEFAULT 28,
            status TEXT NOT NULL,
            total_series INTEGER NOT NULL,
            completed_series INTEGER NOT NULL DEFAULT 0,
            current_series TEXT,
            duration_sec REAL,
            error_message TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS promotions (
            id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL DEFAULT 'retail-demand-m5',
            series_id TEXT,
            name TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            promo_type TEXT NOT NULL DEFAULT 'promotion',
            uplift_pct REAL NOT NULL DEFAULT 0.0,
            notes TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS automation_schedules (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            job_type TEXT NOT NULL,
            cron_expr TEXT NOT NULL,
            dataset_id TEXT NOT NULL DEFAULT 'retail-demand-m5',
            enabled INTEGER NOT NULL DEFAULT 1,
            last_run_at TEXT,
            last_status TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS automation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_id TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT,
            created_at TEXT NOT NULL
        );
        """)

        existing_cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(forecast_runs)").fetchall()
        }
        if "device" not in existing_cols:
            conn.execute("ALTER TABLE forecast_runs ADD COLUMN device TEXT")
        if "reproducibility_json" not in existing_cols:
            conn.execute("ALTER TABLE forecast_runs ADD COLUMN reproducibility_json TEXT")

        cal_cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(series_calibration)").fetchall()
        }
        if "val_errors_json" not in cal_cols:
            conn.execute("ALTER TABLE series_calibration ADD COLUMN val_errors_json TEXT")
