# Scaffold Project — Generate the full planning document infrastructure from an intake file.

## Variables

$ARGUMENTS — Optional. Path to the intake file. Defaults to `planning/intake.md`.
             If the intake file does not exist, stop and say:
             "No intake file found at <path>. Run `/new-project` first to generate it."

## Instructions

1. **Read the intake file** at `$ARGUMENTS` (or `planning/intake.md` if not provided).
   Parse all sections — Core Identity, Technical, Phases, Business Context, Key Components.

2. **Survey what already exists.**
   - Run `ls -la` to check which of the 8 target files already exist at the root and in `planning/`.
   - If any target file already exists, warn the user before overwriting:
     "The following files already exist: [list]. I'll overwrite them. Ctrl-C now if you want to abort."
     Then proceed (do not wait — this is a heads-up, not a blocking question).

3. **Create `planning/tasks/`** if it doesn't exist. Write a `.gitkeep` file inside it.

4. **Generate all 8 files in order A–H.** For each: read the intake, think carefully about what
   the project is, and write substantive content — not boilerplate placeholders. Every section
   listed below is required. Use the intake to fill specifics; use good judgment to fill gaps.
   Infer sensible defaults from the tech stack and project type where the intake is sparse.
   **CRITICAL: All generated markdown files (except CLAUDE.md) MUST begin with universal OKF YAML frontmatter block at the top of the file matching the OKF standard (e.g., type: LocalContext for CONTEXT.md, type: ProjectStatus for STATUS.md, type: Decision for DECISIONS.md, type: Plan for MASTER_PLAN.md, type: Index for README.md and planning/README.md, and type: Log for DEVLOG.md).**

---

### A — planning/CONTEXT.md  *(stable orientation file)*

Sections (in order):
1. **What This Project Is** — 2 paragraphs: what it does and the destination/outcome it builds toward.
2. **Who Is Building It** — the builder's background, through-line, and relevant experience.
3. **The Document Set** — a table: `File | Role | Volatility | Read it when…` for all 7 planning files.
4. **The Project Sequence at a Glance** — Phase names only (one line per phase), no content. Sequence is load-bearing; details live in MASTER_PLAN.md.
5. **Governing Principles** — 6–8 numbered rules that govern how this project is built. Derive from the intake; at minimum include: tests-with-every-block, just-in-time scope, sequence-not-calendar, and any project-specific architectural rules.
6. **Fast Facts** — bullet list: destination, time/capacity available, tech stack, key constraints, warm leads (if commercial).
7. Footer line: `*This file orients; it does not track. For state, open STATUS.md. For why choices were made, open DECISIONS.md.*`

---

### B — planning/STATUS.md  *(volatile state tracker)*

Sections (in order):
1. Header: `**Last updated:** <today> — Project initialized` and `**Current focus:** Phase 0, Block A — Foundation`
2. **How to Read / Update This File** — brief instructions (status values, what to update and when, keep it terse).
3. **Progress Table** — one sub-table per phase. Derive block names from the intake's phases.
   All blocks start as `Not started`. Columns: `Block | What | Status | Notes`.
4. **Business Development / Visibility** (if commercial) — same format, separate table.
5. **Decisions & Deviations Log** — empty section with the prompt: `*Record deviations from the plan and notable choices here.*`
6. **Quick Self-Check** — 3 bullets: Is Current focus accurate? Any In progress rows actually Done? Anything Blocked?
7. Footer: `*State only. For what things mean, see the plans. For orientation, see CONTEXT.md.*`

---

### C — planning/DECISIONS.md  *(append-only decisions log)*

Header: explain the format (what decided · why · what rejected and why) and the append-only rule.

Write D1–D3 covering the most fundamental choices already made:
- **D1** — The core goal of the project (expertise, product, revenue — whichever the intake indicates). Include what was rejected (e.g. "revenue-first without foundation").
- **D2** — The sequencing principle (dependencies and competence, not calendar). Include why calendar sequencing was rejected.
- **D3** — The single most important architectural decision visible in the intake (language choice, database choice, monorepo vs multi-repo, deployment model, etc.). Be specific.

Footer: `*Add entries here as decisions are made. Never edit old entries — supersede them with a new entry.*`

---

### D — planning/MASTER_PLAN.md  *(the strategic plan)*

This is the largest file. Write it at the depth of the example in the orchestration repo's planning — elaborate, thoughtful, substantive. Not a stub.

