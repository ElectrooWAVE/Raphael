"""Unit tests for Evaluation Metrics and Seasonal-Naive Baseline."""
import numpy as np
import pandas as pd
import pytest

from rdf.baseline import forecast_seasonal_naive
from rdf.evaluation import compute_metrics, generate_backtest_cutoffs


def test_compute_metrics():
    actual = [10.0, 20.0, 30.0, 40.0]
    predicted = [12.0, 18.0, 33.0, 38.0]
    # abs err: 2, 2, 3, 2 -> mean = 2.25
    # sq err: 4, 4, 9, 4 -> mean = 5.25 -> sqrt = 2.2913
    # sum actual = 100 -> sum abs err = 9 -> wape = 0.09
    # bias: (101 - 100) / 100 = +0.01

    m = compute_metrics(
        actual=actual,
        predicted_median=predicted,
        q10=[8.0, 15.0, 25.0, 35.0],
        q90=[15.0, 25.0, 35.0, 45.0],
        in_sample_actual=[5.0, 10.0, 15.0, 20.0],
    )
    assert np.isclose(m["mae"], 2.25)
    assert np.isclose(m["wape"], 0.09)
    assert np.isclose(m["bias"], 0.01)
    assert m["coverage_80"] == 1.0  # all actuals within [q10, q90]
    assert np.isclose(m["mean_interval_width"], 9.25)


def test_seasonal_naive_baseline():
    dates = pd.date_range("2024-01-01", periods=28, freq="D")
    df = pd.DataFrame({
        "timestamp": dates,
        "target": [(i % 7) * 5.0 for i in range(28)],
    })
    fc = forecast_seasonal_naive(df, horizon=14, frequency="D")
    assert len(fc) == 14
    # Daily seasonality repeats every 7 days
    assert fc["median"].iloc[0] == df["target"].iloc[-7]
    assert fc["median"].iloc[7] == df["target"].iloc[-7]


def test_generate_backtest_cutoffs():
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    cutoffs = generate_backtest_cutoffs(dates, horizon=14, num_cutoffs=3, min_context=30)
    assert len(cutoffs) == 3
    assert cutoffs[-1] == 100 - 14  # Max cutoff
    assert cutoffs[0] >= 30         # Min context satisfied
