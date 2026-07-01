# Task Spec — OR.Z: SDLC Pipeline as Engine-Native Nodes & Workflows

**Status:** Not started · **Last run:** never

## Goal
Graduate the SDLC execution runtime (`sdlc-flow`/`sdlc-run`) from base-template JS engines into Engine-native Node/Workflow primitives — typed state, durable retries, live observability, and exact cost — driving Claude Code via the existing `CLAUDE_CODE_SDK`/`CLAUDE_CODE_SESSION` providers.

## Context Pointers
- **Block definition:** `planning/master-plan.md` → OR.Z (lines 690–763)
- **Architecture synthesis:** `planning/sdlc-workflow-architecture/synthesis.md` — the full design
- **Nodes design:** `planning/sdlc-workflow-architecture/nodes-design.md` — per-node detail
- **Standing rules:** `GEMINI.md` / `CLAUDE.md` — especially rules 1 (tests), 2 (no hardcoded prompts), 4 (new workflow directories), 6 (dual registry), 7 (no deployment logic in nodes), 9 (seed TaskContext correctly)
- **Existing primitives:** `app/core/nodes/` (Node, AgentNode, RouterNode, ParallelNode), `app/core/workflow.py` (Workflow, WorkflowSchema, node_context), `app/core/task.py` (TaskContext, NodeRun)
- **Provider seam:** `app/services/claude_code/` (ClaudeCodeModel, ClaudeAgentSdkBackend, BastionSessionBackend)
- **Harness config:** `planning/harness.json` — the validation suite TestTaskNode must execute
- **Hard prerequisite:** Project E (ParallelNode merge fix) must be complete before this block ships. If Project E is not done, tasks 1–8 can still be built and tested in isolation; only the wave fan-out in a future SDLCBlockWorkflow requires it.

## Out of Scope (per OR.Z block contract)
- **Auto-merge** — the human review gate stays (D25)
- **Replacing base-template's spec/command authoring surface** — only the execution runtime graduates
- **One-shot rewrite of the JS engines** — incremental parity instead
- **Self-healing trigger** (program Block N)
- **SDLCBlockWorkflow (wave fan-out via ParallelNode)** — depends on Project E; this spec builds the sequential SDLCFlowWorkflow only. The block-level fan-out is a follow-on spec once E ships.
- **CoverageScanNode** (synthesis §3 item 1) — coverage gap-check is a nice-to-have; defer to a hardening pass
- **UITestNode** — `harness.json` has `"uiTest": { "enabled": false }` for this repo

## Step-by-Step Tasks

### 1. SDLC Pydantic Schemas & State Model
Define the structured JSON task schema and Pydantic models that replace the markdown-based task parsing.

- Create `app/schemas/sdlc_schema.py` with:
  - `SDLCTask` model: `task_id: int`, `title: str`, `description: str`, `acceptance_criteria: list[str]`, `status: str` (enum: `pending | in_progress | done | failed | skipped`), `validation_commands: list[str]`, `attempt_count: int = 0`, `max_attempts: int = 3`
  - `SDLCFlowEventSchema` (the Pydantic event schema for the API): `spec_slug: str`, `task_range: str | None = None` (e.g. `"1-3,5"`), `resume: bool = False`, `auto_pr: bool = True`, `branch_name: str | None = None`
  - `SDLCState` model: `spec_slug: str`, `phase_id: str | None`, `block_id: str | None`, `global_status: str`, `tasks: list[SDLCTask]`, `telemetry: SDLCTelemetry`
  - `SDLCTelemetry` model: `total_attempts: int = 0`, `budget_spent: float = 0.0`, `tasks_passed: int = 0`, `tasks_failed: int = 0`
  - `SDLCTriageVerdict` enum: `PASS`, `RETRYABLE`, `MAJOR_BAIL`
  - `SDLCReviewVerdict` enum: `PASS`, `FAIL`, `PARTIAL`
- Write unit tests in `tests/schemas/test_sdlc_schema.py`: model construction, validation, status transitions, task_range parsing, round-trip serialization.

