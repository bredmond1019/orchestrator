---
type: Guide
title: SDLC Flow Workflow
description: Setup, event payload, node-by-node behavior, state file format, and debugging guide for the SDLC_FLOW workflow.
doc_id: sdlc-flow-workflow
layer: [engine]
project: orchestrator
status: active
keywords: [SDLC_FLOW, sdlc-flow, worktree, harness.json, triage, review, PR, Claude Code, resume]
related: [workflows, api-reference, configuration, data-contract]
---

# SDLC Flow Workflow

`SDLC_FLOW` drives a structured task list (`SDLCTask` records) through a sequential
implement → test → triage → review loop, task by task, in one shared git worktree —
then patches docs, writes a wrap-up log, and opens a PR. It is the orchestrator-native
graduation of the `/sdlc-flow` slash-command pipeline: same lifecycle, but run as a
`Workflow`/`Node` graph (`app/workflows/sdlc_flow_workflow.py`) instead of a sequence
of manually-invoked skills.

Use this doc for **setup, triggering, debugging, and state-file mechanics**. For the
node DAG diagram and the event payload shape, see the
[`SDLC Flow` section of the workflow catalog](workflows.md#6-sdlc-flow-sdlc_flow) — this
doc doesn't repeat that, it goes one level deeper.

## When to use this vs. the slash commands

- **`SDLC_FLOW` (this workflow)** — when you want the pipeline running as an async
  Celery job behind the API, driven by an external caller (e.g. a future scheduler,
  or `bastion`), with progress readable from `task_context`/`node_runs` per the
  [data contract](data-contract.md).
- **`/sdlc-flow` (slash command / skill)** — when you're at a terminal and want the
  same pipeline run interactively in this session, with live narration.

Both consume the same kind of task list and both write the same
`sdlc-flow-state.json` shape, but they are two independent implementations — fixing
a bug in one does not fix the other. `SDLCBlockWorkflow` (a wave-parallel variant
using `ParallelNode`, mirroring `/sdlc-block`) is deferred future scope, not yet built.

> **Keeping the two in sync.** `SDLCTask` (`app/schemas/sdlc_schema.py`) is the schema
> `/sdlc-flow`'s `tasks.json` contract was deliberately aligned *to* (base-template
> `planning/decisions/D44-tasks-json-task-list.md` / `D45-tasks-json-orchestrator-schema-
> alignment.md`) — this doc's shape is the one being matched, not the other way around. If
> base-template's `.claude/workflows/sdlc-flow.js` or `generate-tasks.md` changes again,
> check this file and `SDLCTask` still agree; see the `verify-sdlc-flow-schema-vs-base-
> template-d44-d48` entry in this repo's `planning/state.json` `carryover[]` for the current
> status of that check.

## Setup

### 1. Task list input

`LoadTaskStateNode` needs one of these two files inside the target worktree, at
`planning/<spec_slug>/`:

