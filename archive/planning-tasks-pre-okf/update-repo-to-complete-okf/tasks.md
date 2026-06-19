---
type: Specification
title: Complete OKF — Phase 1
description: Close the deliberately-deferred OKF gaps in the orchestration repo without disturbing the SDLC workflows — split DECISIONS, OKF-frontmatter docs/, update log-work.
---

# Task Spec — OKF Completion, Phase 1

## Goal
Close the deliberately-deferred OKF gaps in the orchestration repo without disturbing the SDLC workflows — split DECISIONS, OKF-frontmatter `docs/`, update `log-work`.

## Context Pointers
- **Plan:** `planning/plans/update-repo-to-complete-okf.md` — the authoritative work items, load-bearing-file list, and out-of-scope/Phase-2 boundary. Read it first; this spec decomposes it.
- **Load-bearing files (DO NOT touch this phase):** `planning/STATUS.md`, `planning/MASTER_PLAN.md`, root `DEVLOG.md` (read + prepend only), `planning/tasks/<stem>/{tasks.md,execution-plan.json,reports/}`, all `.claude/workflows/*.js`. The workflows never read/write `DECISIONS.md` — splitting it is safe at the workflow layer.
- **Source to split:** `planning/DECISIONS.md` — currently D1–D26, each in `**Decided / Why / Rejected**` form, plus a header block and a footer index line.
- **Prose pointers to repoint:** `CLAUDE.md` ("Before you start" + D-references), `planning/CONTEXT.md` (Document Set table + "five/seven files" prose), `planning/README.md` (files table + footer).
- **Docs to frontmatter:** everything under `docs/` (see Task 4).
- **Command to update:** `.claude/commands/log-work.md` (step 5 currently points at the aggregate `DECISIONS.md`).
- **CLAUDE.md standing rules in play:** module docstrings line 1, OKF frontmatter shape (`type`/`title`/`description`), ask-first guard on settled-choice logging. No new workflow is added, so the tests-ship-with-every-workflow rule does not trigger — validation here is "nothing broke."

## Step-by-Step Tasks

### 1. Split `DECISIONS.md` → atomic `planning/decisions/` files
- Create `planning/decisions/`.
- For each decision D1–D26, create `planning/decisions/D{N}-<kebab-title>.md` with frontmatter:
  ```yaml
  ---
  type: Decision
  title: D{N} — Short Title
  description: One-sentence summary.
  ---
  ```
- Preserve each entry's **Decided / Why / Rejected** body verbatim, including any `*Note:* … superseded by …` lines (D14–D19, D17 especially) — do not drop the supersession notes.
- Keep the existing D-numbering exactly; titles taken from the existing `### DN — …` headers.

### 2. Create the decisions registry index
- Create `planning/decisions/index.md` with `type: Index` frontmatter.
- List D1–D26 newest-at-the-bottom, preserving the append-only convention and the closing "to add / to reverse a decision" guidance carried over from the old footer.
- Carry over the grouping note (D1–D13 foundational; D14–D25 Company Brain, retained-but-superseded; D26 goal revision).

### 3. Delete the aggregate and repoint prose
- Delete `planning/DECISIONS.md`.
- Repoint every prose reference (NOT workflow JS) to `planning/decisions/`:
  - `CLAUDE.md` — "Before you start" line referencing `planning/DECISIONS.md`, and inline D6/D16/D17/D18/D20 mentions.
  - `planning/CONTEXT.md` — Document Set table row + surrounding "five/seven files" prose + the "five jobs" sentence.
  - `planning/README.md` — files table row + footer line.
- Grep the repo for residual `DECISIONS.md` mentions and confirm the only remaining ones are the **workflow `notes`-field prompt strings** (accepted Phase-2 seam) — leave those untouched.

### 4. OKF-frontmatter the `docs/` folder + add `docs/index.md`
- Prepend OKF frontmatter (content otherwise unchanged) to:
  - `docs/api-reference.md` → `type: Reference`
  - `docs/configuration.md` → `type: Reference`
  - `docs/app-architecture-overview.md` → `type: Architecture`
  - `docs/agentic-workflows/*.md` (3 files) → `type: Reference`
  - `docs/architecture_review/*.md` (8 files) → `type: Reference`
- Create `docs/index.md` (`type: Index`) listing each doc with a one-line description.
- Confirm the CLAUDE.md "Documentation" table links to `docs/api-reference.md` / `docs/configuration.md` still resolve (no renames).

### 5. Update `log-work` to write atomic decisions
- In `.claude/commands/log-work.md`, replace the step that prompts to add a settled choice to `planning/DECISIONS.md` with the brain `log-decision` pattern: on a settled choice, **ask first**, then create `planning/decisions/D{N+1}-<kebab>.md` with OKF frontmatter and register it in `planning/decisions/index.md`.
- Keep the ask-first guard intact (do not have the command edit decisions without confirmation).

### 6. Record the DEVLOG entry
- Prepend a dated entry to root `DEVLOG.md` (below frontmatter) describing the migration, and **explicitly record the accepted seam**: workflow `notes`-field prompt strings still say "DECISIONS.md" by design — Phase 2 corrects them — so it isn't later read as an oversight.

### 7. Validate
- Run the Validation Commands listed below and confirm all pass.

## Acceptance Criteria
- `planning/decisions/` exists with one atomic file per prior decision (D1–D26), each carrying OKF `type: Decision` frontmatter and the verbatim Decided/Why/Rejected body (supersession notes preserved).
- `planning/decisions/index.md` exists (`type: Index`), newest-at-the-bottom, append-only convention preserved.
- Old `planning/DECISIONS.md` is removed; `CLAUDE.md`, `planning/CONTEXT.md`, and `planning/README.md` pointers resolve to `planning/decisions/`.
- The only surviving `DECISIONS.md` mentions are the workflow `notes`-field prompt strings (the accepted Phase-2 seam) — confirmed by grep.
- Every file under `docs/` carries OKF frontmatter; `docs/index.md` exists and lists them.
- `.claude/commands/log-work.md` creates atomic decision files (ask-first guard intact) instead of pointing at a single aggregate.
- No `.claude/workflows/*.js` file was modified, and no workflow reference resolves to a moved/renamed file.
- A dated `DEVLOG.md` entry records the change and the accepted "DECISIONS.md string" seam.

## Validation Commands
```
# No workflow JS was modified
git diff --name-only -- '.claude/workflows/*.js'   # must be empty

# Only the accepted seam (workflow notes-field prompt strings) still mentions the old file
grep -rn "DECISIONS.md" --include='*.md' --include='*.js' . | grep -v 'planning/decisions/'

# Old aggregate is gone; new tree exists
test ! -f planning/DECISIONS.md && ls planning/decisions/index.md

# Every docs/ markdown has frontmatter and an index exists
ls docs/index.md

# Standard repo health (nothing broke)
uv run pylint app/
uv run pytest
cd app && uv run python -c "from main import app"
cd app && uv run python -c "from worker.config import celery_app"
```

## Notes
- This is OKF **Phase 1** only — additive, workflow-safe. Renames of load-bearing files, `README.md`→`index.md` conversions across `planning/`, and correcting the workflow prompt strings are **Phase 2** (`planning/plans/complete-okf-phase-2.md`).
- `scaffold-project.md` is deliberately NOT brought to complete OKF here — its replacement (`/new-project` + base template) is handled centrally; leave it as-is.
- No Python workflow is added, so the tests-ship-with-every-workflow rule does not trigger; validation is "existing suite still green + no workflow JS touched."