Sections (in order):
1. **Title** — `# <Project Name> — Master Plan` with created date and "Living document" note.
2. **The Goal, Stated Plainly** — 2–3 paragraphs: what the project is, why it matters, what "ready" means (the competence or delivery checkpoint).
3. **The Destination** — the named product or outcome. If commercial: the buyer, the differentiator, the through-line connecting builder to product.
4. **Architecture / Design Overview** — the key structural design: how the system is organized, what are the layers, ASCII diagram if useful. Include the load-bearing design decisions.
5. **Phase 0 — Foundation** — one sub-section per block. For each block: **What**, **Why**, build notes (specific tasks, tools, conventions), acceptance criteria (testable, specific "done when" conditions).
6. **Phase 1 — Core** — same structure. This is where the first shippable feature set lives.
7. **Phase 2 — Depth / Hardening** — same structure. Hardening, optimization, second-layer features.
8. **Phase 3+ — Differentiating Build** — the capstone or the hardest/most-differentiating work.
9. **Business Development / Visibility** (if commercial) — content plan, networking approach, first paid offer trigger, job hunt notes if applicable.
10. **Quick Reference Sequence Table** — `| Phase | Block | What | Why | Role in destination |` — one row per block.
11. Footer: `*Sequenced by dependency and competence, not calendar. When life gets in the way, pick up where you left off.*`

---

### E — planning/README.md  *(navigation only)*

Sections:
1. Title: `# <Project Name> — Planning Docs`
2. One-line description of what this directory is.
3. **Files table** — `| File | What it is | Open it when… |` covering all 6 planning files plus `tasks/`.
4. **Read order for a newcomer** — numbered list (CONTEXT → STATUS → relevant plan section).
5. Brief note: "What's NOT here" (code repos, generated task specs live in `tasks/`).
6. Footer tagline (one line).

---

### F — CLAUDE.md  *(repo-scoped agent context)*

This file is the agent's working guide for this specific repo. Write it as instructions to an agent that is about to do work here.

Sections:
1. Opening line: one sentence describing what the repo is.
2. **Before you start** — pointers to `planning/CONTEXT.md` (strategic context), `planning/STATUS.md` (current state), `planning/DECISIONS.md` (settled choices).
3. **Standing rules** — numbered list. At minimum include:
   - Every block ships with tests covering its core functionality. No exceptions.
   - All prompts in `.j2` files, never hardcoded in source (if the stack includes LLM calls).
   - New modules/workflows registered in the appropriate registry (if applicable).
   - No deployment-specific logic inside core modules (inject via config).
   - Any project-specific rules derived from the intake.
4. **Known bugs** — table of `Location | Bug`. If none at init, write: "None known at initialization."
5. **Build / test / run** — code block with exact commands derived from the intake's stack.
6. **Directory map** — ASCII tree of key directories (top 2–3 levels).
7. **What NOT to touch** — reference-only code, generated files, migration history, etc.

---

### G — README.md  *(root project README)*

Standard project README. Sections:
1. Title + one-line description (same as `planning/CONTEXT.md`'s first sentence).
2. **Prerequisites** — what must be installed.
3. **Setup** — numbered steps to get from zero to running.
4. **Running locally** — code blocks with the exact commands from `CLAUDE.md`.
5. **Running via Docker** — if the intake mentions Docker/containerization.
6. **Tests** — one-liner to run the test suite.
7. **Directory map** — same tree as `CLAUDE.md` (copy).
8. **Documentation** — table linking to `planning/CONTEXT.md`, `planning/MASTER_PLAN.md`, and any `docs/` files.

---

### H — DEVLOG.md  *(append-only daily working log)*

```
# DEVLOG — <Project Name>

*Append-only working log. One dated entry per session. Newest entries at the top.*

---

## <today's date>

Project initialized. Planning infrastructure scaffolded via `/scaffold-project`.
All planning documents created: planning/CONTEXT.md, planning/STATUS.md,
planning/DECISIONS.md, planning/MASTER_PLAN.md, planning/README.md, CLAUDE.md,
README.md, DEVLOG.md. Next step: run `/generate-tasks phase0-blockA` to generate
the task spec for the first block.

```diff
(no code changes — planning files only)
```
```

---

## After Writing All Files

Output a summary:

```
Planning infrastructure created:

  planning/CONTEXT.md     ✓ written
  planning/STATUS.md      ✓ written
  planning/DECISIONS.md   ✓ written
  planning/MASTER_PLAN.md ✓ written
  planning/README.md      ✓ written
  planning/tasks/         ✓ created (stub)
  CLAUDE.md               ✓ written
  README.md               ✓ written
  DEVLOG.md               ✓ written

Review the generated documents — especially MASTER_PLAN.md — and edit
anything that needs adjustment. Then start the SDLC pipeline:

  /generate-tasks phase0-blockA
```

## Context / Files to Read

- `planning/intake.md` (or `$ARGUMENTS`)
- Any existing `CLAUDE.md`, `README.md` (to avoid losing content if overwriting)
