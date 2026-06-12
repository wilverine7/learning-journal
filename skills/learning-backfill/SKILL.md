---
name: learning-backfill
description: One-time import of learning topics from all existing Cursor agent chat transcripts into the personal learning journal. Scans ~/.cursor/projects/**/agent-transcripts, extracts user learning questions and Cursor-suggested patterns, merges into ~/.cursor/learning-journal/topics.json, and skips already-imported transcripts on reruns. Use when the user says /learn-backfill, import my chat history, bootstrap learning journal, seed learning topics from old chats, or backfill learning ledger from transcripts.
disable-model-invocation: true
---

# Learning Backfill (one-time import)

Import historical learning signals from **all** Cursor agent transcripts into the cross-project journal at `~/.cursor/learning-journal/`.

Run this **once** to seed the ledger, then rely on hooks for new chats. Safe to rerun — already-processed transcripts are skipped unless forced.

## Workflow

### 1. Optional dry run

Show how much would be imported without writing:

```bash
python3 ~/.cursor/hooks/learning_journal/hook.py backfill-transcripts --dry-run
```

Print the JSON summary to the user:

- `transcripts_seen`
- `transcripts_processed`
- `transcripts_skipped`
- `prompts_appended`
- `signals_appended`

### 2. Run the import

```bash
python3 ~/.cursor/hooks/learning_journal/hook.py backfill-transcripts
```

This will:

1. Scan `~/.cursor/projects/**/agent-transcripts/**/*.jsonl`
2. Infer repo root from file paths in each chat (`.git` walk-up)
3. Extract:
   - **User learning questions** (`what`, `why`, `how`, `explain`, or prompts with `?`)
   - **Agent pattern mentions** in assistant prose
   - **Agent code patterns** from `Write`, `StrReplace`, and `EditNotebook` tool calls
4. Append to `prompts.jsonl` / `signals.jsonl`
5. Merge into `topics.json`
6. Record processed transcript paths + mtimes in `state.json` → `backfilled_transcripts`

### 3. Summarize results

After import, read `~/.cursor/learning-journal/topics.json` and show:

```
| Topic | Questions | Cursor edits | Mentions | Projects |
```

Sort by total signal count descending. Call out **silent-repeat** topics (high agent edits/mentions, zero user questions).

Tell the user:

> Backfill complete. Future chats are captured automatically by hooks. Run `/learn-review week` when you want to study.

## Re-import / force

Only if the user explicitly asks to re-scan everything:

```bash
python3 ~/.cursor/hooks/learning_journal/hook.py backfill-transcripts --force
```

`--force` ignores the processed-transcript cache and may duplicate events already merged into topics. Prefer normal rerun (no flags) which only processes new or changed transcript files.

## What gets imported

| Source in transcript | Journal signal |
|---------------------|----------------|
| User `<user_query>` learning questions | `user_questions` |
| `@app/...` file refs in question | `file` on event |
| Assistant explanation mentioning patterns | `agent_mentions` |
| `Write` / `StrReplace` code with tracked patterns | `agent_edits` |

Intent tagging matches live hooks:

- User asked to implement a pattern → `fulfilled_request` (not counted as passive Cursor suggestion)
- User asked how/why → `user_question`
- Cursor introduced unprompted → `agent_initiated`

## Limits

- **Timestamps** use the transcript file mtime (not per-message time) — good enough for ranking, not exact chronology.
- **Transcripts only** — chats without saved transcripts are skipped.
- **Pattern catalog** — only topics in `~/.cursor/learning-journal/patterns.json` are detected; expand that file to track more concepts.
- **Meta chats** about building this journal will import too; user can `dismiss` those topics during `/learn-review`.

## Related

- Ongoing capture: `~/.cursor/hooks.json`
- Study sessions: use the `learning-review` skill (`/learn-review week`)
- Repo labels: `~/.cursor/learning-journal/projects.json`

## Example

**User:** `/learn-backfill`

1. Run dry-run, show counts
2. Ask: "Proceed with import?" — if user already said backfill/import/bootstrap explicitly, skip confirmation and run import
3. Run import command
4. Print top 15 topics table + next step (`/learn-review week`)
