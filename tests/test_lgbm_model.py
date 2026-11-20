"""Unit tests for Custom Recursive LightGBM Forecaster."""
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from rdf.features import build_series_features, get_default_feature_config
from rdf.lgbm_forecaster import LightGBMForecaster


@pytest.fixture
def synthetic_history() -> pd.DataFrame:
    dates = pd.date_range("2023-01-01", periods=120, freq="D")
    # Base trend + weekly seasonality + noise
    t = np.arange(120)
    seasonal = 10.0 * np.sin(2 * np.pi * t / 7.0)
    sales = np.clip(20.0 + 0.1 * t + seasonal, 0, None)
    return pd.DataFrame({"timestamp": dates, "target": sales, "series_id": "test_item"})


def test_no_data_leakage_in_features(synthetic_history: pd.DataFrame):
    cfg = get_default_feature_config("D")
    df_feat, cols = build_series_features(synthetic_history, cfg)

    # lag_1 at index i must equal target at index i-1
    assert df_feat["lag_1"].iloc[10] == synthetic_history["target"].iloc[9]
    assert df_feat["lag_7"].iloc[10] == synthetic_history["target"].iloc[3]

    # rolling_mean_7 at index 10 must be the mean of indices 3 to 9 (not including 10)
    expected_mean = synthetic_history["target"].iloc[3:10].mean()
    assert np.isclose(df_feat["rolling_mean_7"].iloc[10], expected_mean)


def test_lgbm_train_and_recursive_predict(synthetic_history: pd.DataFrame, tmp_path: Path):
    forecaster = LightGBMForecaster(
        hyperparameters={"n_estimators": 25, "learning_rate": 0.1, "verbose": -1}
    )
    meta = forecaster.fit(synthetic_history, val_fraction=0.2)
    assert "mae" in meta["metrics"]
    assert "rmse" in meta["metrics"]

    # Test recursive prediction for 7, 28, and custom 45 steps
    for h in [7, 28, 45]:
        pred = forecaster.predict_recursive(synthetic_history.iloc[:80], horizon=h, series_id="test_item")
        assert len(pred) == h
        assert "median" in pred.columns
        assert "q10" in pred.columns
        assert "q90" in pred.columns

        # Verify quantile ordering
        assert (pred["q10"] <= pred["median"] + 1e-6).all()
        assert (pred["median"] <= pred["q90"] + 1e-6).all()

        # Verify retail non-negativity
        assert (pred["median"] >= 0.0).all()
        assert (pred["q10"] >= 0.0).all()

    # Test artifact save and load
    save_file = tmp_path / "model.pkl"
    forecaster.save(save_file)
    assert save_file.exists()

    loaded = LightGBMForecaster.load(save_file)
    pred_loaded = loaded.predict_recursive(synthetic_history.iloc[:80], horizon=14, series_id="test_item")
    assert len(pred_loaded) == 14
    assert np.allclose(pred_loaded["median"], forecaster.predict_recursive(synthetic_history.iloc[:80], horizon=14)["median"])
