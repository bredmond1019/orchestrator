# SDLC Block Orchestration (`/sdlc-block`)

*One level up from `/sdlc-task`: drive an **entire block** to completion by orchestrating many parallel `/sdlc-task` pipelines across dependency-ordered waves, with bounded retries, failure triage, escalation, and ordered merges.*

For the single-task and sequential pipelines, see [`sdlc-dynamic-workflows.md`](sdlc-dynamic-workflows.md). This document covers the block-level orchestrator that composes them.

---

## Where it fits

| Workflow | Scope | Isolation | You run merges? |
|---|---|---|---|
| `/sdlc-run` | one task or full block, **sequential** | none (runs on main) | n/a |
| `/sdlc-task` | **one** task | own worktree | yes — `/clean-worktree` |
| **`/sdlc-block`** | **whole block**, parallel waves | one worktree per task | **no — the orchestrator merges for you** |

`/sdlc-block` calls `workflow('sdlc-task', …)` once per task (nesting is one level deep; `sdlc-task` uses `agent()` internally, so there is no illegal second-level nesting). It then merges each wave before the next begins.

---

## Usage

```
/sdlc-block phase0-blockD                    # run every task in the block
/sdlc-block phase0-blockD 1-7                 # run only tasks 1–7 (positional range)
/sdlc-block phase0-blockD --tasks 1,3,5-7     # same idea, explicit flag, list + range
/sdlc-block phase0-blockD --max-wave-width 6  # widen parallelism for a trusted block
/sdlc-block phase0-blockD --max-retries 3
```

| Arg | Meaning | Default |
|---|---|---|
| `<blockId>` | **Required.** Drives every path — `planning/tasks/<blockId>/…`. | — |
| `[range]` | Optional task selection: 2nd positional **or** `--tasks`. Forms: `1-7`, `1,3,5`, `1-3,7`, `5`. | all tasks |
| `--max-retries N` | Total `/sdlc-task` attempts per task before escalation. | `2` |
| `--max-wave-width W` | Max full pipelines run concurrently per batch. | `3` |

Everything derives from `blockId`, exactly like `/sdlc-task` — the orchestrator is fully general across blocks. There is nothing block-specific in the workflow.

---

## Phases

```
┌───────────┐
│  Analyze  │  resume-scout main · load or GENERATE the execution plan
└─────┬─────┘
      │
┌─────▼─────┐   ┌─────────┐
│  Wave N   │ → │ Merge N │   (repeat per wave, in dependency order)
└───────────┘   └─────────┘
      │
┌─────▼─────┐
│  Report   │  block report · apply STATUS/DEVLOG ONCE · surface escalations
└───────────┘
```

### 1. Analyze — agent proposes the graph, **code** computes the waves

The single most important reliability decision. The wave structure is **not** an opaque agent judgment:

- **An agent emits a dependency graph *with evidence*.** Per task: `filesCreated`, `filesModified`, `dependsOn`, and the *quote* from `tasks.md`/`breakdown.md` that establishes each dependency edge. Requiring evidence forces grounding and makes the graph auditable. The agent also classifies each shared file as **additive** (every touching task only appends — e.g. `app/services/__init__.py`, `app/workflows/workflow_registry.py`) or **exclusive** (someone rewrites it — e.g. `app/api/endpoint.py`).
- **Deterministic JS computes the waves** by topological layering of that graph. Two kinds of edges order the tasks:
  - *dependency edges* — task A consumes a symbol/file task B creates;
  - *conflict edges* — two tasks edit the same **exclusive** file → serialized (lower task number first).
  Each topological layer becomes one wave; tasks within a wave are mutually independent and share no exclusive file, so they are safe to run in parallel.
- The agent is told to **bias conservative**: when unsure an edge exists, include it; when unsure a file is additive, treat it as exclusive. Over-serializing costs wall-clock; a bad merge costs correctness.

The generated plan is written to `planning/tasks/<blockId>/execution-plan.json` and committed. On the next run it is **loaded verbatim** (the expensive analysis is skipped), and you can hand-edit it before re-running.

#### `execution-plan.json`

```json
{
  "blockId": "phase0-blockD",
  "additiveFiles": ["app/services/__init__.py", "app/workflows/workflow_registry.py"],
  "tasks": {
    "4":  { "num": 4, "title": "TranscriptService", "dependsOn": [7],
            "filesCreated": ["app/services/transcript_service.py"],
            "filesModified": ["app/services/__init__.py"],
            "evidence": "\"fetch_and_chunk … delegates to ChunkingService (Task 7)\"" },
    "10": { "num": 10, "title": "Clean API Contract", "dependsOn": [],
            "filesCreated": ["app/api/health.py"],
            "filesModified": ["app/api/endpoint.py", "app/main.py"], "evidence": "" }
  },
  "waves": [
    { "label": "Wave 1", "parallel": false, "tasks": [1],                  "mergeOrder": [1] },
    { "label": "Wave 2", "parallel": true,  "tasks": [2,3,5,6,7,8,9,10],   "mergeOrder": [2,3,5,6,7,8,9,10] },
    { "label": "Wave 3", "parallel": false, "tasks": [4],                  "mergeOrder": [4] }
  ]
}
```

