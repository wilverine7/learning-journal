# Claude Code adapter (planned)

Not implemented yet. Intended mapping:

| Learning signal | Claude Code hook |
|-----------------|------------------|
| User learning questions | `UserPromptSubmit` |
| Agent code patterns | `PostToolUse` (`Edit\|Write`) |
| Agent mentions | `Stop` or transcript parse |
| Turn merge | `Stop` |

Will write to the same `core/` ledger using `source: "claude"`.

Install target: `~/.claude/settings.json` (separate from Cursor).