**Files:** `app/schemas/sdlc_schema.py` (new), `tests/schemas/test_sdlc_schema.py` (new)

### 2. SetupWorktreeNode — Git Worktree Isolation
Build the deterministic node that creates an isolated git worktree for SDLC execution.

- Create `app/workflows/sdlc_flow_workflow_nodes/__init__.py`
- Create `app/workflows/sdlc_flow_workflow_nodes/setup_worktree_node.py`:
  - Inherits from `Node` (deterministic, no LLM).
  - `process()`: computes `worktree_path = trees/{branch_name}`, runs `git worktree add`, optionally runs sparse-checkout if configured. Copies `.env` template if present. Stores `worktree_path` and `branch_name` in `TaskContext.data` via `update_node()`.
  - Handles `resume=True`: if the worktree already exists, reattach instead of creating.
  - Handles cleanup on failure (remove partial worktree).
- Write unit tests in `tests/workflows/sdlc_flow/test_setup_worktree_node.py`: happy path (mock subprocess), resume mode, failure cleanup, sparse-checkout config. Use `tmp_path` fixtures — never run real `git worktree` in CI.

**Files:** `app/workflows/sdlc_flow_workflow_nodes/__init__.py` (new), `app/workflows/sdlc_flow_workflow_nodes/setup_worktree_node.py` (new), `tests/workflows/sdlc_flow/__init__.py` (new), `tests/workflows/sdlc_flow/test_setup_worktree_node.py` (new)

### 3. LoadTaskStateNode & SaveStateNode — JSON State Persistence
Build the two deterministic nodes for reading/writing the structured SDLC state to disk.

- Create `app/workflows/sdlc_flow_workflow_nodes/load_task_state_node.py`:
  - Inherits from `Node`. Reads `planning/{spec_slug}/sdlc-flow-state.json` (or `tasks.json` for initial load). Deserializes into `SDLCState`. Filters tasks by `task_range` if provided. Stores in TaskContext via `update_node()`. If state file is absent, constructs initial state from the task list.
- Create `app/workflows/sdlc_flow_workflow_nodes/save_state_node.py`:
  - Inherits from `Node`. Serializes `SDLCState` from TaskContext to `planning/{spec_slug}/sdlc-flow-state.json`. Runs `git add` + `git commit -m "chore: flow state — {stage}"` via subprocess. No LLM.
- Write tests in `tests/workflows/sdlc_flow/test_state_nodes.py`: round-trip load→save, task_range filtering, initial-state construction, git-commit mock.

**Files:** `app/workflows/sdlc_flow_workflow_nodes/load_task_state_node.py` (new), `app/workflows/sdlc_flow_workflow_nodes/save_state_node.py` (new), `tests/workflows/sdlc_flow/test_state_nodes.py` (new)

### 4. TestTaskNode — Harness Executor
Build the deterministic node that runs `planning/harness.json` validation checks against a worktree.

- Create `app/workflows/sdlc_flow_workflow_nodes/test_task_node.py`:
  - Inherits from `Node`. Reads `planning/harness.json` (the checks array). For each check, dispatches by `kind`:
    - `command`: `subprocess.run(check["command"], cwd=worktree_path)`, captures stdout/stderr, checks exit code.
    - `baseline-diff`: captures output JSON, diffs against baseline snapshot, reports net-new failures only.
    - `count-delta`: regex-matches count pattern in stdout, compares to stored baseline, fails on configured `failOn` direction.
    - `warning-scan`: scans stdout/stderr for configured `warningPatterns`.
    - `forbidden-pattern-scan`: runs grep or Python equivalent against git diff for each rule.
  - Stores structured result in TaskContext: `all_passed: bool`, `check_results: list[CheckResult]` (per-check pass/fail + captured output), `failure_summary: str`.
- Write tests in `tests/workflows/sdlc_flow/test_test_task_node.py`: mock subprocess for each check kind, all-pass scenario, mixed-failure scenario, missing harness.json fallback.

