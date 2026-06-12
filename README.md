# Cursor Learning Journal

Track what you ask Cursor about, detect patterns Cursor keeps suggesting, and run interactive review sessions to move topics from **discovered → learning → learned** (5 review passes).

Works **across all projects** via user-level Cursor hooks. Personal ledger data stays in `~/.cursor/learning-journal/` — never committed.

## What it does

| Signal | Captured from |
|--------|----------------|
| Your learning questions | Every chat prompt (`what`, `why`, `explain`, …) |
| Cursor-applied patterns | Agent file edits (`useMemo`, `COALESCE`, …) |
| Cursor-mentioned patterns | Agent replies |

**Skills (invoke in Cursor chat):**

- **`/learn-backfill`** — one-time import from all saved agent transcripts
- **`/learn-review week`** — teach + quiz on 1–2 topics from your ledger

## Requirements

- [Cursor](https://cursor.com) with **Hooks** enabled
- **Python 3.9+**
- macOS / Linux (Windows may work with minor path tweaks)

## Install

```bash
git clone https://github.com/YOUR_USER/cursor-learning-journal.git
cd cursor-learning-journal
./install.sh
```

The installer:

1. Symlinks hook scripts and skills into `~/.cursor/`
2. Merges hook entries into `~/.cursor/hooks.json` (preserves your existing hooks)
3. Creates `~/.cursor/learning-journal/` from templates if missing

Then **restart Cursor** and check **Settings → Hooks**.

## First-time setup

1. **Label your repos** — edit `~/.cursor/learning-journal/projects.json`:

   ```json
   {
     "github.com/your-org/your-repo": { "label": "My App" }
   }
   ```

   Keys are git remote URLs (`git remote get-url origin`). Non-git folders use `local:{hash}`.

2. **Seed from existing chats** (optional):

   ```bash
   python3 ~/.cursor/hooks/learning_journal/hook.py backfill-transcripts --dry-run
   python3 ~/.cursor/hooks/learning_journal/hook.py backfill-transcripts
   ```

3. **Start reviewing** — in Cursor chat: `/learn-review week`

## Customize patterns

Edit `~/.cursor/learning-journal/patterns.json` to add concepts you care about (React hooks, SQL, Zod, etc.). Each entry has regexes for code edits, agent mentions, and user questions.

## Configuration

`~/.cursor/learning-journal/config.json`:

| Key | Default | Meaning |
|-----|---------|---------|
| `reviews_required_for_learned` | 5 | Review passes before `learned` |
| `min_exposures_for_queue` | 3 | Min signals before surfacing in review |
| `merge_debounce_seconds` | 45 | Debounce on ledger merge |

## Repo layout

```
cursor-learning-journal/
├── install.sh              # Install into ~/.cursor/
├── hooks.json.example      # Hook config merged on install
├── hooks/learning_journal/ # Capture + merge + backfill scripts
├── skills/
│   ├── learning-review/    # /learn-review
│   └── learning-backfill/  # /learn-backfill
└── journal-templates/      # Default config (copied once on install)
```

## Updating

```bash
cd cursor-learning-journal
git pull
./install.sh   # re-link symlinks; merges any new hook entries
```

Your personal `topics.json`, prompts, and review history are **not** in this repo.

## Uninstall

```bash
rm -f ~/.cursor/hooks/learning_journal
rm -f ~/.cursor/skills/learning-review ~/.cursor/skills/learning-backfill
# Manually remove learning_journal entries from ~/.cursor/hooks.json
# Optionally delete ~/.cursor/learning-journal/
```

## License

MIT
