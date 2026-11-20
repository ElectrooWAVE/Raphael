"""Universal Dataset Management System.

Handles multi-format file ingestion (CSV, XLSX, Parquet), column detection,
data quality validation, frequency alignment, and versioned parquet storage.
"""
from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from .config import DATA_DIR, PROCESSED_DIR, RAW_DIR
from .db import get_db, init_db, now_iso


@dataclass
class QualityReport:
    num_records: int
    num_series: int
    date_start: str
    date_end: str
    inferred_frequency: str
    zero_sales_count: int
    negative_sales_count: int
    missing_target_count: int
    duplicate_count: int
    gap_count: int
    quality_status: str  # "HEALTHY", "WARNING", "CRITICAL"
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_columns(df: pd.DataFrame) -> dict[str, Any]:
    """Heuristically detect time, target, and series columns."""
    cols = list(df.columns)
    detected_time = ""
    detected_target = ""
    detected_series: list[str] = []
    detected_covariates: list[str] = []

    time_patterns = [r".*date.*", r".*timestamp.*", r".*datetime.*", r".*time.*", r"^ds$", r"^day$"]
    target_patterns = [r".*sales.*", r".*demand.*", r".*quantity.*", r".*qty.*", r".*units.*", r".*revenue.*", r"^target$", r"^y$"]
    series_patterns = [r".*item.*", r".*product.*", r".*sku.*", r".*material.*", r".*store.*", r".*location.*", r".*area.*", r".*dept.*", r".*cat.*"]

    # Detect time column
    for col in cols:
        col_lower = str(col).strip().lower()
        if any(re.match(pat, col_lower) for pat in time_patterns):
            detected_time = str(col)
            break
    if not detected_time:
        for col in cols:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                detected_time = str(col)
                break

    # Detect target column
    for col in cols:
        if str(col) == detected_time:
            continue
        col_lower = str(col).strip().lower()
        if any(re.match(pat, col_lower) for pat in target_patterns):
            detected_target = str(col)
            break
    if not detected_target:
        for col in cols:
            if str(col) != detected_time and pd.api.types.is_numeric_dtype(df[col]):
                detected_target = str(col)
                break

    # Detect series columns
    for col in cols:
        if str(col) in (detected_time, detected_target):
            continue
        col_lower = str(col).strip().lower()
        if any(re.match(pat, col_lower) for pat in series_patterns):
            detected_series.append(str(col))
        else:
            detected_covariates.append(str(col))

    return {
        "columns": cols,
        "suggested_time_col": detected_time,
        "suggested_target_col": detected_target,
        "suggested_series_cols": detected_series,
        "suggested_covariates": detected_covariates,
        "sample_preview": df.head(5).to_dict(orient="records"),
    }


def read_raw_file(file_path: Path) -> pd.DataFrame:
    """Read CSV, XLSX, or Parquet into a DataFrame."""
    suffix = file_path.suffix.lower()
    if suffix in (".csv", ".txt"):
        return pd.read_csv(file_path)
    elif suffix in (".xlsx", ".xls"):
        return pd.read_excel(file_path)
    elif suffix in (".parquet", ".pq"):
        return pd.read_parquet(file_path)
    else:
        raise ValueError(f"Unsupported file format '{suffix}'. Supported: CSV, XLSX, Parquet.")


def inspect_file(file_path: Path) -> dict[str, Any]:
    """Inspect raw file and return detected metadata & column suggestions."""
    df = read_raw_file(file_path)
    meta = detect_columns(df)
    meta["file_name"] = file_path.name
    meta["file_size_bytes"] = file_path.stat().st_size
    meta["num_rows"] = len(df)
    meta["num_columns"] = len(df.columns)
    return meta


