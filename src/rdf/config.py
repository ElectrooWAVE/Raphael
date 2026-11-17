"""Central settings. Change values here, not inside other modules."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

MODEL_ID = "amazon/chronos-2"        # official pretrained weights (120M params)
DEFAULT_HORIZON = 28
MIN_HORIZON, MAX_HORIZON = 7, 90
QUANTILES = [0.1, 0.5, 0.9]

# M5 day index d_1 is 2011-01-29 (official M5 calendar.csv)
M5_START_DATE = "2011-01-29"
