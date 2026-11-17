"""Load sales data and turn one product into a clean, chronological daily series.

Two input formats are supported:
  1. demand_history.csv  -> long format: date, material, area, quantity
  2. sales_train_validation.csv (official M5) -> wide format: id, item_id,
     dept_id, cat_id, store_id, state_id, d_1 ... d_1913

Both are converted to ONE long format: series_id, date, sales.
Genuine zero-sales days are real observations and are never removed.
A day that is truly missing (no row / blank cell) becomes NaN, not 0.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import DATA_DIR, M5_START_DATE


def detect_format(path: Path) -> str:
    cols = pd.read_csv(path, nrows=0).columns
    if {"date", "material", "area", "quantity"} <= set(cols):
        return "demand_history"
    if "item_id" in cols and "store_id" in cols and "d_1" in cols:
        return "m5_wide"
    raise ValueError(f"{path.name}: unrecognised columns {list(cols)[:8]}...")


def load_sales(path: str | Path | None = None) -> pd.DataFrame:
    """Return long DataFrame [series_id, date, sales]. Uses official M5 file if present."""
    if path is None:
        m5 = DATA_DIR / "sales_train_validation.csv"
        path = m5 if m5.exists() else DATA_DIR / "demand_history.csv"
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Sales file not found: {path}")

    fmt = detect_format(path)
    if fmt == "demand_history":
        df = pd.read_csv(
            path,
            usecols=["date", "material", "area", "quantity"],
            dtype={"material": "category", "area": "category", "quantity": "float64"},
            parse_dates=["date"],
        )
        df["series_id"] = df["material"].astype(str) + " | " + df["area"].astype(str)
        df = df.rename(columns={"quantity": "sales"})[["series_id", "date", "sales"]]
    else:
        df = _load_m5_wide(path)
    return df.sort_values(["series_id", "date"], kind="stable").reset_index(drop=True)


def _load_m5_wide(path: Path) -> pd.DataFrame:
    wide = pd.read_csv(path)
    day_cols = [c for c in wide.columns if c.startswith("d_")]
    dates = pd.date_range(M5_START_DATE, periods=len(day_cols), freq="D")
    wide["series_id"] = wide["item_id"] + " | " + wide["store_id"]
    long = wide.melt(id_vars="series_id", value_vars=day_cols, var_name="d", value_name="sales")
    long["date"] = long["d"].map(dict(zip(day_cols, dates)))
    long["sales"] = long["sales"].astype("float64")
    return long[["series_id", "date", "sales"]]


def list_series(df: pd.DataFrame) -> list[str]:
    return sorted(df["series_id"].unique().tolist())


def get_series(df: pd.DataFrame, series_id: str) -> pd.DataFrame:
    """One product -> continuous daily series [date, sales].

    Missing calendar days are inserted as NaN (unknown), zeros are kept as zeros.
    """
    s = df.loc[df["series_id"] == series_id, ["date", "sales"]]
    if s.empty:
        raise KeyError(f"Unknown series: {series_id}")
    s = s.drop_duplicates("date", keep="last").set_index("date").sort_index()
    full = pd.date_range(s.index.min(), s.index.max(), freq="D")
    s = s.reindex(full)
    s.index.name = "date"
    return s.reset_index()


def series_summary(s: pd.DataFrame) -> dict:
    v = s["sales"]
    return {
        "days": int(len(s)),
        "start": s["date"].min().date(),
        "end": s["date"].max().date(),
        "zero_days": int((v == 0).sum()),
        "missing_days": int(v.isna().sum()),
        "total_units": float(np.nansum(v)),
    }
