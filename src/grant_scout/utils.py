"""
Shared utilities: paths, config loading, date helpers, logging.
"""

import os
import logging
from pathlib import Path
from datetime import datetime, timezone

import yaml
from dateutil import parser as dateutil_parser


# ---------------------------------------------------------------------------
# Paths – all relative to the project root (two levels above this file)
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

# Make sure output dirs exist at import time
DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def get_logger(name: str) -> logging.Logger:
    """Return a logger with a consistent format."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
        handler.setFormatter(fmt)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_topics_config() -> dict:
    """Load config/topics.yml and return as a dict."""
    path = CONFIG_DIR / "topics.yml"
    if not path.exists():
        raise FileNotFoundError(f"Topics config not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def parse_date(raw: str | None) -> datetime | None:
    """Parse a date string into a timezone-aware datetime, or None."""
    if not raw:
        return None
    try:
        dt = dateutil_parser.parse(str(raw))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def format_date(dt: datetime | None, fmt: str = "%Y-%m-%d") -> str:
    """Format a datetime to a string, or return empty string."""
    if dt is None:
        return ""
    return dt.strftime(fmt)


def now_utc() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------

def get_env(key: str, default: str = "") -> str:
    """Read an environment variable with a fallback."""
    return os.environ.get(key, default)


def has_claude_key() -> bool:
    """Check whether a Claude API key is configured."""
    return bool(get_env("CLAUDE_API_KEY"))
