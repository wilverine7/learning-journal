"""Cross-project learning journal: capture, classify, merge."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

JOURNAL_DIR = Path.home() / ".cursor" / "learning-journal"
CONFIG_PATH = JOURNAL_DIR / "config.json"
PROJECTS_PATH = JOURNAL_DIR / "projects.json"
PATTERNS_PATH = JOURNAL_DIR / "patterns.json"
PROMPTS_PATH = JOURNAL_DIR / "prompts.jsonl"
SIGNALS_PATH = JOURNAL_DIR / "signals.jsonl"
TOPICS_PATH = JOURNAL_DIR / "topics.json"
REVIEW_LOG_PATH = JOURNAL_DIR / "review-log.jsonl"
STATE_PATH = JOURNAL_DIR / "state.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "reviews_required_for_learned": 5,
    "min_exposures_for_queue": 3,
    "merge_debounce_seconds": 45,
    "default_review_window_days": 7,
    "max_events_per_topic": 50,
}

QUESTION_RE = re.compile(
    r"(?i)(?:^|\b)(?:what(?:'s|\s+is|\s+does|\s+do)|why(?:\s+do|\s+does|\s+are|\s+is|\s+not)?|how(?:\s+does|\s+do|\s+to|\s+can)?|explain|help me understand|can you explain|should i use|is it better|when should|what's the difference)",
)

REQUEST_VERBS_RE = re.compile(
    r"(?i)\b(?:add|use|implement|apply|introduce|switch to|refactor to|memoize|memoiz)\b",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def normalize_git_remote(url: str) -> str:
    cleaned = url.strip()
    if cleaned.startswith("git@"):
        host_path = cleaned.split(":", 1)
        if len(host_path) == 2:
            host, repo = host_path
            repo = repo.removesuffix(".git")
            return f"{host.replace('git@', '')}/{repo}"
    parsed = urlparse(cleaned)
    if parsed.netloc and parsed.path:
        repo = parsed.path.strip("/").removesuffix(".git")
        return f"{parsed.netloc}/{repo}"
    return cleaned.removesuffix(".git")


def project_id_for_root(workspace_root: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", workspace_root, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return normalize_git_remote(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    digest = hashlib.sha256(workspace_root.encode("utf-8")).hexdigest()[:16]
    return f"local:{digest}"


def project_label(project_id: str, workspace_root: str) -> str:
    projects = load_projects()
    entry = projects.get(project_id)
    if isinstance(entry, dict) and entry.get("label"):
        return str(entry["label"])
    if isinstance(entry, str):
        return entry
    if project_id.startswith("local:"):
        return Path(workspace_root).name
    parts = project_id.split("/")
    return parts[-1] if parts else project_id


def primary_workspace(payload: dict[str, Any]) -> str:
    roots = payload.get("workspace_roots") or []
    if roots:
        return str(roots[0])
    return os.getcwd()


def relativize_path(file_path: str, workspace_roots: list[str]) -> str:
    for root in workspace_roots:
        root_with_sep = root if root.endswith(os.sep) else root + os.sep
        if file_path == root:
            return "."
        if file_path.startswith(root_with_sep):
            return os.path.relpath(file_path, root)
    return file_path


def base_context(payload: dict[str, Any]) -> dict[str, Any]:
    workspace_root = primary_workspace(payload)
    project_id = project_id_for_root(workspace_root)
    return {
        "at": utc_now_iso(),
        "conversation_id": payload.get("conversation_id"),
        "generation_id": payload.get("generation_id"),
        "project_id": project_id,
        "project_label": project_label(project_id, workspace_root),
        "workspace_root": workspace_root,
        "workspace_name": Path(workspace_root).name,
    }


def looks_like_learning_question(prompt: str) -> bool:
    if "?" in prompt and len(prompt.strip()) > 8:
        return True
    return QUESTION_RE.search(prompt) is not None


def compile_pattern_list(values: list[str]) -> list[re.Pattern[str]]:
    compiled: list[re.Pattern[str]] = []
    for value in values:
        try:
            compiled.append(re.compile(value, re.IGNORECASE | re.MULTILINE))
        except re.error:
            continue
    return compiled


def load_pattern_catalog() -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for item in load_patterns():
        slug = item.get("slug")
        if not slug:
            continue
        catalog.append(
            {
                "slug": slug,
                "title": item.get("title") or slug,
                "code_res": compile_pattern_list(item.get("code_regex") or []),
                "mention_res": compile_pattern_list(item.get("mention_regex") or []),
                "question_res": compile_pattern_list(item.get("question_regex") or []),
                "keywords": [str(k).lower() for k in (item.get("keywords") or [])],
            }
        )
    return catalog


def match_patterns(text: str, regexes: list[re.Pattern[str]]) -> bool:
    return any(regex.search(text) for regex in regexes)


def detect_patterns_in_text(text: str, mode: str) -> list[str]:
    slugs: list[str] = []
    lowered = text.lower()
    for item in load_pattern_catalog():
        regex_key = "code_res" if mode == "code" else "mention_res" if mode == "mention" else "question_res"
        if match_patterns(text, item[regex_key]):
            slugs.append(item["slug"])
            continue
        if mode == "question" and any(keyword in lowered for keyword in item["keywords"]):
            slugs.append(item["slug"])
    return sorted(set(slugs))


def prompt_requested_pattern(prompt: str, slug: str, keywords: list[str]) -> bool:
    lowered = prompt.lower()
    if any(keyword in lowered for keyword in keywords):
        return REQUEST_VERBS_RE.search(prompt) is not None or not looks_like_learning_question(prompt)
    return False


def trim_excerpt(text: str, limit: int = 220) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def capture_prompt(payload: dict[str, Any]) -> None:
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        print(json.dumps({"continue": True}))
        return

    ctx = base_context(payload)
    attachments = payload.get("attachments") or []
    attached_files = [
        relativize_path(str(item.get("file_path")), payload.get("workspace_roots") or [])
        for item in attachments
        if isinstance(item, dict) and item.get("type") == "file" and item.get("file_path")
    ]

    record = {
        **ctx,
        "type": "user_prompt",
        "prompt": prompt,
        "prompt_excerpt": trim_excerpt(prompt),
        "is_learning_question": looks_like_learning_question(prompt),
        "matched_slugs": detect_patterns_in_text(prompt, "question"),
        "attached_files": attached_files,
    }
    append_jsonl(PROMPTS_PATH, record)

    state = load_state()
    generation_id = payload.get("generation_id")
    if generation_id:
        prompts_by_generation = state["prompts_by_generation"]
        prompts_by_generation[str(generation_id)] = {
            "prompt": prompt,
            "prompt_excerpt": record["prompt_excerpt"],
            "is_learning_question": record["is_learning_question"],
            "matched_slugs": record["matched_slugs"],
            "attached_files": attached_files,
            "project_id": ctx["project_id"],
            "project_label": ctx["project_label"],
            "workspace_root": ctx["workspace_root"],
            "at": ctx["at"],
        }
        if len(prompts_by_generation) > 500:
            keys = sorted(prompts_by_generation.keys(), key=lambda key: prompts_by_generation[key].get("at", ""))
            for key in keys[:-300]:
                prompts_by_generation.pop(key, None)
        save_state(state)

    print(json.dumps({"continue": True}))


def intent_for_generation(generation_id: str | None, slug: str, keywords: list[str]) -> str:
    if not generation_id:
        return "agent_initiated"
    state = load_state()
    prompt_entry = state["prompts_by_generation"].get(str(generation_id))
    if not prompt_entry:
        return "agent_initiated"
    prompt = str(prompt_entry.get("prompt") or "")
    if slug in (prompt_entry.get("matched_slugs") or []):
        if prompt_entry.get("is_learning_question"):
            return "user_question"
        return "fulfilled_request"
    if prompt_requested_pattern(prompt, slug, keywords):
        return "fulfilled_request"
    return "agent_initiated"


def capture_edit(payload: dict[str, Any]) -> None:
    ctx = base_context(payload)
    workspace_roots = payload.get("workspace_roots") or []
    file_path = str(payload.get("file_path") or "")
    relative_file = relativize_path(file_path, workspace_roots) if file_path else None
    edits = payload.get("edits") or []

    matched: dict[str, list[str]] = {}
    for edit in edits:
        if not isinstance(edit, dict):
            continue
        new_string = str(edit.get("new_string") or "")
        if not new_string:
            continue
        for slug in detect_patterns_in_text(new_string, "code"):
            matched.setdefault(slug, []).append(trim_excerpt(new_string, 160))

    if not matched:
        return

    catalog = {item["slug"]: item for item in load_pattern_catalog()}
    for slug, snippets in matched.items():
        keywords = catalog.get(slug, {}).get("keywords", [])
        append_jsonl(
            SIGNALS_PATH,
            {
                **ctx,
                "type": "agent_edit",
                "slug": slug,
                "file": relative_file,
                "snippets": snippets[:3],
                "intent": intent_for_generation(ctx.get("generation_id"), slug, keywords),
            },
        )


def capture_response(payload: dict[str, Any]) -> None:
    text = str(payload.get("text") or "").strip()
    if not text:
        return

    ctx = base_context(payload)
    slugs = detect_patterns_in_text(text, "mention")
    if not slugs:
        return

    recommendation = bool(
        re.search(r"(?i)\b(i(?:'ll| will)|we should|let's|better to|recommend|suggest|using)\b", text)
    )
    catalog = {item["slug"]: item for item in load_pattern_catalog()}

    for slug in slugs:
        keywords = catalog.get(slug, {}).get("keywords", [])
        append_jsonl(
            SIGNALS_PATH,
            {
                **ctx,
                "type": "agent_mention",
                "slug": slug,
                "text_excerpt": trim_excerpt(text),
                "is_recommendation": recommendation,
                "intent": intent_for_generation(ctx.get("generation_id"), slug, keywords),
            },
        )


def empty_topic(slug: str, title: str) -> dict[str, Any]:
    now = utc_now_iso()
    return {
        "slug": slug,
        "title": title,
        "status": "discovered",
        "review_pass_count": 0,
        "dismissed": False,
        "signals": {"user_questions": 0, "agent_edits": 0, "agent_mentions": 0},
        "first_seen_at": now,
        "last_seen_at": now,
        "events": [],
    }


def append_event(topic: dict[str, Any], event: dict[str, Any], config: dict[str, Any]) -> None:
    events = topic.setdefault("events", [])
    events.append(event)
    max_events = int(config.get("max_events_per_topic", 50))
    if len(events) > max_events:
        topic["events"] = events[-max_events:]
    topic["last_seen_at"] = event.get("at") or utc_now_iso()


def increment_signal(topic: dict[str, Any], signal_name: str) -> None:
    signals = topic.setdefault("signals", {"user_questions": 0, "agent_edits": 0, "agent_mentions": 0})
    signals[signal_name] = int(signals.get(signal_name, 0)) + 1


def upsert_topic(topics: dict[str, Any], slug: str, title: str) -> dict[str, Any]:
    if slug not in topics:
        topics[slug] = empty_topic(slug, title)
    elif not topics[slug].get("title"):
        topics[slug]["title"] = title
    return topics[slug]


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


def slug_title(slug: str) -> str:
    for item in load_patterns():
        if item.get("slug") == slug:
            return str(item.get("title") or slug)
    return slug.split("/")[-1].replace("-", " ")


def merge_pending(force: bool = False) -> None:
    config = load_config()
    state = load_state()
    now = time.time()
    last_merge_at = state.get("last_merge_at")
    debounce = int(config.get("merge_debounce_seconds", 45))
    if not force and last_merge_at:
        try:
            last_ts = datetime.fromisoformat(str(last_merge_at).replace("Z", "+00:00")).timestamp()
        except ValueError:
            last_ts = 0.0
        if now - last_ts < debounce:
            return

    topics_doc = load_json(TOPICS_PATH, {"version": 1, "topics": {}})
    topics = topics_doc.setdefault("topics", {})

    prompt_records, prompts_line = read_jsonl_from_line(PROMPTS_PATH, int(state.get("prompts_line", 0)))
    signal_records, signals_line = read_jsonl_from_line(SIGNALS_PATH, int(state.get("signals_line", 0)))

    for record in prompt_records:
        if not record.get("is_learning_question"):
            continue
        slugs = record.get("matched_slugs") or ["general/conceptual-question"]

        for slug in slugs:
            topic = upsert_topic(topics, slug, slug_title(slug))
            increment_signal(topic, "user_questions")
            append_event(
                topic,
                {
                    "type": "user_question",
                    "at": record.get("at"),
                    "project_id": record.get("project_id"),
                    "project_label": record.get("project_label"),
                    "workspace_name": record.get("workspace_name"),
                    "file": (record.get("attached_files") or [None])[0],
                    "excerpt": record.get("prompt_excerpt"),
                },
                config,
            )

    for record in signal_records:
        slug = record.get("slug")
        if not slug:
            continue
        topic = upsert_topic(topics, str(slug), slug_title(str(slug)))
        if record.get("type") == "agent_edit":
            if record.get("intent") == "fulfilled_request":
                continue
            increment_signal(topic, "agent_edits")
            append_event(
                topic,
                {
                    "type": "agent_edit",
                    "at": record.get("at"),
                    "project_id": record.get("project_id"),
                    "project_label": record.get("project_label"),
                    "workspace_name": record.get("workspace_name"),
                    "file": record.get("file"),
                    "intent": record.get("intent"),
                    "excerpt": (record.get("snippets") or [None])[0],
                },
                config,
            )
        elif record.get("type") == "agent_mention":
            if record.get("intent") == "fulfilled_request":
                continue
            increment_signal(topic, "agent_mentions")
            append_event(
                topic,
                {
                    "type": "agent_mention",
                    "at": record.get("at"),
                    "project_id": record.get("project_id"),
                    "project_label": record.get("project_label"),
                    "workspace_name": record.get("workspace_name"),
                    "intent": record.get("intent"),
                    "is_recommendation": record.get("is_recommendation"),
                    "excerpt": record.get("text_excerpt"),
                },
                config,
            )

    topics_doc["topics"] = topics
    save_json(TOPICS_PATH, topics_doc)

    state["prompts_line"] = prompts_line
    state["signals_line"] = signals_line
    state["last_merge_at"] = utc_now_iso()
    save_state(state)


def run_command(command: str) -> None:
    ensure_journal()
    payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}

    if command == "capture-prompt":
        capture_prompt(payload)
        return
    if command == "capture-edit":
        capture_edit(payload)
        return
    if command == "capture-response":
        capture_response(payload)
        return
    if command == "merge":
        merge_pending(force=False)
        return
    if command == "merge-force":
        merge_pending(force=True)
        return

    raise SystemExit(f"Unknown command: {command}")