def validate_and_analyze(
    df: pd.DataFrame,
    time_col: str,
    target_col: str,
    series_cols: list[str] | None = None,
    frequency: str = "D",
) -> tuple[pd.DataFrame, QualityReport]:
    """Validate data quality, parse dates, resolve duplicates, and compute quality metrics."""
    if time_col not in df.columns:
        raise ValueError(f"Time column '{time_col}' not found in dataset columns: {list(df.columns)}")
    if target_col not in df.columns:
        raise ValueError(f"Target column '{target_col}' not found in dataset columns: {list(df.columns)}")

    df = df.copy()
    warnings: list[str] = []

    # Parse timestamps
    try:
        df["_parsed_time"] = pd.to_datetime(df[time_col], errors="coerce")
    except Exception as e:
        raise ValueError(f"Failed to parse time column '{time_col}': {e}") from e

    invalid_dates = df["_parsed_time"].isna().sum()
    if invalid_dates > 0:
        warnings.append(f"{invalid_dates} rows had invalid date values and were dropped.")
        df = df.dropna(subset=["_parsed_time"])

    # Build series identifier
    if series_cols and len(series_cols) > 0:
        for sc in series_cols:
            if sc not in df.columns:
                raise ValueError(f"Series column '{sc}' not found in dataset.")
        if len(series_cols) == 1:
            df["_series_id"] = df[series_cols[0]].astype(str)
        else:
            df["_series_id"] = df[series_cols[0]].astype(str)
            for sc in series_cols[1:]:
                df["_series_id"] = df["_series_id"] + " | " + df[sc].astype(str)
    else:
        df["_series_id"] = "default_series"

    # Numeric target check
    df["_target"] = pd.to_numeric(df[target_col], errors="coerce")
    missing_target = int(df["_target"].isna().sum())
    if missing_target > 0:
        warnings.append(f"{missing_target} rows had missing/non-numeric target values and were dropped.")
        df = df.dropna(subset=["_target"])

    negative_count = int((df["_target"] < 0).sum())
    if negative_count > 0:
        warnings.append(f"{negative_count} observations have negative values.")

    zero_count = int((df["_target"] == 0).sum())

    # Check for duplicates on (_series_id, _parsed_time)
    dup_mask = df.duplicated(subset=["_series_id", "_parsed_time"], keep=False)
    dup_count = int(dup_mask.sum())
    if dup_count > 0:
        warnings.append(f"{dup_count} duplicate timestamps found per series; aggregated by sum.")
        # Aggregate numeric by sum, keep first for categories
        agg_dict: dict[str, Any] = {"_target": "sum"}
        for c in df.columns:
            if c not in ("_series_id", "_parsed_time", "_target"):
                agg_dict[c] = "first"
        df = df.groupby(["_series_id", "_parsed_time"], as_index=False).agg(agg_dict)

    # Sort
    df = df.sort_values(by=["_series_id", "_parsed_time"]).reset_index(drop=True)

    # Frequency check and gaps per series
    gap_count = 0
    short_series_count = 0
    num_series = df["_series_id"].nunique()

    for _, group in df.groupby("_series_id"):
        if len(group) < 30:
            short_series_count += 1
        t_diffs = group["_parsed_time"].diff().dropna()
        if len(t_diffs) > 1:
            median_delta = t_diffs.median()
            # Flag gaps greater than 1.5x expected frequency
            if median_delta > pd.Timedelta(0):
                gaps = (t_diffs > 1.5 * median_delta).sum()
                gap_count += int(gaps)

    if short_series_count > 0:
        warnings.append(f"{short_series_count} series have fewer than 30 historical observations.")
    if gap_count > 0:
        warnings.append(f"{gap_count} potential date gaps detected across series timeline.")

    # Quality status
    status = "HEALTHY"
    if gap_count > 50 or negative_count > 100 or short_series_count == num_series:
        status = "WARNING"
    if len(df) == 0:
        status = "CRITICAL"

    min_date = df["_parsed_time"].min().strftime("%Y-%m-%d") if not df.empty else ""
    max_date = df["_parsed_time"].max().strftime("%Y-%m-%d") if not df.empty else ""

    report = QualityReport(
        num_records=len(df),
        num_series=num_series,
        date_start=min_date,
        date_end=max_date,
        inferred_frequency=frequency,
        zero_sales_count=zero_count,
        negative_sales_count=negative_count,
        missing_target_count=missing_target,
        duplicate_count=dup_count,
        gap_count=gap_count,
        quality_status=status,
        warnings=warnings,
    )
    return df, report