**Files:** `app/workflows/sdlc_flow_workflow_nodes/test_task_node.py` (new), `tests/workflows/sdlc_flow/test_test_task_node.py` (new)

### 5. UpdateTaskStatusNode — State Mutation
Build the deterministic node that updates a single task's status in the SDLC state.

- Create `app/workflows/sdlc_flow_workflow_nodes/update_task_status_node.py`:
  - Inherits from `Node`. Reads `current_task_id` and `new_status` from TaskContext. Locates the matching `SDLCTask` in `SDLCState.tasks`, sets `task.status`, increments `attempt_count` if retrying, updates `SDLCTelemetry` counters.
  - Returns the mutated state via `update_node()`.
- Write tests in `tests/workflows/sdlc_flow/test_update_task_status_node.py`: status transitions (pending→done, pending→failed, retry increment), task-not-found error, telemetry counter correctness.

**Files:** `app/workflows/sdlc_flow_workflow_nodes/update_task_status_node.py` (new), `tests/workflows/sdlc_flow/test_update_task_status_node.py` (new)

### 6. ImplementTaskNode — Claude Code Coding Agent
Build the LLM-driven node that authors code modifications for a single SDLC task by dispatching to Claude Code via the existing provider seam.

- Create `app/workflows/sdlc_flow_workflow_nodes/implement_task_node.py`:
  - Inherits from `AgentNode`. Uses `ModelProvider.CLAUDE_CODE_SDK` (configurable per-node).
  - `process()`: reads `current_task` (an `SDLCTask`) and `worktree_path` from TaskContext. Builds a prompt from the task's `description`, `acceptance_criteria`, and optionally a breakdown checklist. Sets `cwd` to `worktree_path` for the Claude Code agent.
  - Captures modified files list and the agent's execution summary. Records token usage via the existing `AgentNode` telemetry path.
- Create prompt template `app/prompts/sdlc_implement_task.j2`: system prompt instructing Claude Code to implement the task, restrict edits to target files, write unit tests for new logic, and avoid touching out-of-scope files.
- Write tests in `tests/workflows/sdlc_flow/test_implement_task_node.py`: mock the agent/model, verify prompt construction from SDLCTask fields, verify TaskContext output structure, verify telemetry capture. Seed TaskContext per standing rule 9 (`{"result": ...}` envelope).

**Files:** `app/workflows/sdlc_flow_workflow_nodes/implement_task_node.py` (new), `app/prompts/sdlc_implement_task.j2` (new), `tests/workflows/sdlc_flow/test_implement_task_node.py` (new)

### 7. TriageTaskNode — Failure Classification Router
Build the router node that classifies test failures and routes to retry or bail.

- Create `app/workflows/sdlc_flow_workflow_nodes/triage_task_node.py`:
  - Inherits from `BaseRouter` and uses `RouterNode` pattern. Uses a mid-tier model (Sonnet) to classify test output.
  - Reads `TestTaskNode` output (failure logs) and `current_task.attempt_count` from TaskContext via `get_node_output()`.
  - Routes:
    - `RETRYABLE` → `ImplementTaskNode` (if `attempt_count < max_attempts` and failure is transient/fixable)
    - `MAJOR_BAIL` → `WrapUpNode` (if `attempt_count >= max_attempts`, or failure is structural: missing deps, ambiguous spec, infinite hang)
    - `PASS` → `ConsolidatedReviewNode`
  - Stores `SDLCTriageVerdict` in TaskContext.
- Create prompt template `app/prompts/sdlc_triage.j2`: instructs the model to classify test output into PASS / RETRYABLE / MAJOR_BAIL with a one-line reason.
- Write tests in `tests/workflows/sdlc_flow/test_triage_task_node.py`: mock agent for each verdict, verify routing decisions, verify max_attempts enforcement, verify TaskContext read via `get_node_output()`.

