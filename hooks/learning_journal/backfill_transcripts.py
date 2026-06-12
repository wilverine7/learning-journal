"""One-time backfill of learning journal from Cursor agent transcripts."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from lib import (
    JOURNAL_DIR,
    PROMPTS_PATH,
    SIGNALS_PATH,
    append_jsonl,
    detect_patterns_in_text,
    ensure_journal,
    load_pattern_catalog,
    load_state,
    looks_like_learning_question,
    merge_pending,
    project_id_for_root,
    project_label,
    prompt_requested_pattern,
    relativize_path,
    save_state,
    trim_excerpt,
    utc_now_iso,
)

PROJECTS_ROOT = Path.home() / ".cursor" / "projects"
USER_QUERY_RE = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL | re.IGNORECASE)
FILE_AT_RE = re.compile(r"@([\w./\-]+(?:\.[\w]+)?)")
RECOMMENDATION_RE = re.compile(
    r"(?i)\b(i(?:'ll| will)|we should|let's|better to|recommend|suggest|using)\b"
)
CODE_TOOLS = {"Write", "StrReplace", "EditNotebook", "ApplyPatch"}
PATH_TOOLS = {"Read", "Write", "StrReplace", "Glob", "Grep", "SemanticSearch"}


def find_git_root(start: Path) -> Path | None:
    current = start if start.is_dir() else start.parent
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def infer_workspace_root(paths: list[str]) -> str | None:
    roots: list[Path] = []
    for raw in paths:
        if not raw or raw.startswith("~"):
            continue
        path = Path(raw).expanduser()
        if not path.is_absolute():
            continue
        if path.is_file():
            git_root = find_git_root(path)
            if git_root:
                roots.append(git_root)
        elif path.is_dir() and (path / ".git").exists():
            roots.append(path)

    if not roots:
        return None

    roots.sort(key=lambda item: len(str(item)))
    return str(roots[0])


def extract_paths_from_tool(tool_name: str, tool_input: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    if tool_name in PATH_TOOLS:
        for key in ("path", "target_directory", "working_directory"):
            value = tool_input.get(key)
            if isinstance(value, str) and value:
                paths.append(value)
    if tool_name == "Glob":
        target = tool_input.get("target_directory")
        if isinstance(target, str):
            paths.append(target)
    return paths


def extract_code_from_tool(tool_name: str, tool_input: dict[str, Any]) -> list[tuple[str | None, str]]:
    results: list[tuple[str | None, str]] = []
    if tool_name == "Write":
        contents = tool_input.get("contents")
        path = tool_input.get("path")
        if isinstance(contents, str) and contents.strip():
            results.append((str(path) if path else None, contents))
    elif tool_name == "StrReplace":
        new_string = tool_input.get("new_string")
        path = tool_input.get("path")
        if isinstance(new_string, str) and new_string.strip():
            results.append((str(path) if path else None, new_string))
    elif tool_name == "EditNotebook":
        new_string = tool_input.get("new_string")
        if isinstance(new_string, str) and new_string.strip():
            results.append((None, new_string))
    return results


def extract_user_prompt(text: str) -> str:
    match = USER_QUERY_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def attached_files_from_prompt(prompt: str, workspace_root: str | None) -> list[str]:
    if not workspace_root:
        return []
    files: list[str] = []
    for match in FILE_AT_RE.finditer(prompt):
        candidate = match.group(1)
        if "/" not in candidate and not candidate.endswith((".ts", ".tsx", ".js", ".jsx", ".py", ".sql", ".gql")):
            continue
        absolute = str((Path(workspace_root) / candidate).resolve())
        files.append(relativize_path(absolute, [workspace_root]))
    return files[:5]


def transcript_paths() -> list[Path]:
    if not PROJECTS_ROOT.exists():
        return []
    return sorted(PROJECTS_ROOT.glob("**/agent-transcripts/**/*.jsonl"))


def backfill_record_key(path: Path) -> str:
    return str(path.resolve())


def should_process_transcript(path: Path, state: dict[str, Any], force: bool) -> bool:
    if force:
        return True
    backfilled = state.setdefault("backfilled_transcripts", {})
    key = backfill_record_key(path)
    entry = backfilled.get(key)
    if not isinstance(entry, dict):
        return True
    try:
        return path.stat().st_mtime > float(entry.get("mtime", 0))
    except OSError:
        return True


def mark_transcript_processed(path: Path, state: dict[str, Any], stats: dict[str, int]) -> None:
    backfilled = state.setdefault("backfilled_transcripts", {})
    key = backfill_record_key(path)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0
    backfilled[key] = {
        "mtime": mtime,
        "processed_at": utc_now_iso(),
        "prompts": stats.get("prompts", 0),
        "signals": stats.get("signals", 0),
    }


def make_context(
    *,
    at: str,
    conversation_id: str,
    generation_id: str,
    workspace_root: str,
) -> dict[str, Any]:
    project_id = project_id_for_root(workspace_root)
    return {
        "at": at,
        "conversation_id": conversation_id,
        "generation_id": generation_id,
        "project_id": project_id,
        "project_label": project_label(project_id, workspace_root),
        "workspace_root": workspace_root,
        "workspace_name": Path(workspace_root).name,
        "source": "transcript_backfill",
        "transcript_source": "agent_transcript",
    }


def process_transcript(path: Path, dry_run: bool) -> dict[str, int]:
    stats = {"prompts": 0, "signals": 0, "lines": 0}
    from datetime import datetime, timezone

    try:
        mtime_iso = (
            datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except OSError:
        mtime_iso = utc_now_iso()

    conversation_id = path.parent.name
    collected_paths: list[str] = []
    lines: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                lines.append(record)
                for block in record.get("message", {}).get("content", []) or []:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use":
                        tool_input = block.get("input") or {}
                        if isinstance(tool_input, dict):
                            collected_paths.extend(extract_paths_from_tool(str(block.get("name") or ""), tool_input))

    workspace_root = infer_workspace_root(collected_paths)
    if not workspace_root:
        return stats

    catalog = {item["slug"]: item for item in load_pattern_catalog()}
    last_user_prompt: dict[str, Any] | None = None
    turn_index = 0

    for record in lines:
        stats["lines"] += 1
        role = record.get("role")
        content = record.get("message", {}).get("content", []) or []
        turn_index += 1
        generation_id = f"{conversation_id}:{turn_index}"

        if role == "user":
            texts = [
                extract_user_prompt(str(block.get("text") or ""))
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            prompt = "\n".join(text for text in texts if text).strip()
            if not prompt:
                continue

            matched_slugs = detect_patterns_in_text(prompt, "question")
            is_question = looks_like_learning_question(prompt)
            if not is_question:
                last_user_prompt = {
                    "prompt": prompt,
                    "matched_slugs": matched_slugs,
                    "is_learning_question": False,
                }
                continue

            ctx = make_context(
                at=mtime_iso,
                conversation_id=conversation_id,
                generation_id=generation_id,
                workspace_root=workspace_root,
            )
            attached = attached_files_from_prompt(prompt, workspace_root)
            prompt_record = {
                **ctx,
                "type": "user_prompt",
                "prompt": prompt,
                "prompt_excerpt": trim_excerpt(prompt),
                "is_learning_question": True,
                "matched_slugs": matched_slugs,
                "attached_files": attached,
            }
            if not dry_run:
                append_jsonl(PROMPTS_PATH, prompt_record)
                state = load_state()
                state["prompts_by_generation"][generation_id] = {
                    "prompt": prompt,
                    "prompt_excerpt": prompt_record["prompt_excerpt"],
                    "is_learning_question": True,
                    "matched_slugs": matched_slugs,
                    "attached_files": attached,
                    "project_id": ctx["project_id"],
                    "project_label": ctx["project_label"],
                    "workspace_root": workspace_root,
                    "at": mtime_iso,
                }
                save_state(state)
            stats["prompts"] += 1
            last_user_prompt = {
                "prompt": prompt,
                "matched_slugs": matched_slugs,
                "is_learning_question": True,
            }
            continue

        if role != "assistant":
            continue

        ctx = make_context(
            at=mtime_iso,
            conversation_id=conversation_id,
            generation_id=generation_id,
            workspace_root=workspace_root,
        )

        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = str(block.get("text") or "").strip()
                if not text:
                    continue
                slugs = detect_patterns_in_text(text, "mention")
                if not slugs:
                    continue
                recommendation = bool(RECOMMENDATION_RE.search(text))
                for slug in slugs:
                    keywords = catalog.get(slug, {}).get("keywords", [])
                    intent = transcript_intent(last_user_prompt, slug, keywords)
                    if intent == "fulfilled_request":
                        continue
                    signal = {
                        **ctx,
                        "type": "agent_mention",
                        "slug": slug,
                        "text_excerpt": trim_excerpt(text),
                        "is_recommendation": recommendation,
                        "intent": intent,
                    }
                    if not dry_run:
                        append_jsonl(SIGNALS_PATH, signal)
                    stats["signals"] += 1

            if block.get("type") == "tool_use":
                tool_name = str(block.get("name") or "")
                tool_input = block.get("input") or {}
                if tool_name not in CODE_TOOLS or not isinstance(tool_input, dict):
                    continue
                for file_path, code_text in extract_code_from_tool(tool_name, tool_input):
                    slugs = detect_patterns_in_text(code_text, "code")
                    if not slugs:
                        continue
                    relative_file = None
                    if file_path:
                        relative_file = relativize_path(file_path, [workspace_root])
                    for slug in slugs:
                        keywords = catalog.get(slug, {}).get("keywords", [])
                        intent = transcript_intent(last_user_prompt, slug, keywords)
                        if intent == "fulfilled_request":
                            continue
                        signal = {
                            **ctx,
                            "type": "agent_edit",
                            "slug": slug,
                            "file": relative_file,
                            "snippets": [trim_excerpt(code_text, 160)],
                            "intent": intent,
                        }
                        if not dry_run:
                            append_jsonl(SIGNALS_PATH, signal)
                        stats["signals"] += 1

    return stats


def transcript_intent(
    last_user_prompt: dict[str, Any] | None,
    slug: str,
    keywords: list[str],
) -> str:
    if not last_user_prompt:
        return "agent_initiated"
    prompt = str(last_user_prompt.get("prompt") or "")
    if slug in (last_user_prompt.get("matched_slugs") or []):
        if last_user_prompt.get("is_learning_question"):
            return "user_question"
        return "fulfilled_request"
    if prompt_requested_pattern(prompt, slug, keywords):
        return "fulfilled_request"
    return "agent_initiated"


def run_backfill(force: bool = False, dry_run: bool = False) -> dict[str, Any]:
    ensure_journal()
    state = load_state()
    paths = transcript_paths()

    summary = {
        "transcripts_seen": len(paths),
        "transcripts_processed": 0,
        "transcripts_skipped": 0,
        "prompts_appended": 0,
        "signals_appended": 0,
        "dry_run": dry_run,
    }

    for path in paths:
        if not should_process_transcript(path, state, force):
            summary["transcripts_skipped"] += 1
            continue

        stats = process_transcript(path, dry_run=dry_run)
        summary["transcripts_processed"] += 1
        summary["prompts_appended"] += stats["prompts"]
        summary["signals_appended"] += stats["signals"]

        if not dry_run:
            mark_transcript_processed(path, state, stats)

    if not dry_run:
        save_state(state)
        merge_pending(force=True)

    topics_path = JOURNAL_DIR / "topics.json"
    topic_count = 0
    if topics_path.exists():
        try:
            topic_count = len(json.loads(topics_path.read_text(encoding="utf-8")).get("topics", {}))
        except json.JSONDecodeError:
            topic_count = 0
    summary["topics_total"] = topic_count
    return summary


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    force = "--force" in args
    dry_run = "--dry-run" in args
    summary = run_backfill(force=force, dry_run=dry_run)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
