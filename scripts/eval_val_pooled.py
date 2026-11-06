import sys
sys.path.insert(0, ".")
import numpy as np
import pandas as pd
from src.evaluation.metrics import compute_wape
from src.models.baselines import (
    WeekdayMean8WModel,
    MovingAverage91DModel,
    CrostonSBAModel,
    SeasonalNaiveModel,
)
from src.models.blends import blend_predictions
from src.models.demand_prophet import ProphetDemandModel
import json

df_demand = pd.read_parquet("data/processed/demand.parquet")
df_lt = pd.read_parquet("data/processed/lead_time.parquet")
lt_means = df_lt.groupby(["material", "area"])["lead_time_days"].mean().to_dict()

with open("artifacts/metrics/champion_model_selection.json", "r") as f:
    sel_data = json.load(f)

test_days = 84
val_days = 84

# Candidate models evaluated per pair on validation
# Let's generate weekly predictions on the 84-day val window (12 weeks) and 28-day window (4 weeks)
pairs = df_demand[["material", "area"]].drop_duplicates().values.tolist()

val_preds = {m: [] for m in ["weekday_mean_8w", "moving_average_91d", "croston_sba", "seasonal_naive", "blend_prophet_wm8w", "prophet_tuned"]}
val_actuals = []

print("Simulating baseline validation predictions...")
# For fast computation, load the actuals and baseline predictions
# Let's see if we have prophet tuned predictions cached or if we can re-evaluate
