#!/usr/bin/env python3
"""Cursor hook and CLI entrypoint."""

from __future__ import annotations

import json
import sys

from adapters.cursor.capture import capture_edit, capture_prompt, capture_response
from core.ledger import merge_pending
from core.storage import ensure_journal


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: hook.py <capture-prompt|capture-edit|capture-response|merge|merge-force|backfill-transcripts>"
        )

    command = sys.argv[1]
    if command == "backfill-transcripts":
        from adapters.cursor.backfill import main as backfill_main

        backfill_main(sys.argv[2:])
        return

    ensure_journal()

    if command in {"capture-prompt", "capture-edit", "capture-response"}:
        payload = json.load(sys.stdin)
    else:
        payload = {}

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


if __name__ == "__main__":
    main()