**Files:** `app/workflows/sdlc_flow_workflow_nodes/triage_task_node.py` (new), `app/prompts/sdlc_triage.j2` (new), `tests/workflows/sdlc_flow/test_triage_task_node.py` (new)

### 8. [x] ConsolidatedReviewNode, PatchDocsNode, WrapUpNode, PullRequestNode — Completion Nodes
Build the four nodes that handle post-implementation review, documentation, logging, and PR creation.

- Create `app/workflows/sdlc_flow_workflow_nodes/consolidated_review_node.py`:
  - Inherits from `AgentNode`. Uses frontier model (Sonnet/Opus). Reads the full git diff (via `git diff main..HEAD` in worktree). Checks diff against `acceptance_criteria` from the current task. Issues `SDLCReviewVerdict` (`PASS` / `FAIL` / `PARTIAL`). On `FAIL`/`PARTIAL` with minor issues → routes to `ImplementTaskNode`; on structural fail → routes to `WrapUpNode`.
- Create `app/workflows/sdlc_flow_workflow_nodes/patch_docs_node.py`:
  - Inherits from `AgentNode`. Reads modified files from TaskContext, searches `docs/` for references to changed symbols, patches doc files. Uses Sonnet-tier model.
- Create `app/workflows/sdlc_flow_workflow_nodes/wrap_up_node.py`:
  - Inherits from `AgentNode`. Edits `planning/status.md` (regex update of progress/timestamps), prepends a dated summary to `log.md`, generates a markdown report under `reports/`. Uses Sonnet-tier model.
- Create `app/workflows/sdlc_flow_workflow_nodes/pull_request_node.py`:
  - Inherits from `Node` (deterministic). Pushes branch to remote. Runs `gh pr create` via subprocess. Does NOT auto-merge (human review gate, D25). Stores PR URL in TaskContext.
- Create prompt templates: `app/prompts/sdlc_review.j2`, `app/prompts/sdlc_patch_docs.j2`, `app/prompts/sdlc_wrap_up.j2`.
- Write tests in `tests/workflows/sdlc_flow/test_completion_nodes.py`: mock agents for review/docs/wrap-up, mock subprocess for PR node, verify verdict routing, verify TaskContext structures.

**Files:** `app/workflows/sdlc_flow_workflow_nodes/consolidated_review_node.py` (new), `app/workflows/sdlc_flow_workflow_nodes/patch_docs_node.py` (new), `app/workflows/sdlc_flow_workflow_nodes/wrap_up_node.py` (new), `app/workflows/sdlc_flow_workflow_nodes/pull_request_node.py` (new), `app/prompts/sdlc_review.j2` (new), `app/prompts/sdlc_patch_docs.j2` (new), `app/prompts/sdlc_wrap_up.j2` (new), `tests/workflows/sdlc_flow/test_completion_nodes.py` (new)

### 9. SDLCFlowWorkflow — DAG Wiring & Registry
Wire all nodes into the `SDLCFlowWorkflow` with a complete `WorkflowSchema`, register in both registries, and write the integration test.

- Create `app/workflows/sdlc_flow_workflow.py`:
  - Define `SDLCFlowWorkflow(Workflow)` with `workflow_schema = WorkflowSchema(...)`.
  - DAG: `SetupWorktreeNode → LoadTaskStateNode → ImplementTaskNode → TestTaskNode → TriageTaskNode → {ConsolidatedReviewNode | ImplementTaskNode (retry) | WrapUpNode (bail)} → UpdateTaskStatusNode → SaveStateNode → (loop back for next task or) → PatchDocsNode → WrapUpNode → PullRequestNode`.
  - The task loop must be modeled: since the current `Workflow.run()` is a linear chain with routing, the loop-back to `ImplementTaskNode` for the next task is implemented via a `TaskQueueRouterNode` that checks if tasks remain.
- Create `app/workflows/sdlc_flow_workflow_nodes/task_queue_router_node.py`:
  - Inherits from `BaseRouter`. Checks `SDLCState.tasks` for the next pending task. If found, sets `current_task` in TaskContext and routes to `ImplementTaskNode`. If none remain, routes to `PatchDocsNode`.
