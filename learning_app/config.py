from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("APP_DATA_DIR", str(BASE_DIR / "data"))).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_DB_PATH = DATA_DIR / "learning_app.db"
DB_PATH = Path(os.getenv("APP_DB_PATH", str(DEFAULT_DB_PATH))).resolve()

DEFAULT_EXPLANATION_LANGUAGE = os.getenv("APP_EXPLANATION_LANGUAGE", "es").strip().lower() or "es"
DEFAULT_GOAL_EXAM = os.getenv("APP_DEFAULT_GOAL_EXAM", "goethe_b2").strip().lower() or "goethe_b2"
DEFAULT_UI_LANGUAGE = os.getenv("APP_UI_LANGUAGE", "de").strip().lower() or "de"
DEFAULT_RECOMMENDATION_STRATEGY = (
    os.getenv("APP_RECOMMENDATION_STRATEGY", "adaptive_heuristic_v1").strip().lower()
    or "adaptive_heuristic_v1"
)
DEFAULT_REVIEW_STRATEGY = (
    os.getenv("APP_REVIEW_STRATEGY", "sm2_v1").strip().lower()
    or "sm2_v1"
)
DEFAULT_ASSESSMENT_MODE = (
    os.getenv("APP_ASSESSMENT_MODE", "standard_v1").strip().lower()
    or "standard_v1"
)
LOCAL_USER_ID = 1
