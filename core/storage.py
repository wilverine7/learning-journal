"""JSON / JSONL persistence for the learning journal."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.paths import (
    CONFIG_PATH,
    DEFAULT_CONFIG,
    JOURNAL_DIR,
    PATTERNS_PATH,
    PROJECTS_PATH,
    PROMPTS_PATH,
    REVIEW_LOG_PATH,
    SIGNALS_PATH,
    STATE_PATH,
    TOPICS_PATH,
)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def ensure_journal() -> None:
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n", encoding="utf-8")
    if not PROJECTS_PATH.exists():
        PROJECTS_PATH.write_text("{}\n", encoding="utf-8")
    if not PATTERNS_PATH.exists():
        PATTERNS_PATH.write_text("[]\n", encoding="utf-8")
    if not TOPICS_PATH.exists():
        TOPICS_PATH.write_text(json.dumps({"version": 1, "topics": {}}, indent=2) + "\n", encoding="utf-8")
    if not STATE_PATH.exists():
        STATE_PATH.write_text(
            json.dumps(
                {
                    "prompts_line": 0,
                    "signals_line": 0,
                    "last_merge_at": None,
                    "prompts_by_generation": {},
                    "backfilled_transcripts": {},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    for path in (PROMPTS_PATH, SIGNALS_PATH, REVIEW_LOG_PATH):
        path.touch(exist_ok=True)


def load_config() -> dict[str, Any]:
    ensure_journal()
    config = load_json(CONFIG_PATH, DEFAULT_CONFIG.copy())
    merged = DEFAULT_CONFIG.copy()
    merged.update(config)
    return merged


def load_patterns() -> list[dict[str, Any]]:
    ensure_journal()
    patterns = load_json(PATTERNS_PATH, [])
    return patterns if isinstance(patterns, list) else []


def load_projects() -> dict[str, Any]:
    ensure_journal()
    projects = load_json(PROJECTS_PATH, {})
    return projects if isinstance(projects, dict) else {}


def load_state() -> dict[str, Any]:
    ensure_journal()
    state = load_json(
        STATE_PATH,
        {
            "prompts_line": 0,
            "signals_line": 0,
            "last_merge_at": None,
            "prompts_by_generation": {},
            "backfilled_transcripts": {},
        },
    )
    if "prompts_by_generation" not in state:
        state["prompts_by_generation"] = {}
    if "backfilled_transcripts" not in state:
        state["backfilled_transcripts"] = {}
    return state


def save_state(state: dict[str, Any]) -> None:
    save_json(STATE_PATH, state)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    ensure_journal()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl_from_line(path: Path, start_line: int) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        return [], start_line
    records: list[dict[str, Any]] = []
    line_no = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line_no += 1
            if line_no <= start_line:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                records.append(parsed)
    return records, line_no
