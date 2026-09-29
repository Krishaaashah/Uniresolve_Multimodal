"""Configuration settings and constants for Business Entity Resolution Pipeline."""
import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
ZIP_PATH = PROJECT_ROOT / "student_resource.zip"
DATASET_DIR = BASE_DIR / "dataset"
OUTPUT_DIR = BASE_DIR / "output"
MODELS_DIR = BASE_DIR / "models"

MATCHING_OUTPUT_FILE = OUTPUT_DIR / "matching_results.tsv"
CANDIDATE_OUTPUT_FILE = OUTPUT_DIR / "candidate_pairs.tsv"

# Country partitions
SUPPORTED_COUNTRIES = ["US", "India", "France"]

# Blocking Hyperparameters
BLOCKING_PREFIX_LEN = 3
MIN_TOKEN_LEN = 4
MAX_DOC_FREQ_THRESHOLD = 300
MAX_CANDIDATES_PER_ENTITY = 250

# GBDT Matcher Hyperparameters
GBDT_PARAMS = {
    "objective": "binary",
    "metric": "binary_logloss",
    "boosting_type": "gbdt",
    "num_leaves": 31,
    "learning_rate": 0.05,
    "n_estimators": 250,
    "feature_fraction": 0.85,
    "verbose": -1,
    "n_jobs": -1,
    "random_state": 42
}

# Postprocessing Hyperparameters
DEFAULT_F05_THRESHOLD = 0.28
ENFORCE_TARGET_UNIQUENESS = True