- Register `SDLC_FLOW` in `app/workflows/workflow_registry.py` (enum member).
- Register `SDLCFlowEventSchema` in `app/api/schema_registry.py`.
- Write integration test in `tests/workflows/sdlc_flow/test_sdlc_flow_workflow.py`: E2E smoke test with all agents mocked, verifying DAG traversal order, retry loop (mock one task failing then passing), bail path, and final TaskContext state structure. Verify `WorkflowValidator` accepts the schema.

**Files:** `app/workflows/sdlc_flow_workflow.py` (new), `app/workflows/sdlc_flow_workflow_nodes/task_queue_router_node.py` (new), `app/workflows/workflow_registry.py` (modified — add enum), `app/api/schema_registry.py` (modified — add entry), `tests/workflows/sdlc_flow/test_sdlc_flow_workflow.py` (new)

### 10. Validate
- Run the Validation Commands listed below and confirm all pass.
- Verify the dual registry is complete (`tests/api/test_endpoint.py::TestSchemaRegistryCompleteness`).
- Verify the SDLCFlowWorkflow DAG passes `WorkflowValidator`.
- Confirm no regressions in existing workflows.
- Verify all new `.j2` prompts are loadable via `PromptManager`.

## Acceptance Criteria
- A structured `SDLCFlowEventSchema` is accepted by `POST /events/` and dispatches to the `SDLCFlowWorkflow`.
- The workflow DAG traverses: setup → load state → (task loop: implement → test → triage → review) → patch docs → wrap up → PR.
- `ImplementTaskNode` drives Claude Code via `CLAUDE_CODE_SDK` provider (or `CLAUDE_CODE_SESSION`), never writing code itself.
- `TriageTaskNode` routes `RETRYABLE` failures back to `ImplementTaskNode` (bounded by `max_attempts`), `MAJOR_BAIL` to `WrapUpNode`, and `PASS` to `ConsolidatedReviewNode`.
- `TestTaskNode` executes all check kinds from `harness.json` (command, baseline-diff, count-delta, warning-scan, forbidden-pattern-scan) and produces a structured pass/fail result.
- `PullRequestNode` creates a PR but does NOT auto-merge (human review gate, D25).
- The run is visible in `events` / `node_runs` (bastion can monitor it via the existing D20/D30 data contract).
- All system prompts are `.j2` files in `app/prompts/`, loaded via `PromptManager` — none hardcoded.
- Tests cover every new node + the DAG integration path (retry loop, bail path, happy path).
- The orchestrator gate holds: `uv run python -m pytest` passes, `ruff check app/` clean, `pylint app/` 10.00/10.

## Validation Commands
```
uv run python -m ruff check app/
uv run python -m pylint app/
uv run python -m pytest
```

## Notes
- **Project E (ParallelNode merge) is NOT in scope here.** This spec builds the sequential SDLCFlowWorkflow. A future SDLCBlockWorkflow will compose ParallelNode for wave fan-out once Project E ships.
- **Task loop modeling:** The current `Workflow.run()` engine supports linear chains + routing. The SDLC task loop (iterate over N tasks) requires a `TaskQueueRouterNode` to check the queue and loop back. If the `Workflow.run()` engine needs modification to support cycles (a node appearing multiple times in a traversal), that modification belongs in task 9 and should be minimal — e.g., allowing `_get_next_node_class` to revisit a node class. Alternatively, the task loop can be modeled within `ImplementTaskNode.process()` itself (process one task, let the outer routing handle the next). Evaluate both approaches.
- **The SDLC-spec contract doc** mentioned in OR.Z ("warrants a new shared SDLC-spec/harness contract doc between base-template and orchestrator") is documentation work that should be written as part of task 8's wrap-up or as a follow-on chore, not a separate implementation task.

## Amendment Log
<!-- Append-only. Pipeline stages append one dated line here when they deviate from the spec. -->
_No amendments yet._
