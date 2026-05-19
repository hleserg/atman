---
name: linear-project-orchestration
description: >-
  Orchestrates Linear project work via MCP: pick ready issues (respect blockers),
  parallelize when safe, enforce In Progress/Done on issues and project state,
  attach per-issue completion reports as Linear Documents, and publish a project
  closure doc linking all issue reports. Use when the user names a Linear project,
  asks to "work the project", "take tasks from Linear", run parallel agents on
  issues, or wants issue/project status updates and delivery reports in Linear.
---

# Linear project orchestration (Atman)

Use this skill when the user gives a **Linear project** (name, slug, or ID) and expects the agent to **drive execution**: queue selection, status hygiene, optional parallelism, and **reports in Linear Documents** — not only local `reports/` files.

**Prerequisites:** Linear MCP (`plugin-linear-linear`) authenticated in Cursor. If tools fail, stop and ask the user to connect Linear in **Settings → MCP**.

**Atman iron rule** (also in `CLAUDE.md`): status changes are **immediate**, not deferred to commit/PR time.

---

## Triggers (examples)

- «Работай по проекту *Backend refactor*»
- «Возьми первую задачу из Linear проекта X»
- «Закрой проект — собери общий отчёт»
- «Параллельно возьми всё, что без блокеров»

---

## Phase 0 — Resolve workspace vocabulary

Before changing states, call **`list_issue_statuses`** for the relevant **team** and note exact names for:

| Intent | Typical name (confirm in workspace) |
|--------|-------------------------------------|
| Started work | `In Progress` |
| Finished issue | `Done` |
| Project active | project `state` from `get_project` / team convention (e.g. `In Progress`, `Started`) |
| Project finished | e.g. `Completed`, `Done` |

Use **`save_issue`** field `state` and **`save_project`** field `state` with those exact strings.

---

## Phase 1 — Discover project and backlog

1. **`get_project`** — id, name, description, current `state`, lead.
2. **`list_issues`** with `project` = project name/slug/id, `includeArchived: false`, reasonable `limit` (paginate with `cursor` if needed).
3. For each non-Done issue, **`get_issue`** when you need `blockedBy` / `blocks` / `relatedTo` / full description.

Build an internal table:

| identifier | title | state | priority | blockedBy (open) | assignee |
|------------|-------|-------|----------|------------------|----------|

**Ready issue** = state is not terminal (not `Done` / `Canceled` / team equivalent) AND every id in `blockedBy` is already **Done** (or missing).

**Sort ready queue:** priority (urgent first), then `updatedAt` or project board order if visible.

---

## Phase 2 — Start project (when beginning work)

When the user starts orchestration on a project that is still idle:

1. **`save_project`** — set `state` to the team’s **active** project state (from Phase 0).
2. Optionally append to `description` or `summary` a one-line «Agent run started &lt;ISO date&gt;» — do not wipe existing markdown.

If the project is already active, skip.

---

## Phase 3 — Take one issue (single-track default)

For the **first ready issue** (unless user asked for parallel — Phase 4):

1. **`save_issue`**: `id`, `state` = **In Progress**, `assignee` = `"me"` if appropriate.
2. Confirm in chat: identifier + title + link if returned.
3. Do the implementation work in the repo (follow `AGENTS.md`, `make check` when code changes).
4. On completion:
   - **`save_issue`**: `state` = **Done**
   - Run **Phase 5** (issue report) before moving to the next issue.

Never start coding before step 1. Never pick the next issue before step 4 + Phase 5 for the current one (unless Phase 4 parallel mode).

---

## Phase 4 — Parallel mode (optional)

Run only when the user explicitly allows parallelism **or** says «всё без блокеров параллельно».

**Rules:**

- Only issues in the **ready** set (Phase 1).
- Default **max 2** concurrent issues; **max 3** only if the user asks. Do not parallelize issues that share the same files or the same Linear parent/subtask chain unless the user accepts collision risk.
- Each issue gets its own **Task** subagent (or isolated turn) with a prompt that includes: issue id, title, description, «set In Progress immediately», «set Done + issue report when finished».
- Parent agent: track statuses; do not mark the **project** complete until **all** issues are Done.
- If two issues block each other, run them **sequentially**.