- **`sdlc-flow-state.json`** — if present, this run resumes from it (see
  [Resuming a run](#resuming-a-run)).
- **`tasks.json`** — otherwise, this bootstraps a fresh `SDLCState`. It must be a
  JSON array of task objects matching `SDLCTask` (`app/schemas/sdlc_schema.py`):

  ```json
  [
    {
      "task_id": 1,
      "title": "Add the SDLCTask schema",
      "description": "Define SDLCTask/SDLCState/SDLCTelemetry in app/schemas/sdlc_schema.py...",
      "acceptance_criteria": ["parse_task_range handles ranges and single ids", "..."],
      "validation_commands": [],
      "max_attempts": 3
    }
  ]
  ```

  Only `task_id`, `title`, and `description` are required — `acceptance_criteria`
  defaults to `[]`, `status` defaults to `pending`, `attempt_count` to `0`,
  `max_attempts` to `3`. If neither file exists, `LoadTaskStateNode` raises
  `FileNotFoundError` naming the spec slug.

### 2. `planning/harness.json`

`TestTaskNode` runs whatever `planning/harness.json` declares (same schema the
`/test` skill and `/sdlc-flow` slash command use — see the repo's own
`planning/harness.json` for a real example). If the file is absent, `TestTaskNode`
treats the task as passing with an empty check list — don't rely on this in a real
spec; it means nothing was actually validated.

### 3. Environment / auth

| Node(s) | Requirement |
|---|---|
| `ImplementTaskNode`, `TriageTaskNode` | `ModelProvider.CLAUDE_CODE_SDK` — runs against your **Claude Code subscription**, not the metered API. Needs the local `claude` CLI installed and authenticated, plus the `CLAUDE_CODE_*` vars in `app/.env` (`CLAUDE_CODE_BIN`, `CLAUDE_CODE_CWD`, `CLAUDE_CODE_PERMISSION_MODE`, `CLAUDE_CODE_SDK_TIMEOUT_SECONDS`, ...). The SDK backend deliberately blanks `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` for the spawned CLI so a host-exported key can't redirect billing. |
| `ConsolidatedReviewNode`, `PatchDocsNode`, `WrapUpNode` | `ModelProvider.ANTHROPIC` — needs `ANTHROPIC_API_KEY` set (metered API, current `claude-sonnet-5`). |
| `SetupWorktreeNode` | A git repo with `origin` reachable; creates the worktree via `git worktree add <path> -b <branch> origin/main`. |
| `PullRequestNode` | `gh` CLI installed and authenticated (`gh auth status`), and push access to `origin`. Only invoked when the event's `auto_pr` is `true` (default). |

Missing `ANTHROPIC_API_KEY` or an unauthenticated `claude`/`gh` CLI surfaces as a
plain exception from the offending node's `subprocess`/SDK call — the workflow does
not pre-flight check these, so the first failure you'll see is mid-run, not at
trigger time.

## Triggering a run

```bash
curl -X POST http://localhost:8080/events/ \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $ORCHESTRATION_API_KEY" \
  -d '{
    "workflow_type": "SDLC_FLOW",
    "data": {
      "spec_slug": "sdlc-workflow-architecture/tasks.md",
      "task_range": "1-3",
      "resume": false,
      "auto_pr": true
    }
  }'
```

The response is a `202` with a `task_id`. Poll status via the API's event-status
endpoint or `scripts/inspect_run.py <task_id>` (see [scripts.md](scripts.md)) — that
script dumps `task_context.nodes` / `node_runs` for a run, which is the fastest way
to see exactly which node ran, what it wrote, and where it stopped.

### Event fields

| Field | Type | Default | Notes |
|---|---|---|---|
| `spec_slug` | string | — (required) | Directory name under `planning/` holding `tasks.json` / `sdlc-flow-state.json` |
| `task_range` | string \| null | `null` (all tasks) | e.g. `"1-3,5"` — 1-indexed, inclusive; parsed by `SDLCFlowEventSchema.parse_task_range` (raises a `ValidationError` on malformed input like `"3-1"` or `"abc"` *before* the workflow runs) |
| `resume` | bool | `false` | Reattach to an existing worktree/state instead of creating a new one |
| `auto_pr` | bool | `true` | Whether `PullRequestNode` pushes and opens a PR at the end |
| `branch_name` | string \| null | derived: `sdlc/<spec_slug>` | Override the git branch name |

## The task loop, step by step

For each task dispatched by `TaskQueueRouterNode`:

1. **`ImplementTaskNode`** — dispatches to Claude Code (via the `sdlc_implement_task.j2`
   prompt) to implement the task in the worktree. Reports `summary`,
   `modified_files`, `tests_added` — it does not write code itself, it only records
   what the agent says it did.
2. **`TestTaskNode`** — runs `planning/harness.json`'s checks against the worktree.
   Deterministic, no LLM call.
3. **`TriageTaskNode`** — if all checks passed, records `PASS` with no model call.
   If `attempt_count >= max_attempts`, records `MAJOR_BAIL` with no model call
   (deterministic short-circuit). Otherwise classifies the failure via an LLM call
   into `RETRYABLE` or `MAJOR_BAIL`.
4. **`TriageRouterNode`** routes: `PASS` → `ConsolidatedReviewNode`,
   `RETRYABLE` → back to `ImplementTaskNode` (another attempt),
   `MAJOR_BAIL` → `WrapUpNode` (this task, and the whole run, ends here).
5. **`ConsolidatedReviewNode`** — reviews the full `git diff main..HEAD` against the
   task's `acceptance_criteria`, returns `PASS` / `FAIL` / `PARTIAL` plus an `issues`
   list.
6. **`ReviewRouterNode`** routes: `PASS` → `UpdateTaskStatusNode` (task done, next
   task). `FAIL`/`PARTIAL` with issues → back to `ImplementTaskNode` (treated as
   fixable). `FAIL`/`PARTIAL` with **no issues, or more than 5** → `WrapUpNode`
   (treated as structural — an empty issue list on a non-`PASS` verdict means the
   model judged the diff fundamentally off-track, not just missing something
   small, so retrying isn't expected to converge).
7. **`UpdateTaskStatusNode`** — mutates the task's `status` (`done`/`failed`) and
   `SDLCState.telemetry` counters.
8. **`SaveStateNode`** — writes `sdlc-flow-state.json` and commits it, then loops
   back to `TaskQueueRouterNode` for the next `pending` task.

Once no `pending` task remains, the loop exits to `PatchDocsNode` → `WrapUpNode` →
`PullRequestNode`.

## The state file

`planning/<spec_slug>/sdlc-flow-state.json` is the full `SDLCState.model_dump_json()`
— it's committed after every task, so a killed or crashed run can always resume from
its last committed task boundary. Top-level shape:

```json
{
  "spec_slug": "...",
  "phase_id": null,
  "block_id": null,
  "global_status": "pending",
  "tasks": [
    {
      "task_id": 1,
      "title": "...",
      "description": "...",
      "acceptance_criteria": ["..."],
      "status": "done",
      "validation_commands": [],
      "attempt_count": 1,
      "max_attempts": 3
    }
  ],
  "telemetry": {
    "total_attempts": 1,
    "budget_spent": 0.0,
    "tasks_passed": 1,
    "tasks_failed": 0
  }
}
```

`SDLCTaskStatus` values: `pending` → `in_progress` (not currently set by any node —
tasks move straight `pending` → `done`/`failed`) → `done` | `failed` | `skipped`
(`skipped` is defined in the enum but not yet produced by any node — reserved for a
future manual-skip path).

### Resuming a run

Pass `"resume": true` with the same `spec_slug` (and, if you overrode it originally,
the same `branch_name`). `SetupWorktreeNode` reattaches to the existing
`trees/<branch>` directory instead of creating a new worktree, and
`LoadTaskStateNode` loads `sdlc-flow-state.json` (not `tasks.json`) since it now
exists — so any task already `done`/`failed` is skipped and the loop picks up at the
first remaining `pending` task. `task_range` still applies as an additional filter
on top of resumed state.

## Debugging

**"Nothing happened / task_id never progresses"** — check the Celery worker logs;
confirm the worker is running (`cd app && uv run celery -A worker.config.celery_app
worker --loglevel=info`) and that `SDLC_FLOW` is registered (it's covered by
`tests/api/test_endpoint.py::TestSchemaRegistryCompleteness`, so a missing
registration would already fail CI — if you hit this in a fresh clone, check
`app/workflows/workflow_registry.py` and `app/api/schema_registry.py` both have the
`SDLC_FLOW` entry per standing rule 6 in `CLAUDE.md`).

**"`FileNotFoundError: No state or tasks file found for <spec_slug>`"** — neither
`sdlc-flow-state.json` nor `tasks.json` exists at
`<worktree>/planning/<spec_slug>/`. Check the `spec_slug` you sent matches the
directory name exactly (it's used verbatim as a path segment, no slugification).

**"Run stopped after one task, no error"** — check that task's `SDLCTriageVerdict`
in `sdlc-flow-state.json` isn't the reason: a `MAJOR_BAIL` (either from
`TriageTaskNode` — real failures the model judged non-retryable, or max attempts
reached — or from `ReviewRouterNode`'s structural-FAIL path) ends the whole run at
`WrapUpNode`, it does not skip to the next task. Read `WrapUpNode`'s output
(`log_entry` / `report`) for the model's stated reason.

**"Task keeps retrying and never converges"** — check `attempt_count` vs
`max_attempts` in the state file for that task; `TriageTaskNode` force-bails once
the budget is hit, so a genuinely stuck task terminates rather than looping forever.
If `max_attempts` is 3 and it's still not bailing, verify `UpdateTaskStatusNode` is
actually incrementing `attempt_count` on `RETRYABLE` (it should — see
`update_task_status_node.py`).

**"`git push` or `gh pr create` failed"** — `PullRequestNode` raises a
`RuntimeError` with the subprocess's `stderr` verbatim; check `gh auth status` and
that the branch was actually created (`git worktree list` from the repo root, or
`git -C trees/<branch> log --oneline -5`).

**"Worktree already exists" / stale worktree from a killed run** — `SetupWorktreeNode`
only reattaches when `resume=true`; without it, a leftover `trees/<branch>`
directory from a prior crashed run causes `git worktree add` to fail. Clean it up
with `git worktree remove trees/<branch> --force && git worktree prune` before
re-triggering with `resume=false`, or re-trigger with `resume=true` to continue it.

**Inspecting a specific node's output** — every node's write lands in
`task_context.nodes["<NodeName>"]["result"]` (or `["output"]` for the raw
`AgentNode` output, per the data contract). `scripts/inspect_run.py` prints this for
a given `task_id`; for a quick one-off check against a live worktree without the
API, you can also just read `sdlc-flow-state.json` directly.

## Architectural notes (read before modifying the DAG)

- The retry/loop-back edges (`TriageRouterNode`/`ReviewRouterNode` → `ImplementTaskNode`,
  `SaveStateNode` → `TaskQueueRouterNode`) are **runtime-only routing decisions**
  inside each router's `determine_next_node`, not declared `NodeConfig.connections`
  edges. `WorkflowValidator._has_cycle` was patched to skip a router node's own
  declared connections for exactly this reason — see the module docstring in
  `app/workflows/sdlc_flow_workflow.py` and the `_has_cycle` section of
  [api-reference.md](api-reference.md) before changing either the DAG or the
  validator, since they now depend on each other's exemption.
- `BaseRouter.process()` merges into `task_context.nodes` via `update_node` rather
  than overwriting — this lets `TaskQueueRouterNode` stash the dispatched task's
  fields under its own `result` key without a later `next_node` write wiping it out.
  If you add a new router that needs to store data on itself, rely on this merge
  behavior rather than direct dict assignment.
- Nodes that read "the current mutated state" (`TaskQueueRouterNode`,
  `UpdateTaskStatusNode`, `SaveStateNode`, `WrapUpNode`) all follow the same
  fallback pattern: prefer `UpdateTaskStatusNode`'s output if it has already run
  this loop iteration, else fall back to `LoadTaskStateNode`'s initial load. Copy
  this pattern (`_latest_state_dict`) rather than inventing a new one if you add a
  node that also needs the live `SDLCState`.
