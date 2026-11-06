"""Prophet demand forecasting wrapper for Raphael.

Implements BaseModel interface with:
- Linear growth, yearly + weekly seasonality, US country holidays
- is_promotion extra regressor
- Dual 80% and 95% confidence interval extraction
- Strictly non-negative clipping at 0.0 for demand count forecasts and bounds
- Promotion coefficient extraction and residual std calculation
"""
import io
import logging
import pickle
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import numpy as np
import pandas as pd

# Suppress cmdstanpy and prophet noise during import
_old_stderr = sys.stderr
sys.stderr = io.StringIO()
try:
    import cmdstanpy
    _cmd_logger = cmdstanpy.utils.get_logger()
    _cmd_logger.setLevel(logging.ERROR)
    for _h in _cmd_logger.handlers[:]:
        _cmd_logger.removeHandler(_h)
    _cmd_logger.addHandler(logging.NullHandler())
    from prophet import Prophet
    from prophet.utilities import regressor_coefficients
    logging.getLogger("prophet").setLevel(logging.ERROR)
finally:
    sys.stderr = _old_stderr

from src.models.registry import BaseModel, ModelRegistry


def _silence_stan():
    """Ensure child/worker processes also silence cmdstanpy output."""
    try:
        c_log = cmdstanpy.utils.get_logger()
        c_log.setLevel(logging.ERROR)
        for h in c_log.handlers[:]:
            c_log.removeHandler(h)
        c_log.addHandler(logging.NullHandler())
        logging.getLogger("prophet").setLevel(logging.ERROR)
    except Exception:
        pass


@ModelRegistry.register("prophet")
class ProphetDemandModel(BaseModel):
    """Wrapper around Facebook Prophet tailored for Raphael materials demand."""

    def __init__(
        self,
        growth: str = "linear",
        yearly_seasonality: bool = True,
        weekly_seasonality: bool = True,
        daily_seasonality: bool = False,
        country_holidays: str = "US",
        clip_lower_bound: float = 0.0,
        changepoint_prior_scale: float = 0.05,
        seasonality_prior_scale: float = 10.0,
        holidays_prior_scale: float = 10.0,
    ):
        self.growth = growth
        self.yearly_seasonality = yearly_seasonality
        self.weekly_seasonality = weekly_seasonality
        self.daily_seasonality = daily_seasonality
        self.country_holidays = country_holidays
        self.clip_lower_bound = clip_lower_bound
        self.changepoint_prior_scale = changepoint_prior_scale
        self.seasonality_prior_scale = seasonality_prior_scale
        self.holidays_prior_scale = holidays_prior_scale

        self.model: Optional[Prophet] = None
        self.promo_coef: Optional[float] = None
        self.residual_std: Optional[float] = None
        self.in_sample_metrics: Dict[str, float] = {}

    def _init_prophet(self) -> Prophet:
        m = Prophet(
            growth=self.growth,
            yearly_seasonality=self.yearly_seasonality,
            weekly_seasonality=self.weekly_seasonality,
            daily_seasonality=self.daily_seasonality,
            interval_width=0.95,
            changepoint_prior_scale=self.changepoint_prior_scale,
            seasonality_prior_scale=self.seasonality_prior_scale,
            holidays_prior_scale=self.holidays_prior_scale,
        )
        if self.country_holidays:
            m.add_country_holidays(country_name=self.country_holidays)
        m.add_regressor("is_promotion")
        return m

    def fit(self, df: pd.DataFrame, **kwargs) -> "ProphetDemandModel":
        """Fit Prophet on DataFrame containing 'ds', 'y', and 'is_promotion'."""
        _silence_stan()
        if not {"ds", "y", "is_promotion"}.issubset(df.columns):
            raise ValueError("Training DataFrame must contain columns: 'ds', 'y', 'is_promotion'")

        self.model = self._init_prophet()
        # Fit model
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.model.fit(df)

        # Extract promotion coefficient
        try:
            coef_df = regressor_coefficients(self.model)
            promo_row = coef_df[coef_df["regressor"] == "is_promotion"]
            if not promo_row.empty:
                self.promo_coef = float(promo_row["coef"].iloc[0])
            else:
                self.promo_coef = 0.0
        except Exception:
            self.promo_coef = 0.0

        # Compute in-sample residuals and daily residual standard deviation
        in_sample = self.predict(df[["ds", "is_promotion"]])
        residuals = df["y"].to_numpy() - in_sample["yhat"].to_numpy()
        self.residual_std = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.0
        return self

    def predict(self, df_future: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """Predict future periods with dual 95% and 80% intervals, clipped at 0."""
        _silence_stan()
        if self.model is None:
            raise RuntimeError("Model has not been fitted. Call fit() first.")
        if not {"ds", "is_promotion"}.issubset(df_future.columns):
            raise ValueError("Future DataFrame must contain 'ds' and 'is_promotion'.")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # 1. Predict 95% intervals
            self.model.interval_width = 0.95
            fc_95 = self.model.predict(df_future)

            # 2. Predict 80% intervals
            self.model.interval_width = 0.80
            fc_80 = self.model.predict(df_future)

        res = pd.DataFrame()
        res["ds"] = pd.to_datetime(fc_95["ds"])
        res["yhat"] = np.maximum(self.clip_lower_bound, fc_95["yhat"].to_numpy(dtype=float))

        # 95% bounds
        res["yhat_lower_95"] = np.maximum(self.clip_lower_bound, fc_95["yhat_lower"].to_numpy(dtype=float))
        res["yhat_upper_95"] = np.maximum(self.clip_lower_bound, fc_95["yhat_upper"].to_numpy(dtype=float))

        # 80% bounds
        res["yhat_lower_80"] = np.maximum(self.clip_lower_bound, fc_80["yhat_lower"].to_numpy(dtype=float))
        res["yhat_upper_80"] = np.maximum(self.clip_lower_bound, fc_80["yhat_upper"].to_numpy(dtype=float))

        # Components for interpretation
        if "is_promotion" in fc_95.columns:
            res["promo_effect"] = fc_95["is_promotion"].to_numpy(dtype=float)
        if "trend" in fc_95.columns:
            res["trend"] = fc_95["trend"].to_numpy(dtype=float)
        if "weekly" in fc_95.columns:
            res["weekly"] = fc_95["weekly"].to_numpy(dtype=float)
        if "yearly" in fc_95.columns:
            res["yearly"] = fc_95["yearly"].to_numpy(dtype=float)

        return res

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "config": {
                "growth": self.growth,
                "yearly_seasonality": self.yearly_seasonality,
                "weekly_seasonality": self.weekly_seasonality,
                "daily_seasonality": self.daily_seasonality,
                "country_holidays": self.country_holidays,
                "clip_lower_bound": self.clip_lower_bound,
                "changepoint_prior_scale": self.changepoint_prior_scale,
                "seasonality_prior_scale": self.seasonality_prior_scale,
                "holidays_prior_scale": self.holidays_prior_scale,
            },
            "model": self.model,
            "promo_coef": self.promo_coef,
            "residual_std": self.residual_std,
        }
        with open(path, "wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, path: Path) -> "ProphetDemandModel":
        with open(path, "rb") as f:
            payload = pickle.load(f)
        instance = cls(**payload["config"])
        instance.model = payload["model"]
        instance.promo_coef = payload.get("promo_coef", 0.0)
        instance.residual_std = payload.get("residual_std", 0.0)
        return instance