def import_dataset(
    file_path: Path,
    dataset_name: str,
    time_col: str,
    target_col: str,
    series_cols: list[str] | None = None,
    covariates: list[str] | None = None,
    frequency: str = "D",
    dataset_id: str | None = None,
    description: str = "",
) -> dict[str, Any]:
    """Import and standardize dataset, storing raw and versioned parquet files."""
    init_db()
    raw_df = read_raw_file(file_path)
    processed_df, quality_report = validate_and_analyze(
        raw_df,
        time_col=time_col,
        target_col=target_col,
        series_cols=series_cols,
        frequency=frequency,
    )

    clean_name = dataset_name.strip()
    if not clean_name:
        clean_name = file_path.stem.replace("_", " ").title()

    if not dataset_id:
        dataset_id = re.sub(r"[^a-zA-Z0-9_-]", "-", clean_name.lower())
        dataset_id = re.sub(r"-+", "-", dataset_id).strip("-")
        if not dataset_id:
            dataset_id = f"ds-{uuid.uuid4().hex[:8]}"

    # Determine version number
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
        if existing:
            v_row = conn.execute(
                "SELECT MAX(version_num) as max_v FROM dataset_versions WHERE dataset_id = ?",
                (dataset_id,),
            ).fetchone()
            version_num = (v_row["max_v"] or 0) + 1
        else:
            version_num = 1
            conn.execute(
                "INSERT INTO datasets (id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (dataset_id, clean_name, description, now_iso(), now_iso()),
            )

    version_id = f"{dataset_id}-v{version_num}"

    # Directory layout:
    # storage/raw/{dataset_id}/v{version_num}/
    # storage/processed/{dataset_id}/v{version_num}/data.parquet
    raw_dest_dir = RAW_DIR / dataset_id / f"v{version_num}"
    raw_dest_dir.mkdir(parents=True, exist_ok=True)
    stored_raw_path = raw_dest_dir / file_path.name
    if file_path.resolve() != stored_raw_path.resolve():
        shutil.copy2(file_path, stored_raw_path)

    proc_dest_dir = PROCESSED_DIR / dataset_id / f"v{version_num}"
    proc_dest_dir.mkdir(parents=True, exist_ok=True)
    stored_proc_path = proc_dest_dir / "data.parquet"

    # Assemble standardized columns: series_id, timestamp, target, + optional covariates
    export_df = pd.DataFrame({
        "series_id": processed_df["_series_id"],
        "timestamp": processed_df["_parsed_time"],
        "target": processed_df["_target"].astype(float),
    })

    if covariates:
        for cov in covariates:
            if cov in processed_df.columns:
                export_df[cov] = processed_df[cov]

    export_df.to_parquet(stored_proc_path, index=False)

    # Insert version metadata
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO dataset_versions (
                id, dataset_id, version_num, original_file_path, processed_file_path,
                file_format, num_records, num_series, date_start, date_end,
                frequency, target_col, time_col, series_cols_json, covariates_json,
                quality_report_json, import_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version_id,
                dataset_id,
                version_num,
                str(stored_raw_path),
                str(stored_proc_path),
                file_path.suffix.lstrip("."),
                quality_report.num_records,
                quality_report.num_series,
                quality_report.date_start,
                quality_report.date_end,
                frequency,
                target_col,
                time_col,
                json.dumps(series_cols or []),
                json.dumps(covariates or []),
                json.dumps(quality_report.to_dict()),
                "COMPLETED",
                now_iso(),
            ),
        )
        conn.execute("UPDATE datasets SET updated_at = ? WHERE id = ?", (now_iso(), dataset_id))

    return {
        "dataset_id": dataset_id,
        "dataset_name": clean_name,
        "version_id": version_id,
        "version_num": version_num,
        "quality_report": quality_report.to_dict(),
        "processed_file_path": str(stored_proc_path),
    }


