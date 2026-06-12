# Learning Journal

Track what you ask your AI coding tools about, detect patterns they keep suggesting, and run interactive review sessions to move topics from **discovered → learning → learned** (5 review passes).

**Cursor adapter included today.** Core ledger and CLI are tool-agnostic; Claude Code adapter is stubbed for future work.

Personal ledger data stays in `~/.cursor/learning-journal/` (override with `LEARNING_JOURNAL_HOME`) — never committed.

## What it does

| Signal | Captured from (Cursor) |
|--------|------------------------|
| Your learning questions | Every chat prompt (`what`, `why`, `explain`, …) |
| Agent-applied patterns | Agent file edits (`useMemo`, `COALESCE`, …) |
| Agent-mentioned patterns | Agent replies |

**Skills (invoke in Cursor chat):**

- **`/learn-backfill`** — one-time import from all saved agent transcripts
- **`/learn-review week`** — teach + quiz on 1–2 topics from your ledger

## Requirements

- [Cursor](https://cursor.com) with **Hooks** enabled (today)
- **Python 3.9+**
- macOS / Linux

## Install

```bash
git clone https://github.com/YOUR_USER/learning-journal.git
cd learning-journal
./install.sh
```

Then **restart Cursor** and check **Settings → Hooks**.

## CLI (tool-agnostic)

After install, `~/.cursor/bin/learning-journal` is on your PATH if you use Cursor’s bin, or run directly:

```bash
learning-journal merge-force
learning-journal backfill --dry-run
learning-journal backfill --adapter cursor
```

Cursor hooks still work via the backward-compatible path:

```bash
~/.cursor/hooks/learning_journal/run.sh merge-force
```

## Architecture

```
adapters/cursor/     → Cursor hook stdin / transcripts  →  core/  →  ~/.cursor/learning-journal/
adapters/claude/     → (planned) Claude Code hooks
bin/learning-journal → tool-agnostic merge / backfill CLI
core/                → patterns, projects, ledger merge (shared)
skills/              → Cursor Agent Skills for /learn-review and /learn-backfill
```

Normalized events include `source` (`cursor`, `claude`, …) so one ledger can aggregate multiple tools later.

See [`adapters/README.md`](adapters/README.md) for adapter conventions.

## First-time setup

1. Edit `~/.cursor/learning-journal/projects.json` with repo labels (git remote → friendly name).
2. `learning-journal backfill --dry-run` then `learning-journal backfill`
3. In Cursor chat: `/learn-review week`

## Repo layout

```
learning-journal/
├── core/                   # Tool-agnostic ledger + patterns
├── adapters/
│   ├── cursor/             # Cursor hooks + transcript backfill
│   └── claude/             # Placeholder
├── bin/learning-journal    # Shared CLI
├── skills/                 # Cursor review/backfill skills
├── journal-templates/      # Default config (copied on install)
├── hooks.json.example      # Cursor hook config
└── install.sh
```

## Updating

```bash
git pull && ./install.sh
```

## License

MIT
