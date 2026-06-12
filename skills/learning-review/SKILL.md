---
name: learning-review
description: Runs an interactive learning review from the personal cross-project learning journal. Reads ~/.cursor/learning-journal/topics.json, prioritizes topics from user questions and repeated Cursor-suggested patterns, teaches 1-2 topics with repo/file context, quizzes the user, and updates mastery status. Use when the user says /learn-review, learning review, review what I asked, study my cursor questions, or wants to learn topics Cursor keeps suggesting.
disable-model-invocation: true
---

# Learning Review

Personal learning journal across all Cursor projects. Data lives in `~/.cursor/learning-journal/`.

## Before starting

1. Run merge so the ledger is current:

```bash
python3 ~/.cursor/hooks/learning_journal/hook.py merge-force
```

2. Read these files:
   - `~/.cursor/learning-journal/config.json`
   - `~/.cursor/learning-journal/topics.json`
   - `~/.cursor/learning-journal/patterns.json` (titles and categories)
   - `~/.cursor/learning-journal/projects.json` (friendly repo labels)

3. Parse the user's time window from their message:
   - `day` → last 1 day
   - `week` → last 7 days (default from config if unspecified)
   - `month` → last 30 days
   - `all` → no time filter

## Topic selection (pick 1–2)

Skip topics where `dismissed` is true.

Score each topic (higher = review sooner):

| Signal | Weight |
|--------|--------|
| `signals.user_questions` in window | +3 each |
| `signals.agent_edits` in window (agent-initiated) | +2 each |
| `signals.agent_mentions` in window | +1 each |
| Status `discovered` | +2 |
| Status `learning` with `review_pass_count` below required | +4 |
| High agent edits, zero user questions ("silent repeat") | +5 bonus |
| Already `learned` or `expert` | exclude unless user asks for refresher |

Only surface topics for a **new review session** when total exposures in window ≥ `min_exposures_for_queue` (default 3), **unless** the user explicitly asked about that topic (`user_questions` ≥ 1).

Prefer topics the user has not reviewed recently (no `review-log.jsonl` entry in the last 48h for that slug).

## Teaching format

For each selected topic:

1. **Context** — cite project labels and files from `events` (e.g. "In **SCX** `app/.../DealTable.tsx` you asked…" / "Cursor applied this 4 times in **Budget app**").
2. **Mini-lesson** — 3–5 short paragraphs tied to their actual usage, not generic docs.
3. **Quiz** — 2–3 questions mixing recall and apply-in-context. Wait for answers before scoring.

Do not start teaching during normal coding chats. Only in this explicit review flow.

## Quiz code context rules

When a question references code from the user's repo (from `events[].file`, attached files, or ledger excerpts):

1. **Read the file first** — use the `file` path and `project_id` / workspace from the event to open the real source (e.g. `api/entities/events/event.helpers.ts` in **SCX**). Prefer the user's open workspace or the path recorded in the event.
2. **Show the whole block** — include the **full** relevant snippet in the lesson and again in each quiz question that depends on it: the full SELECT/JOIN (or function/hook), not a one-line fragment or `COALESCE(LOWER(TRIM(...)))` placeholder.
3. **Label the source** — every code block must cite **project label**, **file path**, and **line range** when available (e.g. `SCX · event.helpers.ts:3660–3680`).
4. **One scenario per question** — do not ask about two different code paths in one question without showing both blocks. Separate Q2 (event property fallback) from Q3 (property filter WHERE clause) with distinct, complete snippets.
5. **If the file is missing or path is stale** — say so, paste the longest excerpt from `events[].excerpt`, and ask a generic recall question instead of a file-specific one.

Bad (too little context):

> Same expression when both are NULL — why might `property_name` be NULL?

Good:

> Given this query from **SCX** `api/entities/events/event.helpers.ts:3660–3680`:
>
> ```sql
> -- full SELECT … JOIN … COALESCE(e.property_id, ai_single.property_id) … p.name
> ```
>
> When both `e.property_id` and `ai_single.property_id` are NULL, what does COALESCE return and why is `p.name` NULL?

Apply these rules to the **mini-lesson** as well: teach from the same complete blocks you will quiz on.

## Scoring and status updates

After the user answers the quiz:

- **Pass** — mostly correct; minor gaps OK with brief correction.
- **Fail** — significant gaps; re-teach briefly, do not increment pass count.

On pass, append to `~/.cursor/learning-journal/review-log.jsonl`:

```json
{
  "at": "ISO-8601",
  "slug": "react/use-memo",
  "passed": true,
  "review_pass_count_after": 2,
  "window": "week"
}
```

Update `topics.json` for that slug:

| Field | Rule |
|-------|------|
| `review_pass_count` | +1 on pass |
| `status` | `discovered` → `learning` on first pass |
| `status` | `learning` → `learned` when `review_pass_count` ≥ `reviews_required_for_learned` (default **5**) |
| `status` | `learned` → `expert` only if user requests expert check or nails a hard explain-back without hints |

On fail: keep status, optionally add a note in the review log with `"passed": false`.

Write updated `topics.json` atomically (write temp file, then replace).

## User commands during review

| User says | Action |
|-----------|--------|
| dismiss / I know this | set `dismissed: true` on topic |
| show ledger / what am I learning | print summary table by status |
| focus on {topic} | teach that slug next |
| expert check on {topic} | harder explain-back; promote to `expert` on success |

## Ledger summary table

When showing status, use:

```
| Status | Topic | Questions | Cursor edits | Passes | Last seen |
```

Group by: `discovered` (to learn), `learning`, `learned`, `expert`.

## Silent-repeat callout

If a topic has `agent_edits + agent_mentions ≥ 3` and `user_questions == 0`, say explicitly:

> Cursor has been using **{title}** repeatedly and you haven't asked about it yet. Good candidate to study even without a direct question.

## Assumptions

- Hooks capture prompts (`beforeSubmitPrompt`), agent edits (`afterFileEdit`), and agent mentions (`afterAgentResponse`); merge runs on `stop` / `sessionEnd` and via merge-force above.
- For a **first-time seed from old chats**, the user should run `/learn-backfill` once before their first review.
- Pattern catalog is editable in `~/.cursor/learning-journal/patterns.json`.
- Repo labels are editable in `~/.cursor/learning-journal/projects.json` (key = git remote, e.g. `github.com/Sponsor-CX/scx` → `"SCX"`).
- Non-git folders use `local:{hash}` keys; label defaults to folder name.

## Examples

**User:** `/learn-review week`

1. merge-force
2. Pick top 2 scored topics from last 7 days
3. Teach + quiz each
4. Update ledger

**User:** `show my learning ledger`

Print summary from `topics.json` without starting a quiz unless asked.
