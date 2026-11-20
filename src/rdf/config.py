"""Central settings. Change values here, not inside other modules."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
STORAGE_DIR = PROJECT_ROOT / "storage"
RAW_DIR = STORAGE_DIR / "raw"
PROCESSED_DIR = STORAGE_DIR / "processed"
MODELS_DIR = STORAGE_DIR / "models"
DB_PATH = STORAGE_DIR / "metadata.db"
MAX_UPLOAD_MB = int(os.environ.get("RDF_MAX_UPLOAD_MB", "100"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

# Create directories if they do not exist
for _dir in (STORAGE_DIR, RAW_DIR, PROCESSED_DIR, MODELS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

MODEL_ID = "amazon/chronos-2"        # official pretrained weights (120M params)
MODEL_PATH = MODEL_ID                # optional: set to "models/<tag>" to test a fine-tuned checkpoint
CONTEXT_LENGTH: int | None = None    # set to winning validation context_length (None = model default)
CROSS_LEARNING: bool = False         # set to winning validation cross_learning flag
DEFAULT_HORIZON = 28
MIN_HORIZON, MAX_HORIZON = 7, 90
QUANTILES = [0.1, 0.5, 0.9]

# M5 day index d_1 is 2011-01-29 (official M5 calendar.csv)
M5_START_DATE = "2011-01-29"
