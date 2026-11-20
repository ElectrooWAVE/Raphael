"""Universal Dataset Management System.

Handles multi-format file ingestion (CSV, XLSX, Parquet), column detection,
data quality validation, frequency alignment, and versioned parquet storage.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import uuid
from dataclasses import asdict, dataclass
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


def _sanitize_json_value(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, (pd.Timestamp,)):
        if pd.isna(val):
            return None
        return val.strftime("%Y-%m-%d")
    if isinstance(val, float):
        return val if math.isfinite(val) else None
    if isinstance(val, (np.floating,)):
        f = float(val)
        return f if math.isfinite(f) else None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.bool_,)):
        return bool(val)
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


def sanitize_filename(filename: str) -> str:
    """Return a safe basename without directory traversal characters."""
    raw = (filename or "").strip()
    if not raw or ".." in raw or "/" in raw or "\\" in raw:
        raise ValueError("Invalid filename.")
    name = Path(raw).name
    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    if not cleaned or cleaned.startswith("."):
        raise ValueError("Invalid filename.")
    return cleaned


def _infer_frequency(df: pd.DataFrame, time_col: str, series_cols: list[str]) -> str:
    if not time_col or time_col not in df.columns or df.empty:
        return "D"
    try:
        sample = df.head(5000).copy()
        if series_cols and series_cols[0] in sample.columns:
            first_val = sample[series_cols[0]].iloc[0]
            sample = sample[sample[series_cols[0]] == first_val]
        ts = pd.to_datetime(sample[time_col], errors="coerce").dropna().sort_values()
        diffs = ts.diff().dropna()
        diffs = diffs[diffs > pd.Timedelta(0)]
        if diffs.empty:
            return "D"
        med_hours = diffs.median().total_seconds() / 3600.0
        if med_hours < 12:
            return "H"
        if med_hours <= 36:
            return "D"
        if med_hours <= 24 * 10:
            return "W"
        return "M"
    except Exception:
        return "D"


def _normalize_covariates(covariates: Sequence[str | dict[str, str]] | None) -> list[dict[str, str]]:
    if not covariates:
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in covariates:
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            role = str(item.get("role", "past-only")).strip().lower()
            if role not in ("past-only", "known-future"):
                role = "past-only"
        else:
            name = str(item).strip()
            role = "past-only"
        if name and name not in seen:
            seen.add(name)
            out.append({"name": name, "role": role})
    return out


def detect_columns(df: pd.DataFrame) -> dict[str, Any]:
    """Heuristically detect time, target, series columns, frequency, and covariate roles."""
    cols = [str(c) for c in df.columns]
    detected_time = ""
    detected_target = ""
    detected_series: list[str] = []
    detected_covariates: list[str] = []

    time_patterns = [r".*date.*", r".*timestamp.*", r".*datetime.*", r".*time.*", r"^ds$", r"^day$"]
    target_patterns = [r".*sales.*", r".*demand.*", r".*quantity.*", r".*qty.*", r".*units.*", r".*revenue.*", r"^target$", r"^y$"]
    series_patterns = [r".*item.*", r".*product.*", r".*sku.*", r".*material.*", r".*store.*", r".*location.*", r".*area.*", r".*dept.*", r".*cat.*"]
    future_cov_patterns = [r".*event.*", r".*holiday.*", r".*calendar.*", r".*weekday.*", r".*weekend.*", r".*month.*", r".*quarter.*", r".*year.*"]

    # Detect time column
    for col in cols:
        if any(re.match(pat, col.strip().lower()) for pat in time_patterns):
            detected_time = col
            break
    if not detected_time:
        for col in cols:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                detected_time = col
                break
    if not detected_time and not df.empty:
        for col in cols:
            if pd.api.types.is_object_dtype(df[col]) or isinstance(df[col].dtype, pd.StringDtype):
                parsed = pd.to_datetime(df[col].head(200), errors="coerce")
                if parsed.notna().mean() >= 0.8:
                    detected_time = col
                    break

    # Detect numeric target column
    for col in cols:
        if col == detected_time:
            continue
        if pd.api.types.is_numeric_dtype(df[col]) and any(re.match(pat, col.strip().lower()) for pat in target_patterns):
            detected_target = col
            break
    if not detected_target:
        for col in cols:
            if col != detected_time and any(re.match(pat, col.strip().lower()) for pat in target_patterns):
                detected_target = col
                break
    if not detected_target:
        for col in cols:
            if col != detected_time and pd.api.types.is_numeric_dtype(df[col]):
                detected_target = col
                break

    # Detect series columns (pattern match or low-cardinality text)
    n_rows = max(len(df), 1)
    max_card = min(500, max(50, int(n_rows * 0.25)))
    for col in cols:
        if col in (detected_time, detected_target):
            continue
        col_lower = col.strip().lower()
        is_text = pd.api.types.is_object_dtype(df[col]) or isinstance(df[col].dtype, (pd.CategoricalDtype, pd.StringDtype))
        n_uniq = int(df[col].nunique(dropna=True))
        if any(re.match(pat, col_lower) for pat in series_patterns):
            detected_series.append(col)
        elif is_text and 1 < n_uniq <= max_card:
            detected_series.append(col)
        else:
            detected_covariates.append(col)

    column_types: dict[str, str] = {}
    for col in cols:
        if col == detected_time or pd.api.types.is_datetime64_any_dtype(df[col]):
            column_types[col] = "datetime"
        elif pd.api.types.is_numeric_dtype(df[col]):
            column_types[col] = "numeric"
        else:
            column_types[col] = "text"

    covariate_roles: dict[str, str] = {}
    for col in cols:
        if col in (detected_time, detected_target) or col in detected_series:
            continue
        col_lower = col.strip().lower()
        covariate_roles[col] = "known-future" if any(re.match(p, col_lower) for p in future_cov_patterns) else "past-only"

    preview_rows: list[dict[str, Any]] = []
    for rec in df.head(10).to_dict(orient="records"):
        preview_rows.append({str(k): _sanitize_json_value(v) for k, v in rec.items()})

    return {
        "columns": cols,
        "column_types": column_types,
        "suggested_time_col": detected_time,
        "suggested_target_col": detected_target,
        "suggested_series_cols": detected_series,
        "suggested_covariates": detected_covariates,
        "suggested_covariate_roles": covariate_roles,
        "suggested_frequency": _infer_frequency(df, detected_time, detected_series),
        "sample_preview": preview_rows,
    }


def read_raw_file(file_path: Path) -> pd.DataFrame:
    """Read CSV, XLSX, or Parquet into a DataFrame."""
    suffix = file_path.suffix.lower()
    if suffix in (".csv", ".txt"):
        return pd.read_csv(file_path)
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(file_path)
    if suffix in (".parquet", ".pq"):
        return pd.read_parquet(file_path)
    raise ValueError(f"Unsupported file format '{suffix}'. Supported: CSV, XLSX, Parquet.")


def inspect_file(file_path: Path, display_name: str | None = None) -> dict[str, Any]:
    """Inspect raw file and return detected metadata & column suggestions."""
    df = read_raw_file(file_path)
    meta = detect_columns(df)
    meta["file_name"] = display_name or file_path.name
    meta["file_size_bytes"] = file_path.stat().st_size
    meta["num_rows"] = int(len(df))
    meta["num_columns"] = int(len(df.columns))
    return meta


def validate_dataset_frame(
    df: pd.DataFrame,
    time_col: str,
    target_col: str,
    series_cols: list[str] | None = None,
    covariates: Sequence[str | dict[str, str]] | None = None,
    frequency: str = "D",
) -> dict[str, Any]:
    """Validate dataset thoroughly before import. Returns blocking errors and non-blocking warnings."""
    errors: list[str] = []
    warnings: list[str] = []

    if df.empty:
        errors.append("Dataset contains zero rows.")
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "quality_status": "ERROR",
            "num_records": 0,
            "num_series": 0,
            "date_start": "",
            "date_end": "",
            "inferred_frequency": frequency,
            "duplicate_count": 0,
            "missing_days_total": 0,
            "missing_days_per_series": {},
            "missing_target_count": 0,
            "negative_sales_count": 0,
            "zero_sales_count": 0,
            "zero_sales_share": 0.0,
            "covariate_nan_counts": {},
        }

    if not time_col or time_col not in df.columns:
        errors.append(f"Date column '{time_col}' was not found in dataset columns.")
    if not target_col or target_col not in df.columns:
        errors.append(f"Target column '{target_col}' was not found in dataset columns.")

    sc_clean = [c.strip() for c in (series_cols or []) if c and c.strip()]
    for sc in sc_clean:
        if sc not in df.columns:
            errors.append(f"Series identifier column '{sc}' was not found in dataset columns.")

    cov_norm = _normalize_covariates(covariates)
    for cov in cov_norm:
        if cov["name"] not in df.columns:
            errors.append(f"Covariate column '{cov['name']}' was not found in dataset columns.")

    if errors:
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "quality_status": "ERROR",
            "num_records": int(len(df)),
            "num_series": 0,
            "date_start": "",
            "date_end": "",
            "inferred_frequency": frequency,
            "duplicate_count": 0,
            "missing_days_total": 0,
            "missing_days_per_series": {},
            "missing_target_count": 0,
            "negative_sales_count": 0,
            "zero_sales_count": 0,
            "zero_sales_share": 0.0,
            "covariate_nan_counts": {},
        }

    work = df.copy()
    work["_parsed_time"] = pd.to_datetime(work[time_col], errors="coerce")
    invalid_dates = int(work["_parsed_time"].isna().sum())
    if invalid_dates == len(work):
        errors.append(f"Date column '{time_col}' contains no valid parseable dates.")
    elif invalid_dates > 0:
        errors.append(f"{invalid_dates} row(s) in '{time_col}' have unparseable dates.")

    work["_target"] = pd.to_numeric(work[target_col], errors="coerce")
    missing_target = int(work["_target"].isna().sum())
    if missing_target == len(work):
        errors.append(f"Target column '{target_col}' contains no numeric values.")
    elif missing_target > 0:
        warnings.append(f"{missing_target} target value(s) are NaN/non-numeric and will remain NaN (never 0).")

    if sc_clean:
        work["_series_id"] = work[sc_clean[0]].astype(str)
        for sc in sc_clean[1:]:
            work["_series_id"] = work["_series_id"] + " | " + work[sc].astype(str)
    else:
        work["_series_id"] = "default_series"

    valid_dates_df = work.dropna(subset=["_parsed_time"])
    dup_mask = valid_dates_df.duplicated(subset=["_series_id", "_parsed_time"], keep=False)
    duplicate_count = int(dup_mask.sum())
    if duplicate_count > 0:
        errors.append(
            f"Found {duplicate_count} duplicate (series, date) rows. Remove or aggregate duplicates before importing."
        )

    negative_count = int((work["_target"] < 0).sum())
    if negative_count > 0:
        warnings.append(f"{negative_count} observation(s) have negative target values.")

    non_na_count = int(work["_target"].notna().sum())
    zero_count = int((work["_target"] == 0).sum())
    zero_share = float(zero_count / non_na_count) if non_na_count > 0 else 0.0
    if zero_count > 0:
        warnings.append(
            f"{zero_count:,} zero-sales row(s) ({zero_share:.1%}) detected and will be kept untouched."
        )

    cov_nans: dict[str, int] = {}
    for cov in cov_norm:
        cname = cov["name"]
        n_na = int(work[cname].isna().sum())
        cov_nans[cname] = n_na
        if n_na > 0:
            warnings.append(f"Covariate '{cname}' ({cov['role']}) has {n_na} NaN value(s).")

    num_series = int(work["_series_id"].nunique())
    missing_days_per_series: dict[str, int] = {}
    missing_days_total = 0
    short_series_count = 0

    if not valid_dates_df.empty:
        for sid, grp in valid_dates_df.groupby("_series_id"):
            if len(grp) < 30:
                short_series_count += 1
            if frequency == "D":
                norm_dates = grp["_parsed_time"].dt.normalize()
                span_days = int((norm_dates.max() - norm_dates.min()).days) + 1
                obs_days = int(norm_dates.nunique())
                miss = max(0, span_days - obs_days)
                if miss > 0:
                    missing_days_total += miss
                    missing_days_per_series[str(sid)] = miss

    if short_series_count > 0:
        warnings.append(f"{short_series_count} series have fewer than 30 rows.")
    if missing_days_total > 0:
        warnings.append(
            f"{missing_days_total} missing calendar day(s) across {len(missing_days_per_series)} series (kept as NaN, never 0)."
        )

    top_missing = dict(sorted(missing_days_per_series.items(), key=lambda x: x[1], reverse=True)[:10])
    min_date = valid_dates_df["_parsed_time"].min().strftime("%Y-%m-%d") if not valid_dates_df.empty else ""
    max_date = valid_dates_df["_parsed_time"].max().strftime("%Y-%m-%d") if not valid_dates_df.empty else ""

    status = "ERROR" if errors else ("WARNING" if warnings else "HEALTHY")
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "quality_status": status,
        "num_records": int(len(work)),
        "num_series": num_series,
        "date_start": min_date,
        "date_end": max_date,
        "inferred_frequency": frequency,
        "duplicate_count": duplicate_count,
        "missing_days_total": int(missing_days_total),
        "missing_days_per_series": top_missing,
        "missing_target_count": missing_target,
        "negative_sales_count": negative_count,
        "zero_sales_count": zero_count,
        "zero_sales_share": round(zero_share, 4),
        "covariate_nan_counts": cov_nans,
    }


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

    try:
        df["_parsed_time"] = pd.to_datetime(df[time_col], errors="coerce")
    except Exception as e:
        raise ValueError(f"Failed to parse time column '{time_col}': {e}") from e

    invalid_dates = int(df["_parsed_time"].isna().sum())
    if invalid_dates > 0:
        warnings.append(f"{invalid_dates} rows had invalid date values and were dropped.")
        df = df.dropna(subset=["_parsed_time"])

    if series_cols and len(series_cols) > 0:
        for sc in series_cols:
            if sc not in df.columns:
                raise ValueError(f"Series column '{sc}' not found in dataset.")
        df["_series_id"] = df[series_cols[0]].astype(str)
        for sc in series_cols[1:]:
            df["_series_id"] = df["_series_id"] + " | " + df[sc].astype(str)
    else:
        df["_series_id"] = "default_series"

    df["_target"] = pd.to_numeric(df[target_col], errors="coerce")
    missing_target = int(df["_target"].isna().sum())
    if missing_target > 0:
        warnings.append(f"{missing_target} rows had missing/non-numeric target values (kept as NaN).")

    negative_count = int((df["_target"] < 0).sum())
    if negative_count > 0:
        warnings.append(f"{negative_count} observations have negative values.")

    zero_count = int((df["_target"] == 0).sum())

    dup_mask = df.duplicated(subset=["_series_id", "_parsed_time"], keep=False)
    dup_count = int(dup_mask.sum())
    if dup_count > 0:
        warnings.append(f"{dup_count} duplicate timestamps found per series; aggregated by sum.")
        agg_dict: dict[str, Any] = {"_target": "sum"}
        for c in df.columns:
            if c not in ("_series_id", "_parsed_time", "_target"):
                agg_dict[c] = "first"
        df = df.groupby(["_series_id", "_parsed_time"], as_index=False).agg(agg_dict)

    df = df.sort_values(by=["_series_id", "_parsed_time"]).reset_index(drop=True)

    gap_count = 0
    short_series_count = 0
    num_series = int(df["_series_id"].nunique())

    for _, group in df.groupby("_series_id"):
        if len(group) < 30:
            short_series_count += 1
        t_diffs = group["_parsed_time"].diff().dropna()
        if len(t_diffs) > 1:
            median_delta = t_diffs.median()
            if median_delta > pd.Timedelta(0):
                gaps = (t_diffs > 1.5 * median_delta).sum()
                gap_count += int(gaps)

    if short_series_count > 0:
        warnings.append(f"{short_series_count} series have fewer than 30 historical observations.")
    if gap_count > 0:
        warnings.append(f"{gap_count} potential date gaps detected across series timeline.")

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
    covariates: Sequence[str | dict[str, str]] | None = None,
    frequency: str = "D",
    dataset_id: str | None = None,
    description: str = "",
    strict: bool = False,
    original_filename: str | None = None,
) -> dict[str, Any]:
    """Import and standardize dataset, storing raw and versioned parquet files."""
    init_db()
    raw_df = read_raw_file(file_path)
    cov_norm = _normalize_covariates(covariates)
    cov_names = [c["name"] for c in cov_norm]

    if strict:
        v_report = validate_dataset_frame(
            raw_df,
            time_col=time_col,
            target_col=target_col,
            series_cols=series_cols,
            covariates=cov_norm,
            frequency=frequency,
        )
        if not v_report["valid"]:
            raise ValueError("; ".join(v_report["errors"]))

    processed_df, quality_report = validate_and_analyze(
        raw_df,
        time_col=time_col,
        target_col=target_col,
        series_cols=series_cols,
        frequency=frequency,
    )

    clean_name = dataset_name.strip()
    if not clean_name:
        clean_name = Path(original_filename or file_path.name).stem.replace("_", " ").title()

    if not dataset_id:
        dataset_id = re.sub(r"[^a-zA-Z0-9_-]", "-", clean_name.lower())
        dataset_id = re.sub(r"-+", "-", dataset_id).strip("-")
        if not dataset_id:
            dataset_id = f"ds-{uuid.uuid4().hex[:8]}"
    else:
        dataset_id = re.sub(r"[^a-zA-Z0-9_-]", "-", dataset_id).strip("-")
        if not dataset_id:
            raise ValueError("Invalid dataset_id.")

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
    safe_raw_name = sanitize_filename(original_filename or file_path.name)

    raw_dest_dir = (RAW_DIR / dataset_id / f"v{version_num}").resolve()
    proc_dest_dir = (PROCESSED_DIR / dataset_id / f"v{version_num}").resolve()
    if not raw_dest_dir.is_relative_to(RAW_DIR.resolve()) or not proc_dest_dir.is_relative_to(PROCESSED_DIR.resolve()):
        raise ValueError("Resolved storage path escapes storage root.")

    raw_dest_dir.mkdir(parents=True, exist_ok=True)
    stored_raw_path = (raw_dest_dir / safe_raw_name).resolve()
    if not stored_raw_path.is_relative_to(raw_dest_dir):
        raise ValueError("Invalid stored filename.")
    if file_path.resolve() != stored_raw_path:
        shutil.copy2(file_path, stored_raw_path)

    proc_dest_dir.mkdir(parents=True, exist_ok=True)
    stored_proc_path = proc_dest_dir / "data.parquet"

    export_df = pd.DataFrame({
        "series_id": processed_df["_series_id"],
        "timestamp": processed_df["_parsed_time"],
        "target": processed_df["_target"].astype(float),
    })

    for cov in cov_names:
        if cov in processed_df.columns:
            export_df[cov] = processed_df[cov]

    export_df.to_parquet(stored_proc_path, index=False)

    q_dict = quality_report.to_dict()
    if strict:
        q_dict["zero_sales_share"] = v_report["zero_sales_share"]
        q_dict["missing_days_total"] = v_report["missing_days_total"]
        q_dict["missing_days_per_series"] = v_report["missing_days_per_series"]
        q_dict["covariate_nan_counts"] = v_report["covariate_nan_counts"]

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
                Path(safe_raw_name).suffix.lstrip("."),
                quality_report.num_records,
                quality_report.num_series,
                quality_report.date_start,
                quality_report.date_end,
                frequency,
                target_col,
                time_col,
                json.dumps(series_cols or []),
                json.dumps(cov_norm),
                json.dumps(q_dict),
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
        "quality_report": q_dict,
        "covariates": cov_norm,
        "processed_file_path": str(stored_proc_path),
    }


def list_datasets() -> list[dict[str, Any]]:
    """Return all datasets with their latest version metadata and usage counts."""
    init_db()
    with get_db() as conn:
        rows = conn.execute("""
            SELECT d.id, d.name, d.description, d.created_at, d.updated_at,
                   dv.id as latest_version_id, dv.version_num, dv.num_records,
                   dv.num_series, dv.date_start, dv.date_end, dv.frequency,
                   dv.target_col, dv.time_col, dv.covariates_json, dv.quality_report_json,
                   (SELECT COUNT(*) FROM dataset_versions dv2 WHERE dv2.dataset_id = d.id) as version_count,
                   (SELECT COUNT(*) FROM models m WHERE m.dataset_id = d.id) as model_count,
                   (SELECT COUNT(*) FROM forecast_runs fr WHERE fr.dataset_id = d.id) as run_count
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
        for col, out_key in (("quality_report_json", "quality_report"), ("covariates_json", "covariates")):
            if d.get(col):
                try:
                    d[out_key] = json.loads(d[col])
                except Exception:
                    d[out_key] = None
            else:
                d[out_key] = None
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
    """Return daily/periodic history for a single series: columns [date, sales].

    Missing calendar days for daily datasets stay NaN (never 0); genuine zero-sales rows are kept.
    """
    v_info = get_dataset_version(dataset_id, version_num)
    if not v_info:
        raise ValueError(f"Dataset '{dataset_id}' (version {version_num}) not found.")
    df = pd.read_parquet(v_info["processed_file_path"])
    sub = df[df["series_id"] == series_id].copy()
    if sub.empty:
        raise KeyError(f"Series '{series_id}' not found in dataset '{dataset_id}'.")
    sub["date"] = pd.to_datetime(sub["timestamp"])
    sub["sales"] = sub["target"].astype(float)
    sub = sub[["date", "sales"]].sort_values("date").reset_index(drop=True)

    if v_info.get("frequency") == "D" and len(sub) > 1:
        sub_idx = sub.drop_duplicates("date", keep="last").set_index("date")
        full_idx = pd.date_range(sub_idx.index.min(), sub_idx.index.max(), freq="D")
        if len(full_idx) != len(sub_idx):
            sub_idx = sub_idx.reindex(full_idx)
            sub_idx.index.name = "date"
            return sub_idx.reset_index()
    return sub


def delete_dataset(dataset_id: str) -> dict[str, Any] | None:
    """Delete dataset, its versions metadata, and stored files inside RAW_DIR/PROCESSED_DIR."""
    init_db()
    with get_db() as conn:
        row = conn.execute("SELECT id FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
        if not row:
            return None
        model_count = int(conn.execute("SELECT COUNT(*) FROM models WHERE dataset_id = ?", (dataset_id,)).fetchone()[0])
        run_count = int(conn.execute("SELECT COUNT(*) FROM forecast_runs WHERE dataset_id = ?", (dataset_id,)).fetchone()[0])
        conn.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))

    for root_dir in (RAW_DIR, PROCESSED_DIR):
        target = (root_dir / dataset_id).resolve()
        if target.exists() and target.is_relative_to(root_dir.resolve()) and target != root_dir.resolve():
            shutil.rmtree(target, ignore_errors=True)

    return {
        "deleted": True,
        "dataset_id": dataset_id,
        "used_by_models": model_count,
        "used_by_runs": run_count,
    }


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