def list_datasets() -> list[dict[str, Any]]:
    """Return all datasets with their latest version metadata."""
    init_db()
    with get_db() as conn:
        rows = conn.execute("""
            SELECT d.id, d.name, d.description, d.created_at, d.updated_at,
                   dv.id as latest_version_id, dv.version_num, dv.num_records,
                   dv.num_series, dv.date_start, dv.date_end, dv.frequency,
                   dv.target_col, dv.time_col, dv.quality_report_json
            FROM datasets d
            LEFT JOIN dataset_versions dv ON d.id = dv.dataset_id
            WHERE dv.version_num = (
                SELECT MAX(version_num) FROM dataset_versions WHERE dataset_id = d.id
            )
            ORDER BY d.updated_at DESC
        """).fetchall()

    result = []
    for r in rows:
        d = dict(r)
        if d.get("quality_report_json"):
            try:
                d["quality_report"] = json.loads(d["quality_report_json"])
            except Exception:
                d["quality_report"] = None
        else:
            d["quality_report"] = None
        result.append(d)
    return result


def get_dataset_version(dataset_id: str, version_num: int | None = None) -> dict[str, Any] | None:
    """Fetch specific or latest version metadata of a dataset."""
    init_db()
    with get_db() as conn:
        if version_num is not None:
            row = conn.execute(
                "SELECT * FROM dataset_versions WHERE dataset_id = ? AND version_num = ?",
                (dataset_id, version_num),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM dataset_versions WHERE dataset_id = ? ORDER BY version_num DESC LIMIT 1",
                (dataset_id,),
            ).fetchone()

    if not row:
        return None
    res = dict(row)
    for col in ("series_cols_json", "covariates_json", "quality_report_json"):
        if res.get(col):
            try:
                res[col[:-5]] = json.loads(res[col])
            except Exception:
                res[col[:-5]] = None
    return res


def load_dataset_data(dataset_id: str, version_num: int | None = None) -> pd.DataFrame:
    """Load standardized long-format data for a dataset version."""
    v_info = get_dataset_version(dataset_id, version_num)
    if not v_info:
        raise ValueError(f"Dataset '{dataset_id}' (version {version_num}) not found.")
    proc_path = Path(v_info["processed_file_path"])
    if not proc_path.exists():
        raise FileNotFoundError(f"Processed file not found at {proc_path}")
    return pd.read_parquet(proc_path)


def get_dataset_series_list(dataset_id: str, version_num: int | None = None) -> list[str]:
    """Return distinct series IDs in dataset."""
    df = load_dataset_data(dataset_id, version_num)
    return sorted(df["series_id"].unique().tolist())


def get_series_history(
    dataset_id: str,
    series_id: str,
    version_num: int | None = None,
) -> pd.DataFrame:
    """Return daily/periodic history for a single series: columns [date, sales]."""
    df = load_dataset_data(dataset_id, version_num)
    sub = df[df["series_id"] == series_id].copy()
    if sub.empty:
        raise KeyError(f"Series '{series_id}' not found in dataset '{dataset_id}'.")
    sub = sub.sort_values(by="timestamp").reset_index(drop=True)
    return pd.DataFrame({
        "date": pd.to_datetime(sub["timestamp"]),
        "sales": sub["target"].astype(float),
    })


def ensure_default_dataset() -> str:
    """Seed the default retail demand M5 dataset if no datasets exist."""
    init_db()
    datasets = list_datasets()
    if datasets:
        return datasets[0]["id"]

    csv_path = DATA_DIR / "demand_history.csv"
    if not csv_path.exists():
        return ""

    peek = pd.read_csv(csv_path, nrows=2)
    cols = list(peek.columns)

    if {"date", "material", "area", "quantity"} <= set(cols):
        time_col = "date"
        target_col = "quantity"
        series_cols = ["material", "area"]
        covs = [c for c in ["is_promotion"] if c in cols]
    elif {"date", "sales"} <= set(cols):
        time_col = "date"
        target_col = "sales"
        series_cols = [c for c in ["item_id", "store_id"] if c in cols]
        covs = []
    else:
        meta = detect_columns(peek)
        time_col = meta["suggested_time_col"] or cols[0]
        target_col = meta["suggested_target_col"] or cols[-1]
        series_cols = meta["suggested_series_cols"]
        covs = []

    res = import_dataset(
        file_path=csv_path,
        dataset_name="Retail Demand (M5 Sample)",
        time_col=time_col,
        target_col=target_col,
        series_cols=series_cols,
        covariates=covs,
        frequency="D",
        dataset_id="retail-demand-m5",
        description="Standardized multi-store retail demand dataset.",
    )
    return res["dataset_id"]
