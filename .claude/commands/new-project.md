# New Project — Gather project details through a focused interview, then write planning/intake.md.

## Variables

$ARGUMENTS — Required. Either a file path to an existing project spec/description, OR inline
             text describing the project. If omitted, stop and say:
             "Usage: /new-project <description or path/to/spec.md>"

## Instructions

1. **Read provided context.**
   - If `$ARGUMENTS` looks like a file path (contains `/` or ends with `.md`, `.txt`, etc.), read that file.
   - Otherwise treat it as a plain-text project description.

2. **Survey the existing repo.**
   - Run `ls -la` and `git ls-files` (or `find . -maxdepth 3 -type f` if not a git repo).
   - Read `README.md` and `CLAUDE.md` if they exist.
   - Read any files in `planning/` if the directory exists.
   - Goal: understand what's already decided so you don't ask redundant questions.

3. **Identify gaps across these four question groups.** Only ask what's NOT already answered
   by the provided description or existing files.

   **Group 1 — Core Identity**
   - What does this project do, in one sentence?
   - Who is it for — the end user, buyer, or internal consumer?
   - What problem does it solve, and why does it matter?
   - What does "done" look like — what is the named destination or shipped outcome?
   - What makes this approach different or worth building specifically?

   **Group 2 — Technical**
   - Primary language and framework / stack?
   - Existing infrastructure to build on (monorepo, services, databases, APIs)?
   - Key architectural non-negotiables or hard constraints?
   - Known external dependencies (APIs, SDKs, services)?

   **Group 3 — Phases & Sequence**
   - What are the rough phases (e.g. Foundation → Core Features → ...)?
   - What hard dependencies exist between phases?
   - Estimated scope (weeks, months, open-ended)?
   - What must exist before anything useful can run end-to-end?

   **Group 4 — Business / Context**
   - Solo project, team, or client work?
   - Purpose: commercial product, internal tool, learning project, or portfolio?
   - Any known constraints — timeline, budget, team size, compliance?
   - Business goals, if commercial: first client, revenue target, partnership?

4. **Ask ALL needed questions in ONE message.** Group them clearly under the headings above.
   Skip any group where all questions are already answered. Be direct — do not pad or over-explain.
   Example opening: "Before I write the intake, I need answers to a few things I couldn't
   determine from your description:"

5. **Wait for the user's answers.** If a critical follow-up surfaces (e.g. an answer
   changes the scope or introduces a new dependency), ask it. Otherwise proceed.

6. **Write `planning/intake.md`** using the format below. Create the `planning/` directory
   if it doesn't exist. Synthesize all available information — don't just transcribe answers;
   draw inferences and flag anything still uncertain with a `<!-- TODO: clarify -->` comment.

7. **Report the result:**
   ```
   Intake written to planning/intake.md.

   Review it and make any edits, then run:
     /scaffold-project
   to generate all planning documents (CONTEXT.md, STATUS.md, DECISIONS.md,
   MASTER_PLAN.md, planning/README.md, CLAUDE.md, README.md, DEVLOG.md).
   ```

## Output Format — planning/intake.md

```md
# Project Intake — <Project Name>

*Created: <date>. Source of truth for `/scaffold-project`. Edit this file before re-scaffolding.*

---

## Core Identity

- **Project name:** ...
- **One-sentence description:** ...
- **Target user / buyer:** ...
- **Problem solved:** ...
- **Destination ("done" looks like):** ...
- **Unique angle / differentiator:** ...

---

## Technical

- **Primary language / stack:** ...
- **Existing infrastructure:** ...
- **Key architectural constraints:** ...
- **Known external dependencies (APIs, services):** ...

---

## Phases & Sequence

- **Phase 0 — Foundation:** ...
- **Phase 1 — Core:** ...
- **Phase 2 — Depth / Hardening:** ...
- **Phase 3+ — Differentiating build / capstone:** ...
- **Hard dependencies between phases:** ...
- **Estimated scope:** ...

---

## Business / Context

- **Project type:** solo | team | client work
- **Purpose:** commercial | internal | learning | portfolio
- **Constraints:** ...
- **Business goals:** ...

---

## Key Components

*Major modules, workflows, services, or systems to build — one bullet per component.*

- ...

---

## Notes / Additional Context

...
```
