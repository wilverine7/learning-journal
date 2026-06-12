"""Journal storage paths (tool-agnostic)."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_JOURNAL_HOME = Path.home() / ".cursor" / "learning-journal"


def journal_home() -> Path:
    override = os.environ.get("LEARNING_JOURNAL_HOME", "").strip()
    if override:
        return Path(override).expanduser()
    return DEFAULT_JOURNAL_HOME


JOURNAL_DIR = journal_home()
CONFIG_PATH = JOURNAL_DIR / "config.json"
PROJECTS_PATH = JOURNAL_DIR / "projects.json"
PATTERNS_PATH = JOURNAL_DIR / "patterns.json"
PROMPTS_PATH = JOURNAL_DIR / "prompts.jsonl"
SIGNALS_PATH = JOURNAL_DIR / "signals.jsonl"
TOPICS_PATH = JOURNAL_DIR / "topics.json"
REVIEW_LOG_PATH = JOURNAL_DIR / "review-log.jsonl"
STATE_PATH = JOURNAL_DIR / "state.json"

DEFAULT_CONFIG: dict = {
    "reviews_required_for_learned": 5,
    "min_exposures_for_queue": 3,
    "merge_debounce_seconds": 45,
    "default_review_window_days": 7,
    "max_events_per_topic": 50,
}
