"""Unit tests for Universal Dataset Management System."""
import tempfile
import uuid
from pathlib import Path
import pandas as pd
import pytest

from rdf.dataset_manager import (
    detect_columns,
    get_dataset_series_list,
    get_series_history,
    import_dataset,
    list_datasets,
    load_dataset_data,
    validate_and_analyze,
)


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    csv_file = tmp_path / "custom_retail.csv"
    dates = pd.date_range("2024-01-01", periods=60, freq="D")
    df = pd.DataFrame({
        "order_date": list(dates) + list(dates),
        "product_sku": ["SKU_A"] * 60 + ["SKU_B"] * 60,
        "store_code": ["STORE_01"] * 60 + ["STORE_02"] * 60,
        "units_sold": [10.0 + (i % 5) for i in range(120)],
        "on_sale": [1 if i % 7 == 0 else 0 for i in range(120)],
    })
    df.to_csv(csv_file, index=False)
    return csv_file


@pytest.fixture
def single_series_csv(tmp_path: Path) -> Path:
    csv_file = tmp_path / "single_series.csv"
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    df = pd.DataFrame({
        "timestamp": dates,
        "revenue": [100.0 + (i * 2) for i in range(50)],
    })
    df.to_csv(csv_file, index=False)
    return csv_file


def test_detect_columns(sample_csv: Path):
    df = pd.read_csv(sample_csv)
    meta = detect_columns(df)
    assert meta["suggested_time_col"] == "order_date"
    assert meta["suggested_target_col"] == "units_sold"
    assert "product_sku" in meta["suggested_series_cols"]
    assert "store_code" in meta["suggested_series_cols"]


def test_validation_quality_analysis():
    df = pd.DataFrame({
        "date": ["2024-01-01", "2024-01-02", "2024-01-02", "2024-01-03", "2024-01-05", "invalid"],
        "sales": [10.0, 0.0, 5.0, -2.0, 8.0, 15.0],
    })
    clean_df, report = validate_and_analyze(df, time_col="date", target_col="sales")
    assert report.zero_sales_count == 1
    assert report.negative_sales_count == 1
    assert report.duplicate_count == 2
    # Invalid date dropped and duplicate aggregated
    assert len(clean_df) == 4


def test_import_and_versioning(sample_csv: Path):
    ds_id = f"test-store-{uuid.uuid4().hex[:6]}"
    res1 = import_dataset(
        file_path=sample_csv,
        dataset_name="Test Store Dataset",
        time_col="order_date",
        target_col="units_sold",
        series_cols=["product_sku", "store_code"],
        covariates=["on_sale"],
        dataset_id=ds_id,
    )
    assert res1["version_num"] == 1
    assert res1["quality_report"]["num_series"] == 2

    # Import new version under same id
    res2 = import_dataset(
        file_path=sample_csv,
        dataset_name="Test Store Dataset",
        time_col="order_date",
        target_col="units_sold",
        series_cols=["product_sku", "store_code"],
        dataset_id=ds_id,
    )
    assert res2["version_num"] == 2

    series = get_dataset_series_list(ds_id)
    assert "SKU_A | STORE_01" in series
    assert "SKU_B | STORE_02" in series

    hist = get_series_history(ds_id, "SKU_A | STORE_01")
    assert len(hist) == 60
    assert hist["sales"].iloc[0] == 10.0


def test_single_series_import(single_series_csv: Path):
    ds_id = f"single-series-{uuid.uuid4().hex[:6]}"
    res = import_dataset(
        file_path=single_series_csv,
        dataset_name="Single Series Shop",
        time_col="timestamp",
        target_col="revenue",
        series_cols=None,
        dataset_id=ds_id,
    )
    assert res["version_num"] == 1
    assert res["quality_report"]["num_series"] == 1

    series = get_dataset_series_list(ds_id)
    assert series == ["default_series"]
    hist = get_series_history(ds_id, "default_series")
    assert len(hist) == 50