> Wave width is **not** baked into the plan — `--max-wave-width` batches a wide wave at *execution* time, so the same plan is reusable at any width.

### 2. Wave N — run tasks with a retry + triage state machine

Each task runs through `workflow('sdlc-task', '<blockId> <N>')`. On a non-PASS result, a **triage agent** classifies the failure before any retry:

| Signal from the `sdlc-task` return | Class | Action |
|---|---|---|
| `NOT_REACHED` / null result / worktree-setup crash / agent died | **RETRYABLE** (infra) | clean-slate re-run |
| FAIL, but the failing acceptance criteria **changed** from last attempt | RETRYABLE (progressing) | clean-slate re-run |
| FAIL with the **same** criteria as last attempt | **MAJOR** | escalate |
| Failure references a missing upstream symbol/dependency | **MAJOR** (structural) | escalate |

The triage is deliberately calibrated: `/sdlc-task` already runs **up to 3 internal fix passes** before it returns, so a genuine repeated criteria failure is unlikely to be fixed by another full re-run — it escalates instead of burning tokens. When unsure, triage prefers **MAJOR** (escalation is cheap; a wasted clean-slate retry is not).

- **Retries are clean-slate.** A RETRYABLE failure tears down that attempt's worktree/branch (so they don't accumulate) and re-invokes `/sdlc-task` fresh from main, up to `--max-retries` total attempts.
- **Escalation preserves state.** A MAJOR failure (or exhausted retries) keeps the worktree and branch intact for you to inspect, and records the task #, review-report path, worktree path, and failure reasons.

### 3. Merge N — selective-union merge, in task-number order

After a wave's tasks settle, passing branches merge into main in `mergeOrder`:

