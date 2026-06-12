"""Normalized events, merge, and topic ledger updates."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from core.patterns import (
    detect_patterns_in_text,
    load_pattern_catalog,
    looks_like_learning_question,
    prompt_requested_pattern,
    slug_title,
    trim_excerpt,
)
from core.paths import PROMPTS_PATH, SIGNALS_PATH, TOPICS_PATH
from core.storage import (
    append_jsonl,
    ensure_journal,
    load_config,
    load_json,
    load_state,
    read_jsonl_from_line,
    save_json,
    save_state,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def intent_for_turn(
    *,
    source: str,
    turn_id: str | None,
    slug: str,
    keywords: list[str],
) -> str:
    if not turn_id:
        return "agent_initiated"
    state = load_state()
    key = f"{source}:{turn_id}"
    prompt_entry = state["prompts_by_generation"].get(key)
    if not prompt_entry:
        prompt_entry = state["prompts_by_generation"].get(str(turn_id))
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


def remember_turn_prompt(
    *,
    source: str,
    turn_id: str,
    prompt: str,
    prompt_excerpt: str,
    is_learning_question: bool,
    matched_slugs: list[str],
    attached_files: list[str],
    project_id: str,
    project_label: str,
    workspace_root: str,
    at: str,
) -> None:
    state = load_state()
    prompts_by_generation = state["prompts_by_generation"]
    prompts_by_generation[f"{source}:{turn_id}"] = {
        "prompt": prompt,
        "prompt_excerpt": prompt_excerpt,
        "is_learning_question": is_learning_question,
        "matched_slugs": matched_slugs,
        "attached_files": attached_files,
        "project_id": project_id,
        "project_label": project_label,
        "workspace_root": workspace_root,
        "at": at,
    }
    if len(prompts_by_generation) > 500:
        keys = sorted(prompts_by_generation.keys(), key=lambda key: prompts_by_generation[key].get("at", ""))
        for key in keys[:-300]:
            prompts_by_generation.pop(key, None)
    save_state(state)


def record_user_prompt(
    *,
    source: str,
    at: str,
    conversation_id: str | None,
    turn_id: str | None,
    project_id: str,
    project_label: str,
    workspace_root: str,
    workspace_name: str,
    prompt: str,
    attached_files: list[str] | None = None,
    capture_type: str = "user_prompt",
) -> dict[str, Any]:
    ensure_journal()
    attached_files = attached_files or []
    prompt_excerpt = trim_excerpt(prompt)
    is_learning_question = looks_like_learning_question(prompt)
    matched_slugs = detect_patterns_in_text(prompt, "question")

    record = {
        "source": source,
        "at": at,
        "conversation_id": conversation_id,
        "generation_id": turn_id,
        "project_id": project_id,
        "project_label": project_label,
        "workspace_root": workspace_root,
        "workspace_name": workspace_name,
        "type": capture_type,
        "prompt": prompt,
        "prompt_excerpt": prompt_excerpt,
        "is_learning_question": is_learning_question,
        "matched_slugs": matched_slugs,
        "attached_files": attached_files,
    }
    append_jsonl(PROMPTS_PATH, record)

    if turn_id:
        remember_turn_prompt(
            source=source,
            turn_id=turn_id,
            prompt=prompt,
            prompt_excerpt=prompt_excerpt,
            is_learning_question=is_learning_question,
            matched_slugs=matched_slugs,
            attached_files=attached_files,
            project_id=project_id,
            project_label=project_label,
            workspace_root=workspace_root,
            at=at,
        )
    return record


def record_agent_edit(
    *,
    source: str,
    at: str,
    conversation_id: str | None,
    turn_id: str | None,
    project_id: str,
    project_label: str,
    workspace_root: str,
    workspace_name: str,
    slug: str,
    file: str | None,
    snippets: list[str],
    intent: str | None = None,
) -> None:
    ensure_journal()
    catalog = {item["slug"]: item for item in load_pattern_catalog()}
    keywords = catalog.get(slug, {}).get("keywords", [])
    resolved_intent = intent or intent_for_turn(source=source, turn_id=turn_id, slug=slug, keywords=keywords)
    append_jsonl(
        SIGNALS_PATH,
        {
            "source": source,
            "at": at,
            "conversation_id": conversation_id,
            "generation_id": turn_id,
            "project_id": project_id,
            "project_label": project_label,
            "workspace_root": workspace_root,
            "workspace_name": workspace_name,
            "type": "agent_edit",
            "slug": slug,
            "file": file,
            "snippets": snippets[:3],
            "intent": resolved_intent,
        },
    )


def record_agent_mention(
    *,
    source: str,
    at: str,
    conversation_id: str | None,
    turn_id: str | None,
    project_id: str,
    project_label: str,
    workspace_root: str,
    workspace_name: str,
    slug: str,
    text_excerpt: str,
    is_recommendation: bool,
    intent: str | None = None,
) -> None:
    ensure_journal()
    catalog = {item["slug"]: item for item in load_pattern_catalog()}
    keywords = catalog.get(slug, {}).get("keywords", [])
    resolved_intent = intent or intent_for_turn(source=source, turn_id=turn_id, slug=slug, keywords=keywords)
    append_jsonl(
        SIGNALS_PATH,
        {
            "source": source,
            "at": at,
            "conversation_id": conversation_id,
            "generation_id": turn_id,
            "project_id": project_id,
            "project_label": project_label,
            "workspace_root": workspace_root,
            "workspace_name": workspace_name,
            "type": "agent_mention",
            "slug": slug,
            "text_excerpt": text_excerpt,
            "is_recommendation": is_recommendation,
            "intent": resolved_intent,
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
                    "source": record.get("source"),
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
                    "source": record.get("source"),
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
                    "source": record.get("source"),
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
