"""Translate Cursor hook payloads into normalized journal events."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from core.ledger import record_agent_edit, record_agent_mention, record_user_prompt, utc_now_iso
from core.patterns import detect_patterns_in_text, load_pattern_catalog, trim_excerpt
from core.projects import build_project_context, relativize_path

SOURCE = "cursor"


def primary_workspace(payload: dict[str, Any]) -> str:
    roots = payload.get("workspace_roots") or []
    if roots:
        return str(roots[0])
    return os.getcwd()


def base_context(payload: dict[str, Any]) -> dict[str, Any]:
    workspace_root = primary_workspace(payload)
    project = build_project_context(workspace_root)
    return {
        "source": SOURCE,
        "at": utc_now_iso(),
        "conversation_id": payload.get("conversation_id"),
        "turn_id": payload.get("generation_id"),
        **project,
    }


def capture_prompt(payload: dict[str, Any]) -> None:
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        print(json.dumps({"continue": True}))
        return

    ctx = base_context(payload)
    workspace_root = ctx["workspace_root"]
    attachments = payload.get("attachments") or []
    attached_files = [
        relativize_path(str(item.get("file_path")), workspace_root)
        for item in attachments
        if isinstance(item, dict) and item.get("type") == "file" and item.get("file_path")
    ]

    record_user_prompt(
        source=ctx["source"],
        at=ctx["at"],
        conversation_id=ctx["conversation_id"],
        turn_id=str(ctx["turn_id"]) if ctx["turn_id"] else None,
        project_id=ctx["project_id"],
        project_label=ctx["project_label"],
        workspace_root=workspace_root,
        workspace_name=ctx["workspace_name"],
        prompt=prompt,
        attached_files=attached_files,
    )
    print(json.dumps({"continue": True}))


def capture_edit(payload: dict[str, Any]) -> None:
    ctx = base_context(payload)
    workspace_root = ctx["workspace_root"]
    file_path = str(payload.get("file_path") or "")
    relative_file = relativize_path(file_path, workspace_root) if file_path else None
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

    turn_id = str(ctx["turn_id"]) if ctx["turn_id"] else None
    for slug, snippets in matched.items():
        record_agent_edit(
            source=ctx["source"],
            at=ctx["at"],
            conversation_id=ctx["conversation_id"],
            turn_id=turn_id,
            project_id=ctx["project_id"],
            project_label=ctx["project_label"],
            workspace_root=workspace_root,
            workspace_name=ctx["workspace_name"],
            slug=slug,
            file=relative_file,
            snippets=snippets,
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
    turn_id = str(ctx["turn_id"]) if ctx["turn_id"] else None

    for slug in slugs:
        record_agent_mention(
            source=ctx["source"],
            at=ctx["at"],
            conversation_id=ctx["conversation_id"],
            turn_id=turn_id,
            project_id=ctx["project_id"],
            project_label=ctx["project_label"],
            workspace_root=ctx["workspace_root"],
            workspace_name=ctx["workspace_name"],
            slug=slug,
            text_excerpt=trim_excerpt(text),
            is_recommendation=recommendation,
        )