1. **Plain `git merge --no-ff`** first. (`--ff-only` is a red herring — every branch after the first shares the pre-wave base and can't fast-forward.) If it auto-resolves, done.
2. **On conflict**, inspect the conflicted files:
   - **All conflicted files are additive** → abort and redo as `git merge -X union` (safe — union only touches append-only files like `__init__.py`).
   - **Any exclusive file conflicts** → abort, mark the task **merge-escalated**, preserve the branch. A silent bad merge is worse than a halt; `-X union` is **never** applied globally.
3. On success, the worktree is removed and the branch deleted. On escalation, both are preserved.

`STATUS.md` and `DEVLOG.md` are **never** touched inside worktrees (`sdlc-task` already defers them to per-task log files).

### 4. Report — write once, surface escalations

- Writes `planning/tasks/<blockId>/reports/block-workflow.md`: an outcome table (task → result/verdict/merge/commit), an **Escalations** section with worktree paths + review reports, and the resume command.
- Applies `DEVLOG.md` entries from each merged task's log and writes a **single authoritative `STATUS.md` update** — block → `Done`/`In progress`, Current focus → next block (or the lowest unmerged task). This is the fix for the "Current focus thrash" that per-task log application caused under out-of-order parallel waves.
- Overall verdict: **PASS** (all selected tasks merged) / **PARTIAL** (some merged, some escalated/skipped) / **BLOCKED** (nothing merged).

---

## Failure handling: poison the subtree, not the block

Because the orchestrator holds the real dependency graph, an escalation poisons **only the dependent subtree**. A task is *skipped* if any task it depends on escalated or was itself poisoned; everything independent keeps running. This maximizes completed work versus a blunt "abort all later waves." The blast radius of a failure is exactly its downstream dependents — no more, no less.

```
Task 7 escalates  →  Task 4 (dependsOn 7) is SKIPPED
                  →  Tasks 2,3,5,6,8,9,10 (independent) still run and merge
```

---

## Resumption

Re-run `/sdlc-block <blockId>` (with the same or a different range). **Git is the source of truth**: a task is "done" if its `taskN-workflow.md` is committed on main with a PASS verdict.

- Done tasks are detected and **skipped**.
- Escalated tasks are **retried** (after you fix the blocker or edit `execution-plan.json`).
- A preserved worktree from a prior escalation is reported in the Analyze phase.

If you gave a task **range** whose dependencies fall outside it and aren't yet done on main, Analyze warns up front (e.g. *"task 4 needs task 7"*) rather than letting it fail mid-run.

---

## Token efficiency

An orchestration that spawns dozens of agents needs deliberate cost control. The levers in use:

| Lever | How |
|---|---|
| **Model tiering** | Principle: **Opus on planning, Sonnet on the rest.** In the orchestrator, only the dependency-graph **analysis** (planning) runs on **opus**; **sonnet** drives triage, merge, and report; **haiku** handles teardown and plan-writing. The child `/sdlc-task` follows the same rule — **opus** only for the spec-authoring fallback (`generate-tasks`), **sonnet** for every implement/test/review/document/report stage (review is safe on Sonnet because an authoritative fresh-test run gates the verdict, and fix failures escalate rather than silently ship). See its `MODEL` map. The real planning leverage is upstream: run the `/generate-tasks` and `/breakdown` skills on an Opus session. |
| **Staged model escalation** | Inside `/sdlc-task`, the **final** fix pass and review attempt before the loop gives up run on **opus** (`ESCALATION_MODEL`); the earlier cycles stay on Sonnet. A hard task that has already failed twice gets one strong shot before escalating — without paying Opus on every task. See [sdlc-dynamic-workflows.md](sdlc-dynamic-workflows.md#staged-model-escalation). |
| **Triage-gated retries** | A clean-slate retry re-runs a full ~8-agent pipeline. Triage ensures that spend only happens on transient/progressing failures, never on a stuck one. |
| **Plan caching** | `execution-plan.json` is committed and reused, so re-runs skip the expensive graph analysis entirely. |
| **Budget guard** | If a token target is set for the turn (`+500k`-style), the orchestrator stops launching new waves when the remaining budget can't cover one (estimated per wave) and reports a resume command instead of overrunning. |
| **Fail-fast** | A Wave-1 prerequisite failure poisons its whole subtree, short-circuiting doomed downstream work instead of running it. |

### Picking `--max-wave-width`

Width barely affects **total** tokens — every task runs eventually regardless of batching. What width controls is **peak token rate, failure blast radius, and merge complexity**. Because `/sdlc-task` is internally sequential, each in-flight task occupies roughly one concurrency slot, so width ≈ "pipelines running at once."

- **Default `3`** — a real 3× wall-clock win, but a systemic problem (bad shared-file assumption, missing dep) burns at most 3 pipelines before the merge checkpoint catches it.
- **Raise to `4–6`** once a block's plan is trusted and you want throughput.
- **Drop to `1`** to run a wave strictly sequentially for debugging.

> Workflow concurrency is capped at ~`min(16, cores−2)` slots **shared** across the orchestrator and all child `sdlc-task` workflows, and the **token budget is shared** too. Wide waves interleave through those slots rather than truly running N×.

---

## Worked example — `phase0-blockD`

11 tasks. A plausible computed plan:

| Wave | Tasks | Why |
|---|---|---|
| 1 | `1` (deps) | `pyproject.toml`/`uv.lock` must land on main before any worktree branches off — isolated and merged first to avoid lockfile conflicts. |
| 2 | `2,3,5,6,7,8,9,10` | Independent services + scaffold; each only appends to `__init__.py`/`workflow_registry.py` (additive → union-safe). Batched `--max-wave-width 3` at a time. |
| 3 | `4` | `TranscriptService` depends on `ChunkingService` (Task 7) — runs after Wave 2 merges. |
| 4 | `11` (Validate) | Final whole-block validation, sequential. |

Run just the services first: `/sdlc-block phase0-blockD 1-7`. Finish later: `/sdlc-block phase0-blockD` (done tasks skipped).

---

## Edge cases

| Situation | Behavior |
|---|---|
| `execution-plan.json` missing | Analyze generates it from `tasks.md` (+ `breakdown.md`), writes & commits it. |
| Existing plan present | Loaded verbatim; analysis skipped. Hand-edit it to override waves/deps. |
| Task fails transiently | Triage → RETRYABLE → clean-slate retry (failed worktree torn down). |
| Task fails structurally / repeatedly | Triage → MAJOR → escalate; worktree preserved; dependents skipped. |
| Retries exhausted | Escalate (same as MAJOR). |
| Merge hits an exclusive-file conflict | Abort, escalate that task, preserve the branch — never auto-resolved. |
| Selected range omits a prerequisite | Pre-flight warning in Analyze; the task may still fail and escalate. |
| Interrupted mid-run | Re-run `/sdlc-block <blockId>` — done tasks skipped, escalated retried. |
| Token target exhausted | Budget guard stops before the next wave; resume command printed. |

---

## Relationship to existing commands

- **`/sdlc-task`** — the per-task pipeline this orchestrates. Unchanged; still usable standalone.
- **`/clean-worktree`** — the manual single-branch merge. `/sdlc-block` performs the equivalent inline (with the selective-union strategy) so you don't merge by hand.
- **`review-and-merge-tasks-9-12.js`** — the predecessor that established the parallel-review-then-ordered-merge pattern. `/sdlc-block` generalizes it: dynamic dependency analysis, per-task retry/triage, and escalation replace the fixed task list and skill-based merge.
