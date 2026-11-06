"""Baseline forecasting models for Raphael.

Provides:
- NaiveModel: Projects last observed historical demand.
- SeasonalNaiveModel: Projects historical demand from same day of week (7-day cycle).
- WeekdayMean8WModel: Day-of-week average over the past 8 weeks (56 days).
- MovingAverage28DModel: Flat average over the past 28 days.
- MovingAverage91DModel: Flat average over the past 91 days (13 weeks).
- CrostonSBAModel: Syntetos-Boylan Approximation for intermittent demand.
All baseline models strictly clip predictions at 0.0.
"""
from pathlib import Path
import pickle
from typing import Optional
import numpy as np
import pandas as pd
from src.models.registry import BaseModel, ModelRegistry


@ModelRegistry.register("naive")
class NaiveModel(BaseModel):
    """Naive persistence forecast (repeats last observed value)."""

    def __init__(self):
        self.last_value: Optional[float] = None

    def fit(self, df: pd.DataFrame, target_col: str = "y", **kwargs) -> "NaiveModel":
        if df.empty or target_col not in df.columns:
            raise ValueError(f"Input DataFrame must contain non-empty '{target_col}' column.")
        self.last_value = max(0.0, float(df[target_col].iloc[-1]))
        return self

    def predict(self, df_future: pd.DataFrame, **kwargs) -> pd.DataFrame:
        if self.last_value is None:
            raise RuntimeError("Model must be fitted before predict.")
        res = df_future[["ds"]].copy() if "ds" in df_future.columns else pd.DataFrame(index=df_future.index)
        res["yhat"] = self.last_value
        res["yhat_lower_80"] = self.last_value
        res["yhat_upper_80"] = self.last_value
        res["yhat_lower_95"] = self.last_value
        res["yhat_upper_95"] = self.last_value
        return res

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"last_value": self.last_value}, f)

    @classmethod
    def load(cls, path: Path) -> "NaiveModel":
        with open(path, "rb") as f:
            data = pickle.load(f)
        m = cls()
        m.last_value = data["last_value"]
        return m


@ModelRegistry.register("seasonal_naive")
class SeasonalNaiveModel(BaseModel):
    """Seasonal naive forecast (repeats weekly 7-day seasonal values)."""

    def __init__(self, season_length: int = 7):
        self.season_length = season_length
        self.last_season: Optional[np.ndarray] = None

    def fit(self, df: pd.DataFrame, target_col: str = "y", **kwargs) -> "SeasonalNaiveModel":
        if len(df) < self.season_length or target_col not in df.columns:
            raise ValueError(f"DataFrame must have at least {self.season_length} rows.")
        vals = df[target_col].iloc[-self.season_length:].to_numpy(dtype=float)
        self.last_season = np.maximum(0.0, vals)
        return self

    def predict(self, df_future: pd.DataFrame, **kwargs) -> pd.DataFrame:
        if self.last_season is None:
            raise RuntimeError("Model must be fitted before predict.")
        n_periods = len(df_future)
        reps = int(np.ceil(n_periods / self.season_length))
        preds = np.tile(self.last_season, reps)[:n_periods]

        res = df_future[["ds"]].copy() if "ds" in df_future.columns else pd.DataFrame(index=df_future.index)
        res["yhat"] = preds
        res["yhat_lower_80"] = preds
        res["yhat_upper_80"] = preds
        res["yhat_lower_95"] = preds
        res["yhat_upper_95"] = preds
        return res

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"season_length": self.season_length, "last_season": self.last_season}, f)

    @classmethod
    def load(cls, path: Path) -> "SeasonalNaiveModel":
        with open(path, "rb") as f:
            data = pickle.load(f)
        m = cls(season_length=data["season_length"])
        m.last_season = data["last_season"]
        return m


@ModelRegistry.register("weekday_mean_8w")
class WeekdayMean8WModel(BaseModel):
    """Forecast by day-of-week average over the past 8 weeks (56 days)."""

    def __init__(self, weeks: int = 8):
        self.weeks = weeks
        self.window_days = weeks * 7
        self.weekday_means: dict = {}
        self.fallback_mean: float = 0.0

    def fit(self, df: pd.DataFrame, target_col: str = "y", date_col: str = "ds", **kwargs) -> "WeekdayMean8WModel":
        if len(df) == 0:
            raise ValueError("Input DataFrame cannot be empty.")
        df_sorted = df.sort_values(date_col)
        recent = df_sorted.iloc[-self.window_days:]
        self.fallback_mean = max(0.0, float(recent[target_col].mean()))
        
        # Calculate mean for each day of week (0=Monday, 6=Sunday)
        dow_series = pd.to_datetime(recent[date_col]).dt.dayofweek
        means = recent.groupby(dow_series)[target_col].mean().to_dict()
        self.weekday_means = {k: max(0.0, float(v)) for k, v in means.items()}
        return self

    def predict(self, df_future: pd.DataFrame, date_col: str = "ds", **kwargs) -> pd.DataFrame:
        dow = pd.to_datetime(df_future[date_col]).dt.dayofweek
        preds = np.array([self.weekday_means.get(d, self.fallback_mean) for d in dow], dtype=float)
        preds = np.maximum(0.0, preds)

        res = df_future[[date_col]].copy()
        res["yhat"] = preds
        res["yhat_lower_80"] = preds
        res["yhat_upper_80"] = preds
        res["yhat_lower_95"] = preds
        res["yhat_upper_95"] = preds
        return res

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"weekday_means": self.weekday_means, "fallback_mean": self.fallback_mean}, f)

    @classmethod
    def load(cls, path: Path) -> "WeekdayMean8WModel":
        with open(path, "rb") as f:
            data = pickle.load(f)
        m = cls()
        m.weekday_means = data["weekday_means"]
        m.fallback_mean = data["fallback_mean"]
        return m


