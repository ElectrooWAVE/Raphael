"""Chronos-2 forecasting. Model loading is separate from prediction requests.

Official API (chronos-forecasting 2.x, verified against the amazon-science repo):
    pipeline = Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map=...)
    pred_df  = pipeline.predict_df(df, id_column=..., timestamp_column=...,
                                   target=..., prediction_length=..., quantile_levels=[...])
"""
from __future__ import annotations

import pandas as pd

from .config import MODEL_ID

DENSE_QUANTILES = [round(0.05 * i, 2) for i in range(1, 20)]


class ForecastError(RuntimeError):
    """Raised with a readable message when loading or inference fails."""


def pick_device() -> str:
    import torch
    return "cuda" if torch.cuda.is_available() else "cpu"


def load_pipeline(model_id: str = MODEL_ID):
    """Load pretrained Chronos-2 ONCE. Returns (pipeline, device)."""
    try:
        from chronos import Chronos2Pipeline
    except ImportError as e:
        raise ForecastError(
            "chronos-forecasting is not installed (need >=2.x for Chronos-2). "
            "Run: pip install -r requirements.txt"
        ) from e
    device = pick_device()
    try:
        pipeline = Chronos2Pipeline.from_pretrained(model_id, device_map=device)
    except Exception as e:  # network, disk, CUDA, etc.
        raise ForecastError(f"Could not load '{model_id}' on {device}: {e}") from e
    return pipeline, device


def forecast(pipeline, history: pd.DataFrame, horizon: int, series_id: str = "item") -> pd.DataFrame:
    """history: [date, sales] daily. Returns [date, median, expected, q10, q50, q90].

    Values are real Chronos-2 outputs clipped at 0 (retail demand cannot be negative).
    `median` is the Chronos-2 point prediction (50th percentile). `expected` is an
    approximate mean computed by averaging the dense quantile grid 0.05, 0.10, ..., 0.95.
    """
    if horizon < 1:
        raise ForecastError("Horizon must be at least 1 day.")
    ctx = history.dropna(subset=["sales"])
    if len(ctx) < 30:
        raise ForecastError("Need at least 30 days of history to forecast.")

    df = pd.DataFrame({"item_id": series_id, "timestamp": history["date"], "target": history["sales"]})
    try:
        out = pipeline.predict_df(
            df,
            id_column="item_id",
            timestamp_column="timestamp",
            target="target",
            prediction_length=horizon,
            quantile_levels=DENSE_QUANTILES,
            freq="D",
        )
    except Exception as e:
        raise ForecastError(f"Chronos-2 inference failed: {e}") from e

    q_cols = [str(q) for q in DENSE_QUANTILES]
    dense_clipped = out[q_cols].clip(lower=0)
    res = pd.DataFrame({
        "date": pd.to_datetime(out["timestamp"]).values,
        "median": out["predictions"].clip(lower=0).values,
        "expected": dense_clipped.mean(axis=1).values,
        "q10": out["0.1"].clip(lower=0).values,
        "q50": out["0.5"].clip(lower=0).values,
        "q90": out["0.9"].clip(lower=0).values,
    })
    return res
