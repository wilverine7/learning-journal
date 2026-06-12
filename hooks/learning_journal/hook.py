#!/usr/bin/env python3
"""Cursor hook entrypoint for the cross-project learning journal."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import run_command  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: hook.py <capture-prompt|capture-edit|capture-response|merge|merge-force|backfill-transcripts>"
        )
    command = sys.argv[1]
    if command == "backfill-transcripts":
        from backfill_transcripts import run_backfill

        args = sys.argv[2:]
        summary = run_backfill(force="--force" in args, dry_run="--dry-run" in args)
        print(json.dumps(summary, indent=2))
        return
    run_command(command)


if __name__ == "__main__":
    main()