@ModelRegistry.register("moving_average_28d")
class MovingAverage28DModel(BaseModel):
    """Flat moving average forecast over the past 28 days."""

    def __init__(self, window_days: int = 28):
        self.window_days = window_days
        self.ma_value: float = 0.0

    def fit(self, df: pd.DataFrame, target_col: str = "y", **kwargs) -> "MovingAverage28DModel":
        recent = df[target_col].iloc[-self.window_days:]
        self.ma_value = max(0.0, float(recent.mean())) if len(recent) > 0 else 0.0
        return self

    def predict(self, df_future: pd.DataFrame, **kwargs) -> pd.DataFrame:
        n = len(df_future)
        res = df_future[["ds"]].copy() if "ds" in df_future.columns else pd.DataFrame(index=df_future.index)
        preds = np.full(n, self.ma_value, dtype=float)
        res["yhat"] = preds
        res["yhat_lower_80"] = preds
        res["yhat_upper_80"] = preds
        res["yhat_lower_95"] = preds
        res["yhat_upper_95"] = preds
        return res

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"window_days": self.window_days, "ma_value": self.ma_value}, f)

    @classmethod
    def load(cls, path: Path) -> "MovingAverage28DModel":
        with open(path, "rb") as f:
            data = pickle.load(f)
        m = cls(window_days=data["window_days"])
        m.ma_value = data["ma_value"]
        return m


@ModelRegistry.register("moving_average_91d")
class MovingAverage91DModel(BaseModel):
    """Flat moving average forecast over the past 91 days (13 weeks)."""

    def __init__(self, window_days: int = 91):
        self.window_days = window_days
        self.ma_value: float = 0.0

    def fit(self, df: pd.DataFrame, target_col: str = "y", **kwargs) -> "MovingAverage91DModel":
        recent = df[target_col].iloc[-self.window_days:]
        self.ma_value = max(0.0, float(recent.mean())) if len(recent) > 0 else 0.0
        return self

    def predict(self, df_future: pd.DataFrame, **kwargs) -> pd.DataFrame:
        n = len(df_future)
        res = df_future[["ds"]].copy() if "ds" in df_future.columns else pd.DataFrame(index=df_future.index)
        preds = np.full(n, self.ma_value, dtype=float)
        res["yhat"] = preds
        res["yhat_lower_80"] = preds
        res["yhat_upper_80"] = preds
        res["yhat_lower_95"] = preds
        res["yhat_upper_95"] = preds
        return res

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"window_days": self.window_days, "ma_value": self.ma_value}, f)

    @classmethod
    def load(cls, path: Path) -> "MovingAverage91DModel":
        with open(path, "rb") as f:
            data = pickle.load(f)
        m = cls(window_days=data["window_days"])
        m.ma_value = data["ma_value"]
        return m


@ModelRegistry.register("croston_sba")
class CrostonSBAModel(BaseModel):
    """Croston's method with Syntetos-Boylan Approximation (SBA) for intermittent demand."""

    def __init__(self, alpha: float = 0.1):
        self.alpha = alpha
        self.rate: float = 0.0

    def fit(self, df: pd.DataFrame, target_col: str = "y", **kwargs) -> "CrostonSBAModel":
        vals = df[target_col].to_numpy(dtype=float)
        non_zeros = np.where(vals > 0)[0]
        if len(non_zeros) == 0:
            self.rate = 0.0
            return self

        # Inter-arrival intervals and non-zero demand sizes
        intervals = np.diff(np.insert(non_zeros, 0, -1))
        sizes = vals[non_zeros]

        z = sizes[0]
        p = intervals[0]
        for i in range(1, len(sizes)):
            z = self.alpha * sizes[i] + (1.0 - self.alpha) * z
            p = self.alpha * intervals[i] + (1.0 - self.alpha) * p

        # Syntetos-Boylan debiasing factor
        sba_factor = 1.0 - (self.alpha / 2.0)
        self.rate = max(0.0, float(sba_factor * (z / p))) if p > 0 else 0.0
        return self

    def predict(self, df_future: pd.DataFrame, **kwargs) -> pd.DataFrame:
        n = len(df_future)
        res = df_future[["ds"]].copy() if "ds" in df_future.columns else pd.DataFrame(index=df_future.index)
        preds = np.full(n, self.rate, dtype=float)
        res["yhat"] = preds
        res["yhat_lower_80"] = preds
        res["yhat_upper_80"] = preds
        res["yhat_lower_95"] = preds
        res["yhat_upper_95"] = preds
        return res

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"alpha": self.alpha, "rate": self.rate}, f)

    @classmethod
    def load(cls, path: Path) -> "CrostonSBAModel":
        with open(path, "rb") as f:
            data = pickle.load(f)
        m = cls(alpha=data["alpha"])
        m.rate = data["rate"]
        return m
