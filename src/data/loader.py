"""Data loading and schema enforcement for Raphael raw datasets.

Ensures strict validation of columns, dtypes, date formats, and outputs canonical
validated DataFrames and Parquet files.
"""
from pathlib import Path
from typing import Dict, Tuple
import pandas as pd


def load_raw_csvs(paths: Dict[str, str]) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load raw CSV files into pandas DataFrames.

    Args:
        paths: Dictionary of keys ('demand', 'lead_time', 'inventory', 'calendar_events')
               mapping to file paths.

    Returns:
        Tuple of (df_demand, df_lead_time, df_inventory, df_calendar).
    """
    for key, path_str in paths.items():
        p = Path(path_str)
        if not p.exists():
            raise FileNotFoundError(f"Required raw dataset '{key}' not found at: {p.resolve()}")

    df_demand = pd.read_csv(paths["demand"])
    df_lead_time = pd.read_csv(paths["lead_time"])
    df_inventory = pd.read_csv(paths["inventory"])
    df_calendar = pd.read_csv(paths["calendar_events"])

    return df_demand, df_lead_time, df_inventory, df_calendar


def parse_and_clean_data(
    df_demand: pd.DataFrame,
    df_lead_time: pd.DataFrame,
    df_inventory: pd.DataFrame,
    df_calendar: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Parse dates, strip whitespace, and normalize dtypes according to Raphael schema."""
    # 1. Demand
    df_demand = df_demand.copy()
    df_demand["date"] = pd.to_datetime(df_demand["date"], format="%Y-%m-%d")
    df_demand["material"] = df_demand["material"].astype(str).str.strip()
    df_demand["area"] = df_demand["area"].astype(str).str.strip()
    df_demand["quantity"] = pd.to_numeric(df_demand["quantity"], errors="raise").astype(float)
    df_demand["is_promotion"] = pd.to_numeric(df_demand["is_promotion"], errors="raise").astype(int)
    df_demand = df_demand.sort_values(["material", "area", "date"]).reset_index(drop=True)

    # 2. Lead Time
    df_lead_time = df_lead_time.copy()
    df_lead_time["material"] = df_lead_time["material"].astype(str).str.strip()
    df_lead_time["area"] = df_lead_time["area"].astype(str).str.strip()
    df_lead_time["order_date"] = pd.to_datetime(df_lead_time["order_date"], format="%Y-%m-%d")
    df_lead_time["order_quantity"] = pd.to_numeric(df_lead_time["order_quantity"], errors="raise").astype(float)
    df_lead_time["lead_time_days"] = pd.to_numeric(df_lead_time["lead_time_days"], errors="raise").astype(float)
    df_lead_time = df_lead_time.sort_values(["material", "area", "order_date"]).reset_index(drop=True)

    # 3. Inventory (Note: stock_status_simulated is preserved for reference only, never used in logic)
    df_inventory = df_inventory.copy()
    df_inventory["material"] = df_inventory["material"].astype(str).str.strip()
    df_inventory["area"] = df_inventory["area"].astype(str).str.strip()
    df_inventory["current_stock"] = pd.to_numeric(df_inventory["current_stock"], errors="raise").astype(float)
    df_inventory["last_updated"] = pd.to_datetime(df_inventory["last_updated"], format="%Y-%m-%d")
    df_inventory = df_inventory.sort_values(["material", "area"]).reset_index(drop=True)

    # 4. Calendar reference
    df_calendar = df_calendar.copy()
    df_calendar["date"] = pd.to_datetime(df_calendar["date"], format="%Y-%m-%d")
    df_calendar = df_calendar.sort_values("date").reset_index(drop=True)

    return df_demand, df_lead_time, df_inventory, df_calendar


def save_processed_parquets(
    df_demand: pd.DataFrame,
    df_lead_time: pd.DataFrame,
    df_inventory: pd.DataFrame,
    df_calendar: pd.DataFrame,
    output_dir: str = "data/processed",
) -> Dict[str, str]:
    """Save cleaned datasets to parquet format for efficient, vectorized downstream processing."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    paths = {
        "demand": str(out_path / "demand.parquet"),
        "lead_time": str(out_path / "lead_time.parquet"),
        "inventory": str(out_path / "inventory.parquet"),
        "calendar": str(out_path / "calendar.parquet"),
    }

    df_demand.to_parquet(paths["demand"], index=False, engine="pyarrow")
    df_lead_time.to_parquet(paths["lead_time"], index=False, engine="pyarrow")
    df_inventory.to_parquet(paths["inventory"], index=False, engine="pyarrow")
    df_calendar.to_parquet(paths["calendar"], index=False, engine="pyarrow")

    return paths