After all parallel issues finish, continue to Phase 6 if no open issues remain.

---

## Phase 5 — Per-issue completion report (Linear Document)

After marking an issue **Done**, create a **Linear Document** attached to that issue:

1. **`save_document`** with:
   - `title`: `Completion report — <IDENTIFIER> — <short title>`
   - `issue`: `<IDENTIFIER>` (e.g. `ATMAN-42`)
   - `content`: markdown from template below (fill all sections; literal newlines, no `\n` escapes).

2. **`save_comment`** on the same issue with a short note: «Completion report: » + document title/slug/link if the API returns it.

3. **`save_issue`** `links`: append `{ "url": "<doc or issue url>", "title": "Completion report" }` if a stable URL is available.

**Optional local mirror:** copy the same markdown to `reports/sessions/<IDENTIFIER>-<YYYY-MM-DD>.md` only if the user wants git-tracked artifacts; Linear Document is **canonical** for this workflow.

### Issue report template

```markdown
# Completion report — <IDENTIFIER>

- **Issue:** <title>
- **Project:** <project name>
- **Completed:** <ISO-8601 datetime>
- **Agent:** Cursor (Atman repo)

## Summary

<2–4 sentences: what was delivered>

## Changes

- <bullet: repo paths, behavior, or "no code — docs/process only">

## Verification

- <commands run, e.g. make check, pytest subset, or N/A>

## Follow-ups

- <open items or "none">

## Links

- PR: <url or "none">
- Branch: <name or "none">
```

---

## Phase 6 — Project closure

When **every** issue in the project is terminal (Done/Canceled) or only Done remain per user instruction:

1. Collect links/titles of all **completion report** documents (from comments, `list_documents` with `projectId`, or issue links).
2. **`save_document`** on the **project**:
   - `title`: `Project closure — <project name> — <YYYY-MM-DD>`
   - `project`: `<project name or id>`
   - `content`: use template below.

3. **`save_project`**: `state` = completed state from Phase 0; optionally refresh `summary` with one-line outcome.

4. Tell the user: project state, closure doc title, and list of issue reports.

### Project closure template

```markdown
# Project closure — <project name>

- **Project:** <name> (<id/slug>)
- **Closed:** <ISO-8601 datetime>
- **Issues completed:** <N> / <total>

## Outcome

<Short narrative: goal met? scope cuts?>

## Issue completion reports

| Issue | Report |
|-------|--------|
| <IDENTIFIER> | <link or document title> |
| … | … |

## Cross-cutting notes

- <architecture, risks, deferred work>

## Recommended next steps

- <bullets>
```

---

## Phase 7 — Handoff and failures

| Situation | Action |
|-----------|--------|
| No ready issues, some blocked | Report blockers; offer to work blocker chain or ask user to unblock |
| No issues in project | Say so; do not invent tasks |
| MCP auth error | Stop; user fixes Settings → MCP |
| Implementation blocked | Comment on issue via **`save_comment`**; leave state **In Progress** or move to team’s «Blocked» if it exists — **do not** set Done |

---

## MCP tool map (quick reference)

| Step | Tools |
|------|--------|
| Discover | `get_project`, `list_issues`, `get_issue`, `list_issue_statuses` |
| Status | `save_issue`, `save_project` |
| Reports | `save_document`, `save_comment`, `save_issue` (`links`) |
| Docs search | `list_documents`, `get_document` |

---

## What this skill does *not* do

- Replace Notion epic tracking (`CLAUDE.md` Notion section) — Linear orchestration is separate unless the user merges them.
- Auto-run without explicit user intent — do not change production Linear data on vague «look at Linear» requests; confirm project scope first if ambiguous.

---

## Examples

**User:** «Работай по проекту E21 Affect Detector»

1. Phase 0–2: resolve statuses, load issues, set project active.
2. Phase 3: first ready issue → In Progress → implement → Done → Phase 5 report.
3. Repeat until backlog clear → Phase 6.

**User:** «Параллельно до трёх задач без блокеров в проекте X»

Phase 4 with `max 3`, then Phase 6 when all Done.
