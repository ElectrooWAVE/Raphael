"""Verify the loader against the raw source CSV."""
import pandas as pd
import pytest

from rdf.config import DATA_DIR
from rdf.data_loader import get_series, list_series, load_sales, series_summary

RAW = DATA_DIR / "demand_history.csv"


@pytest.fixture(scope="module")
def sales():
    return load_sales(RAW)


def test_series_count(sales):
    assert len(list_series(sales)) == 75


@pytest.mark.parametrize("sid", ["FOODS_2_019 | Wisconsin - WI_1", "HOBBIES_1_048 | Texas - TX_1",
                                 "FOODS_3_080 | California - CA_1"])
def test_matches_source(sales, sid):
    raw = pd.read_csv(RAW, parse_dates=["date"])
    mat, area = sid.split(" | ")
    expect = raw[(raw.material == mat) & (raw.area == area)].sort_values("date")
    got = get_series(sales, sid)
    assert len(got) == len(expect)
    assert (got["date"].values == expect["date"].values).all()
    assert (got["sales"].values == expect["quantity"].values).all()


def test_zeros_kept_and_no_nans(sales):
    s = get_series(sales, "FOODS_2_019 | Wisconsin - WI_1")
    info = series_summary(s)
    assert info["zero_days"] == 1178 and info["missing_days"] == 0


def test_gap_becomes_nan_not_zero(sales):
    sid = "FOODS_3_080 | Texas - TX_1"
    holed = sales.drop(sales[(sales.series_id == sid)].index[100:103])
    s = get_series(holed, sid)
    assert len(s) == 1913 and s["sales"].isna().sum() == 3
