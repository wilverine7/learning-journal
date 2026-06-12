#!/bin/bash
# Install learning-journal into ~/.cursor/
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
CURSOR_DIR="$HOME/.cursor"
JOURNAL_DIR="$CURSOR_DIR/learning-journal"
HOOKS_JSON="$CURSOR_DIR/hooks.json"
EXAMPLE_HOOKS="$REPO_ROOT/hooks.json.example"

mkdir -p "$CURSOR_DIR/hooks" "$CURSOR_DIR/skills" "$CURSOR_DIR/bin" "$JOURNAL_DIR"

link_path() {
  local source="$1"
  local target="$2"
  if [[ -L "$target" ]]; then
    rm "$target"
  elif [[ -e "$target" ]]; then
    echo "WARN: $target exists and is not a symlink — skipping (back it up and re-run to link)."
    return 0
  fi
  ln -s "$source" "$target"
  echo "Linked $target -> $source"
}

# Backward-compatible hook path (hooks.json references ./hooks/learning_journal/)
link_path "$REPO_ROOT/adapters/cursor" "$CURSOR_DIR/hooks/learning_journal"
link_path "$REPO_ROOT/skills/learning-review" "$CURSOR_DIR/skills/learning-review"
link_path "$REPO_ROOT/skills/learning-backfill" "$CURSOR_DIR/skills/learning-backfill"
link_path "$REPO_ROOT/bin/learning-journal" "$CURSOR_DIR/bin/learning-journal"

chmod +x "$CURSOR_DIR/hooks/learning_journal/run.sh"
chmod +x "$REPO_ROOT/adapters/cursor/hook.py"
chmod +x "$REPO_ROOT/bin/learning-journal"

python3 <<PY
import json
from pathlib import Path

cursor_dir = Path("$CURSOR_DIR")
example = json.loads(Path("$EXAMPLE_HOOKS").read_text())
hooks_path = cursor_dir / "hooks.json"

if hooks_path.exists():
    existing = json.loads(hooks_path.read_text())
    merged = existing.copy()
    merged.setdefault("version", 1)
    merged_hooks = merged.setdefault("hooks", {})
    for event, entries in example.get("hooks", {}).items():
        current = merged_hooks.setdefault(event, [])
        commands = {e.get("command") for e in current if isinstance(e, dict)}
        for entry in entries:
            if entry.get("command") not in commands:
                current.append(entry)
    hooks_path.write_text(json.dumps(merged, indent=2) + "\n")
    print(f"Merged learning journal hooks into {hooks_path}")
else:
    hooks_path.write_text(json.dumps(example, indent=2) + "\n")
    print(f"Created {hooks_path}")
PY

copy_if_missing() {
  local name="$1"
  local src="$REPO_ROOT/journal-templates/$name"
  local dest="$JOURNAL_DIR/$name"
  if [[ ! -e "$dest" ]]; then
    cp "$src" "$dest"
    echo "Created $dest"
  fi
}

copy_if_missing config.json
copy_if_missing patterns.json
copy_if_missing topics.json
copy_if_missing state.json

if [[ ! -f "$JOURNAL_DIR/projects.json" ]]; then
  cp "$REPO_ROOT/journal-templates/projects.json.example" "$JOURNAL_DIR/projects.json"
  echo "Created $JOURNAL_DIR/projects.json (edit repo labels)"
fi

touch "$JOURNAL_DIR/prompts.jsonl" "$JOURNAL_DIR/signals.jsonl" "$JOURNAL_DIR/review-log.jsonl"

echo ""
echo "Install complete."
echo "  Repo:         $REPO_ROOT"
echo "  Journal data: $JOURNAL_DIR"
echo "  CLI:          learning-journal (via ~/.cursor/bin)"
echo "  Skills:       /learn-review, /learn-backfill"
echo ""
echo "Next steps:"
echo "  1. Edit $JOURNAL_DIR/projects.json with your repo labels"
echo "  2. Restart Cursor (Settings -> Hooks to verify)"
echo "  3. learning-journal backfill --dry-run"
echo "  4. In chat: /learn-review week"
