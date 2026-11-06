"""Model interface and registry for Raphael models.

Every model in Raphael implements the BaseModel interface:
fit, predict, save, and load.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional
import pandas as pd


class BaseModel(ABC):
    """Abstract base class for Raphael time series and predictive models."""

    @abstractmethod
    def fit(self, df: pd.DataFrame, **kwargs) -> "BaseModel":
        """Fit model on input DataFrame."""
        pass

    @abstractmethod
    def predict(self, df_future: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """Generate predictions for future DataFrame."""
        pass

    @abstractmethod
    def save(self, path: Path) -> None:
        """Persist model state to disk."""
        pass

    @classmethod
    @abstractmethod
    def load(cls, path: Path) -> "BaseModel":
        """Restore model from disk."""
        pass


class ModelRegistry:
    """Registry pattern for discovering and instantiating Raphael models."""

    _registry: Dict[str, Any] = {}

    @classmethod
    def register(cls, name: str):
        """Decorator to register a model class."""
        def decorator(subclass):
            cls._registry[name] = subclass
            return subclass
        return decorator

    @classmethod
    def get(cls, name: str) -> Any:
        """Retrieve a model class by name."""
        if name not in cls._registry:
            raise KeyError(f"Model '{name}' not found in registry. Registered models: {list(cls._registry.keys())}")
        return cls._registry[name]

    @classmethod
    def list_models(cls) -> list:
        """List all registered model identifiers."""
        return list(cls._registry.keys())
