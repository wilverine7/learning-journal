# Adapters

Tool-specific capture layers that translate native hook/transcript formats into the normalized events consumed by `core/`.

| Adapter | Status | Config |
|---------|--------|--------|
| [`cursor/`](cursor/) | Implemented | `~/.cursor/hooks.json` |
| [`claude/`](claude/) | Planned | `~/.claude/settings.json` |

Each adapter should:

1. Read tool-native input (hook stdin, transcripts, etc.)
2. Emit records via `core.ledger.record_*` with a stable `source` id
3. Avoid duplicating merge, pattern, or topic logic — that lives in `core/`
