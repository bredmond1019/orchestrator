# Task Breakdown — OR.Z: SDLC Pipeline as Engine-Native Nodes & Workflows

## Source Spec
`planning/sdlc-workflow-architecture/tasks.md`

## Goal
Graduate the SDLC execution runtime (`sdlc-flow`/`sdlc-run`) from base-template JS engines into Engine-native Node/Workflow primitives — typed state, durable retries, live observability, and exact cost — driving Claude Code via the existing `CLAUDE_CODE_SDK`/`CLAUDE_CODE_SESSION` providers.

## How to Use
Work top to bottom. Each sub-step is a single atomic action. Run the inline **Verify**
checks as you go — do not batch them at the end. Each check must pass before continuing.

---

## Steps

### Step 1: SDLC Pydantic Schemas & State Model

#### 1.1 Create `app/schemas/sdlc_schema.py`
**File:** `app/schemas/sdlc_schema.py` (overwrite — the file exists but is 0 bytes)
**Action:** Create the complete SDLC schema module.

Module docstring on line 1 (before imports — standing rule).

**Imports:** `from enum import StrEnum`, `from pydantic import BaseModel, Field`

**Classes to define (in order):**

1. `SDLCTriageVerdict(StrEnum)` — members: `PASS = "pass"`, `RETRYABLE = "retryable"`, `MAJOR_BAIL = "major_bail"`
2. `SDLCReviewVerdict(StrEnum)` — members: `PASS = "pass"`, `FAIL = "fail"`, `PARTIAL = "partial"`
3. `SDLCTaskStatus(StrEnum)` — members: `PENDING = "pending"`, `IN_PROGRESS = "in_progress"`, `DONE = "done"`, `FAILED = "failed"`, `SKIPPED = "skipped"`
4. `SDLCTask(BaseModel)`:
   - `task_id: int`
   - `title: str`
   - `description: str`
   - `acceptance_criteria: list[str] = Field(default_factory=list)`
   - `status: SDLCTaskStatus = SDLCTaskStatus.PENDING`
   - `validation_commands: list[str] = Field(default_factory=list)`
   - `attempt_count: int = 0`
   - `max_attempts: int = 3`
5. `SDLCTelemetry(BaseModel)`:
   - `total_attempts: int = 0`
   - `budget_spent: float = 0.0`
   - `tasks_passed: int = 0`
   - `tasks_failed: int = 0`
6. `SDLCState(BaseModel)`:
   - `spec_slug: str`
   - `phase_id: str | None = None`
   - `block_id: str | None = None`
   - `global_status: str = "pending"`
   - `tasks: list[SDLCTask] = Field(default_factory=list)`
   - `telemetry: SDLCTelemetry = Field(default_factory=SDLCTelemetry)`
7. `SDLCFlowEventSchema(BaseModel)` — the API event schema (follows `ProposalGeneratorEventSchema` pattern):
   - `spec_slug: str = Field(..., description="Path slug under planning/ for the task spec")`
   - `task_range: str | None = Field(default=None, description="Optional task range filter, e.g. '1-3,5'")`
   - `resume: bool = Field(default=False, description="If True, reattach to existing worktree")`
   - `auto_pr: bool = Field(default=True, description="If True, open PR on completion")`
   - `branch_name: str | None = Field(default=None, description="Override branch name; defaults to sdlc/{spec_slug}")`

Add a module-level helper function:
- `def parse_task_range(task_range: str | None, tasks: list[SDLCTask]) -> list[SDLCTask]` — parses `"1-3,5"` into individual task_ids, returns the matching subset of tasks. Returns all tasks if `task_range is None`.

#### 1.2 Update `app/schemas/__init__.py`
**File:** `app/schemas/__init__.py`
**Action:** Add import + `__all__` entry.

Add line: `from app.schemas.sdlc_schema import SDLCFlowEventSchema`
Add `"SDLCFlowEventSchema"` to the `__all__` list.

#### 1.3 Create `tests/schemas/test_sdlc_schema.py`
**File:** `tests/schemas/test_sdlc_schema.py` (new)
**Action:** Create unit tests for all schema models.

**Imports:** `import pytest`, `from pydantic import ValidationError`, `from app.schemas.sdlc_schema import (SDLCTask, SDLCTaskStatus, SDLCTelemetry, SDLCState, SDLCFlowEventSchema, SDLCTriageVerdict, SDLCReviewVerdict, parse_task_range)`

**Test class `TestSDLCTask`:**
- `test_default_status_is_pending` — `SDLCTask(task_id=1, title="t", description="d").status == SDLCTaskStatus.PENDING`
- `test_default_attempt_count` — `assert task.attempt_count == 0`
- `test_default_max_attempts` — `assert task.max_attempts == 3`
- `test_missing_required_field_raises` — `pytest.raises(ValidationError)` on `SDLCTask()` (no args)
- `test_round_trip_serialization` — `model_dump()` → reconstruct → assert equality

**Test class `TestSDLCState`:**
- `test_construction_with_tasks` — build `SDLCState(spec_slug="test", tasks=[SDLCTask(...)])`, assert task list length
- `test_default_telemetry` — `assert state.telemetry.total_attempts == 0`
- `test_round_trip_serialization` — `model_dump()` → reconstruct → assert equality

**Test class `TestSDLCFlowEventSchema`:**
- `test_valid_schema` — `SDLCFlowEventSchema(spec_slug="my-spec")`, assert defaults
- `test_defaults` — `resume == False`, `auto_pr == True`, `task_range is None`, `branch_name is None`
- `test_missing_spec_slug_raises` — `pytest.raises(ValidationError)` on `SDLCFlowEventSchema()`

**Test class `TestParseTaskRange`:**
- `test_none_returns_all` — `parse_task_range(None, tasks)` returns all tasks
- `test_single_id` — `parse_task_range("2", tasks)` returns only task_id=2
- `test_range` — `parse_task_range("1-3", tasks)` returns tasks 1, 2, 3
- `test_mixed` — `parse_task_range("1,3-5", tasks)` returns tasks 1, 3, 4, 5
- `test_empty_string_returns_all` — `parse_task_range("", tasks)` returns all tasks

**Test class `TestEnums`:**
- `test_triage_verdict_values` — assert all 3 members exist
- `test_review_verdict_values` — assert all 3 members exist
- `test_task_status_values` — assert all 5 members exist

**Verify:** `uv run python -m pytest tests/schemas/test_sdlc_schema.py -v` → all pass

---

### Step 2: SetupWorktreeNode — Git Worktree Isolation

#### 2.1 Create `app/workflows/sdlc_flow_workflow_nodes/__init__.py`
**File:** `app/workflows/sdlc_flow_workflow_nodes/__init__.py` (new)
**Action:** Create with a single docstring line:
```python
"""Node package for the sdlc_flow workflow (OR.Z)."""
```
(Follows the empty-`__init__` pattern from `proposal_generator_workflow_nodes/__init__.py`.)

#### 2.2 Create `app/workflows/sdlc_flow_workflow_nodes/setup_worktree_node.py`
**File:** `app/workflows/sdlc_flow_workflow_nodes/setup_worktree_node.py` (new)
**Action:** Create the deterministic worktree setup node.

Module docstring on line 1.

**Imports:** `import logging`, `import shutil`, `import subprocess`, `from pathlib import Path`, `from core.nodes.base import Node`, `from core.task import TaskContext`

**Class `SetupWorktreeNode(Node)`:**
- `process(self, task_context: TaskContext) -> TaskContext`:
  1. Read `spec_slug`, `resume`, `branch_name` from `task_context.event` (the parsed `SDLCFlowEventSchema`).
  2. Compute `branch = branch_name or f"sdlc/{spec_slug}"`.
  3. Compute `worktree_path = Path("trees") / branch`.
  4. If `resume` and `worktree_path.exists()`: log reattach, skip creation.
  5. Else: run `subprocess.run(["git", "worktree", "add", str(worktree_path), "-b", branch, "origin/main"], capture_output=True, text=True, check=False, cwd=".")`. On non-zero returncode: attempt cleanup via `subprocess.run(["git", "worktree", "remove", ...])`, then `raise RuntimeError(f"git worktree add failed: {result.stderr}")`.
  6. Copy `.env` template if `Path("app/.env").exists()` and not `(worktree_path / "app" / ".env").exists()`.
  7. Store via `task_context.update_node(node_name=self.node_name, result={"worktree_path": str(worktree_path), "branch_name": branch})`.
  8. Return `task_context`.

Use `logging.info("msg: %s", value)` (not f-strings — standing rule).

#### 2.3 Create `tests/workflows/sdlc_flow/__init__.py`
**File:** `tests/workflows/sdlc_flow/__init__.py` (new)
**Action:** Empty file.

#### 2.4 Create `tests/workflows/sdlc_flow/test_setup_worktree_node.py`
**File:** `tests/workflows/sdlc_flow/test_setup_worktree_node.py` (new)
**Action:** Create unit tests.

**Imports:** `from unittest.mock import MagicMock, patch`, `import pytest`, `from core.task import NodeRun, NodeStatus, TaskContext`, `from schemas.sdlc_schema import SDLCFlowEventSchema`, `from workflows.sdlc_flow_workflow_nodes.setup_worktree_node import SetupWorktreeNode`

**Helper:**
```python
def _make_ctx(**overrides) -> TaskContext:
    defaults = {"spec_slug": "test-spec"}
    defaults.update(overrides)
    return TaskContext(event=SDLCFlowEventSchema(**defaults))
```

**Test class `TestSetupWorktreeNode`:**

- `test_happy_path_creates_worktree`:
  - `ctx = _make_ctx()`
  - `with patch("workflows.sdlc_flow_workflow_nodes.setup_worktree_node.subprocess.run") as mock_run, patch("workflows.sdlc_flow_workflow_nodes.setup_worktree_node.Path.exists", return_value=False):`
  - `mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")`
  - `node = SetupWorktreeNode()`
  - `result = node.process(ctx)`
  - `assert result is ctx`
  - `output = ctx.get_node_output("SetupWorktreeNode")`
  - `assert output["result"]["worktree_path"] == "trees/sdlc/test-spec"`
  - `assert output["result"]["branch_name"] == "sdlc/test-spec"`
  - `mock_run.assert_called_once()` — verify git command args

- `test_resume_skips_creation`:
  - `ctx = _make_ctx(resume=True)`
  - Patch `Path.exists` to return `True` for the worktree path
  - Verify `subprocess.run` is NOT called
  - Verify output still stored correctly

- `test_custom_branch_name`:
  - `ctx = _make_ctx(branch_name="my-branch")`
  - Verify `worktree_path` is `"trees/my-branch"` and `branch_name` is `"my-branch"`

- `test_failure_cleans_up`:
  - Mock `subprocess.run` with `returncode=1, stderr="error"`
  - `pytest.raises(RuntimeError, match="git worktree add failed")`

**Verify:** `uv run python -m pytest tests/workflows/sdlc_flow/test_setup_worktree_node.py -v` → all pass

---

### Step 3: LoadTaskStateNode & SaveStateNode — JSON State Persistence

#### 3.1 Create `app/workflows/sdlc_flow_workflow_nodes/load_task_state_node.py`
**File:** `app/workflows/sdlc_flow_workflow_nodes/load_task_state_node.py` (new)
**Action:** Create the state-loading node.

Module docstring on line 1.

**Imports:** `import json`, `import logging`, `from pathlib import Path`, `from core.nodes.base import Node`, `from core.task import TaskContext`, `from schemas.sdlc_schema import SDLCState, SDLCFlowEventSchema, parse_task_range`

**Class `LoadTaskStateNode(Node)`:**
- `process(self, task_context: TaskContext) -> TaskContext`:
  1. Read `spec_slug` and `task_range` from `task_context.event`.
  2. Read `worktree_path` from `task_context.get_node_output("SetupWorktreeNode")["result"]["worktree_path"]`.
  3. Compute `state_path = Path(worktree_path) / "planning" / spec_slug / "sdlc-flow-state.json"`.
  4. If `state_path.exists()`: read + parse as `SDLCState.model_validate_json(state_path.read_text(encoding="utf-8"))`.
  5. Else: check `tasks_path = Path(worktree_path) / "planning" / spec_slug / "tasks.json"`. If exists, read + construct `SDLCState(spec_slug=spec_slug, tasks=...)`.
  6. Else: raise `FileNotFoundError(f"No state or tasks file found for {spec_slug}")`.
  7. Apply `task_range` filter via `parse_task_range(task_range, state.tasks)` — replace `state.tasks` with the filtered list.
  8. Store via `task_context.update_node(node_name=self.node_name, result=state.model_dump())`.
  9. Return `task_context`.

Use `encoding="utf-8"` on all `open()`/`read_text()` calls (standing rule).

#### 3.2 Create `app/workflows/sdlc_flow_workflow_nodes/save_state_node.py`
**File:** `app/workflows/sdlc_flow_workflow_nodes/save_state_node.py` (new)
**Action:** Create the state-saving node.

Module docstring on line 1.

**Imports:** `import json`, `import logging`, `import subprocess`, `from pathlib import Path`, `from core.nodes.base import Node`, `from core.task import TaskContext`, `from schemas.sdlc_schema import SDLCState`

**Class `SaveStateNode(Node)`:**
- `process(self, task_context: TaskContext) -> TaskContext`:
  1. Read `worktree_path` from `task_context.get_node_output("SetupWorktreeNode")["result"]["worktree_path"]`.
  2. Read `state_dict` from the most recent state source in TaskContext. The state is updated by `UpdateTaskStatusNode`, so read from `task_context.get_node_output("UpdateTaskStatusNode")["result"]`. If that's not present (first run), read from `task_context.get_node_output("LoadTaskStateNode")["result"]`.
  3. Parse `state = SDLCState.model_validate(state_dict)`.
  4. Compute `state_path = Path(worktree_path) / "planning" / state.spec_slug / "sdlc-flow-state.json"`.
  5. `state_path.parent.mkdir(parents=True, exist_ok=True)`.
  6. `state_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")`.
  7. Run `subprocess.run(["git", "add", str(state_path)], cwd=worktree_path, capture_output=True, text=True, check=False)`.
  8. Run `subprocess.run(["git", "commit", "-m", "chore: flow state update"], cwd=worktree_path, capture_output=True, text=True, check=False)`.
  9. Store via `task_context.update_node(node_name=self.node_name, result={"saved_to": str(state_path)})`.
  10. Return `task_context`.

#### 3.3 Create `tests/workflows/sdlc_flow/test_state_nodes.py`
**File:** `tests/workflows/sdlc_flow/test_state_nodes.py` (new)
**Action:** Create unit tests for both nodes.

**Imports:** `import json`, `from unittest.mock import MagicMock, patch`, `import pytest`, `from core.task import TaskContext`, `from schemas.sdlc_schema import SDLCFlowEventSchema, SDLCState, SDLCTask, SDLCTaskStatus`, `from workflows.sdlc_flow_workflow_nodes.load_task_state_node import LoadTaskStateNode`, `from workflows.sdlc_flow_workflow_nodes.save_state_node import SaveStateNode`

**Helper:**
```python
def _make_state(n_tasks: int = 3) -> SDLCState:
    tasks = [SDLCTask(task_id=i, title=f"Task {i}", description=f"Desc {i}") for i in range(1, n_tasks + 1)]
    return SDLCState(spec_slug="test-spec", tasks=tasks)

def _make_ctx(state: SDLCState | None = None, **event_overrides) -> TaskContext:
    defaults = {"spec_slug": "test-spec"}
    defaults.update(event_overrides)
    ctx = TaskContext(event=SDLCFlowEventSchema(**defaults))
    # Seed SetupWorktreeNode output per rule 9
    ctx.nodes["SetupWorktreeNode"] = {"result": {"worktree_path": "/tmp/test-worktree", "branch_name": "sdlc/test-spec"}}
    return ctx
```

**Test class `TestLoadTaskStateNode`:**
- `test_loads_existing_state_file` — write a state JSON to `tmp_path`, patch `Path` resolution, assert parsed state
- `test_task_range_filtering` — pass `task_range="1,3"` in event, assert only tasks 1 and 3 are in result
- `test_missing_file_raises` — assert `FileNotFoundError` when neither state nor tasks file exists
- `test_initial_state_from_tasks_json` — provide only `tasks.json`, assert it constructs `SDLCState`

**Test class `TestSaveStateNode`:**
- `test_round_trip_save` — seed `LoadTaskStateNode` output (rule 9), run node, verify file written
- `test_git_commit_called` — patch `subprocess.run`, assert `git add` and `git commit` called

**Verify:** `uv run python -m pytest tests/workflows/sdlc_flow/test_state_nodes.py -v` → all pass

---

### Step 4: TestTaskNode — Harness Executor

#### 4.1 Create `app/workflows/sdlc_flow_workflow_nodes/test_task_node.py`
**File:** `app/workflows/sdlc_flow_workflow_nodes/test_task_node.py` (new)
**Action:** Create the harness check executor node.

Module docstring on line 1.

**Imports:** `import json`, `import logging`, `import re`, `import subprocess`, `from pathlib import Path`, `from pydantic import BaseModel`, `from core.nodes.base import Node`, `from core.task import TaskContext`

**Result models (defined in this module):**
```python
class CheckResult(BaseModel):
    name: str
    kind: str
    passed: bool
    output: str = ""
    message: str = ""

class TestTaskResult(BaseModel):
    all_passed: bool
    check_results: list[CheckResult]
    failure_summary: str = ""
```

**Class `TestTaskNode(Node)`:**
- `process(self, task_context: TaskContext) -> TaskContext`:
  1. Read `worktree_path` from `task_context.get_node_output("SetupWorktreeNode")["result"]["worktree_path"]`.
  2. Read `harness_path = Path(worktree_path) / "planning" / "harness.json"`.
  3. If not `harness_path.exists()`: store a result with `all_passed=True` (no harness = nothing to fail), return.
  4. Load harness: `harness = json.loads(harness_path.read_text(encoding="utf-8"))`.
  5. Extract `checks = harness.get("validation", {}).get("checks", [])`.
  6. Iterate checks. For each check, skip if `check.get("enabled") is False`. Dispatch by `kind`:

     - **`kind` is `None` or `"command"` (plain command):** Run `subprocess.run(check["command"], shell=True, cwd=worktree_path, capture_output=True, text=True, check=False)`. Pass if `returncode == 0`.

     - **`kind` is `"forbidden-pattern-scan"`:** For each rule in `check["rules"]`, run `subprocess.run(f"grep -rnE '{rule['pattern']}' {rule['paths']}", shell=True, cwd=worktree_path, ...)`. If matches found, check for `allowlistPattern` exclusion. Any unexcluded matches = fail.

     - **`kind` is `"baseline-diff"`:** Run `check["command"]`, parse JSON output. Compare to baseline (captured earlier or from `check["baselineCommand"]`). Extract only new entries not in baseline based on `check["compareKeys"]`. If new entries exist = fail.

     - **`kind` is `"count-delta"`:** Run `check["command"]`, regex-match `check["countPattern"]` on stdout. Extract count. Compare to stored baseline. If `check["failOn"] == "decrease"` and count dropped = fail.

     - **`kind` is `"warning-scan"`:** Run `check["command"]`, scan stdout+stderr for any of `check["warningPatterns"]`. If found = report warning (not fail if `gates == False`).

  7. Collect `CheckResult` per check. Compute `all_passed = all(cr.passed for cr in results if check_is_gating)`.
  8. Build `failure_summary` from failed checks.
  9. Store via `task_context.update_node(node_name=self.node_name, result=TestTaskResult(all_passed=all_passed, check_results=results, failure_summary=failure_summary).model_dump())`.
  10. Return `task_context`.

#### 4.2 Create `tests/workflows/sdlc_flow/test_test_task_node.py`
**File:** `tests/workflows/sdlc_flow/test_test_task_node.py` (new)
**Action:** Create unit tests.

**Imports:** `import json`, `from unittest.mock import MagicMock, patch, call`, `import pytest`, `from core.task import TaskContext`, `from schemas.sdlc_schema import SDLCFlowEventSchema`, `from workflows.sdlc_flow_workflow_nodes.test_task_node import TestTaskNode, CheckResult, TestTaskResult`

**Helper:** `_make_ctx()` seeding `SetupWorktreeNode` output (rule 9) and event.

**Test class `TestTestTaskNode`:**

- `test_all_checks_pass` — provide a minimal harness with two `command` checks, mock both subprocess calls returning `returncode=0`. Assert `all_passed is True`.

- `test_command_failure` — mock one command returning `returncode=1`. Assert `all_passed is False`, verify the specific `CheckResult.passed is False`.

- `test_forbidden_pattern_scan_catches_violation` — provide a harness with a `forbidden-pattern-scan` check. Mock grep finding matches. Assert check fails.

- `test_forbidden_pattern_scan_allowlist_passes` — same but with `allowlistPattern` matching. Assert check passes.

- `test_count_delta_decrease_fails` — provide `count-delta` check. Mock command output with a decreased count vs baseline. Assert check fails.

- `test_count_delta_increase_passes` — same but count increases. Assert check passes.

- `test_missing_harness_defaults_pass` — don't create `harness.json`. Assert `all_passed is True`.

- `test_disabled_check_skipped` — include a check with `"enabled": false`. Assert it does not appear in `check_results`.

- `test_warning_scan_non_gating` — check with `"gates": false` that has warnings. Assert `all_passed` is still True (non-gating).

**Verify:** `uv run python -m pytest tests/workflows/sdlc_flow/test_test_task_node.py -v` → all pass

---

### Step 5: UpdateTaskStatusNode — State Mutation

#### 5.1 Create `app/workflows/sdlc_flow_workflow_nodes/update_task_status_node.py`
**File:** `app/workflows/sdlc_flow_workflow_nodes/update_task_status_node.py` (new)
**Action:** Create the state mutation node.

Module docstring on line 1.

**Imports:** `import logging`, `from core.nodes.base import Node`, `from core.task import TaskContext`, `from schemas.sdlc_schema import SDLCState, SDLCTaskStatus`

**Class `UpdateTaskStatusNode(Node)`:**
- `process(self, task_context: TaskContext) -> TaskContext`:
  1. Read `current_task_id` from `task_context.get_node_output("TaskQueueRouterNode")["result"]["current_task_id"]`.
  2. Read `new_status` from triage/review verdict: check `TriageTaskNode` output for the verdict. If `PASS` and review passed → `SDLCTaskStatus.DONE`. If `MAJOR_BAIL` or review structural fail → `SDLCTaskStatus.FAILED`. If `RETRYABLE` → no status change (loop handles retry).
  3. Read current `state_dict` from the latest state source. First check `UpdateTaskStatusNode` (from previous loop iteration), then fall back to `LoadTaskStateNode`.
  4. Parse `state = SDLCState.model_validate(state_dict)`.
  5. Find the matching task by `task_id`. Set `task.status = new_status`.
  6. If retrying: increment `task.attempt_count`.
  7. Update `state.telemetry`: increment `tasks_passed` or `tasks_failed` as appropriate, increment `total_attempts`.
  8. Store via `task_context.update_node(node_name=self.node_name, result=state.model_dump())`.
  9. Return `task_context`.

#### 5.2 Create `tests/workflows/sdlc_flow/test_update_task_status_node.py`
**File:** `tests/workflows/sdlc_flow/test_update_task_status_node.py` (new)
**Action:** Create unit tests.

**Test class `TestUpdateTaskStatusNode`:**
- `test_status_pending_to_done` — seed triage as PASS, assert `task.status == "done"`, `telemetry.tasks_passed == 1`
- `test_status_pending_to_failed` — seed triage as MAJOR_BAIL, assert `task.status == "failed"`, `telemetry.tasks_failed == 1`
- `test_attempt_count_incremented` — seed triage as RETRYABLE, assert `task.attempt_count` incremented, `telemetry.total_attempts` incremented
- `test_task_not_found_raises` — seed a `current_task_id` that doesn't exist, assert `ValueError` raised
- `test_telemetry_counters_correct` — run multiple updates, verify cumulative telemetry

**Verify:** `uv run python -m pytest tests/workflows/sdlc_flow/test_update_task_status_node.py -v` → all pass

---

### Step 6: ImplementTaskNode — Claude Code Coding Agent

#### 6.1 Create `app/prompts/sdlc_implement_task.j2`
**File:** `app/prompts/sdlc_implement_task.j2` (new)
**Action:** Create the Jinja2 prompt template.

Follow the existing pattern (YAML frontmatter + body):
```
---
description: System prompt for ImplementTaskNode — instructs Claude Code to implement a single SDLC task.
author: Brandon Redmond
---

You are an expert software engineer implementing a single task in a codebase.

## Task
Title: {{ task_title }}
Description: {{ task_description }}

## Acceptance Criteria
{% for criterion in acceptance_criteria %}
- {{ criterion }}
{% endfor %}

{% if breakdown_steps %}
## Breakdown Steps
{% for step in breakdown_steps %}
- {{ step }}
{% endfor %}
{% endif %}

## Rules
- Implement ONLY what the task requires — do not touch unrelated files.
- Write unit tests for any new logic you add.
- Follow the project's code style (check CLAUDE.md / GEMINI.md for conventions).
- Do not hardcode system prompts in Python — use .j2 templates in app/prompts/.
- Use Python 3.10+ type syntax (list[T], X | None, StrEnum).
- Module docstrings go on line 1, before imports.
```

#### 6.2 Create `app/workflows/sdlc_flow_workflow_nodes/implement_task_node.py`
**File:** `app/workflows/sdlc_flow_workflow_nodes/implement_task_node.py` (new)
**Action:** Create the LLM-driven coding agent node.

Module docstring on line 1.

**Imports:** `import json`, `import logging`, `from core.nodes.agent import AgentConfig, AgentNode, ModelProvider`, `from core.task import TaskContext`, `from services.prompt_loader import PromptManager`

**Inner class `OutputType(AgentNode.OutputType)`:**
- `summary: str` — description of what was implemented
- `modified_files: list[str]` — list of file paths modified
- `tests_added: list[str]` — list of test files added/modified

**Class `ImplementTaskNode(AgentNode)`:**

- `def get_agent_config(self) -> AgentConfig`:
  ```python
  return AgentConfig(
      system_prompt=PromptManager.get_prompt("sdlc_implement_task",
          task_title="",  # placeholder — real values in user prompt
          task_description="",
          acceptance_criteria=[],
      ),
      output_type=self.OutputType,
      deps_type=None,
      model_provider=ModelProvider.CLAUDE_CODE_SDK,
      model_name="sonnet",
  )
  ```

- `def process(self, task_context: TaskContext) -> TaskContext`:
  1. Read `current_task` from `task_context.get_node_output("TaskQueueRouterNode")["result"]`.
  2. Read `worktree_path` from `task_context.get_node_output("SetupWorktreeNode")["result"]["worktree_path"]`.
  3. Build user prompt as JSON containing: `task_title`, `task_description`, `acceptance_criteria`, `worktree_path`.
  4. Override `self.agent`'s system prompt with the rendered template: `PromptManager.get_prompt("sdlc_implement_task", task_title=current_task["title"], ...)`.
  5. Call `result = self.run_agent_recorded(task_context, user_prompt)`.
  6. Store via `task_context.update_node(node_name=self.node_name, result={"summary": ..., "modified_files": ..., "tests_added": ...})`.
  7. Return `task_context`.

#### 6.3 Create `tests/workflows/sdlc_flow/test_implement_task_node.py`
**File:** `tests/workflows/sdlc_flow/test_implement_task_node.py` (new)
**Action:** Create unit tests following the `test_proposal_writer_node.py` pattern.

**Imports:** `from unittest.mock import MagicMock, patch`, `import pytest`, `from core.nodes.agent import AgentNode`, `from core.task import NodeRun, NodeStatus, TaskContext`, `from schemas.sdlc_schema import SDLCFlowEventSchema`, `from workflows.sdlc_flow_workflow_nodes.implement_task_node import ImplementTaskNode`

**Helper — bypass `AgentNode.__init__`:**
```python
def _make_node() -> ImplementTaskNode:
    node = ImplementTaskNode.__new__(ImplementTaskNode)
    node.agent = MagicMock()
    return node

def _result_for(output) -> MagicMock:
    r = MagicMock()
    r.output = output
    r.usage.return_value = MagicMock(input_tokens=100, output_tokens=50)
    return r
```

**Helper — seed TaskContext per rule 9:**
```python
def _make_ctx() -> TaskContext:
    ctx = TaskContext(event=SDLCFlowEventSchema(spec_slug="test-spec"))
    ctx.nodes["SetupWorktreeNode"] = {"result": {"worktree_path": "/tmp/wt", "branch_name": "sdlc/test"}}
    ctx.nodes["TaskQueueRouterNode"] = {"result": {"current_task_id": 1, "title": "Implement JWT", "description": "Add JWT middleware", "acceptance_criteria": ["Validates tokens"]}}
    ctx.node_runs["ImplementTaskNode"] = NodeRun(status=NodeStatus.RUNNING)
    return ctx
```

**Test class `TestImplementTaskNode`:**
- `test_process_calls_agent` — mock agent, verify `node.agent.run_sync` called once
- `test_prompt_contains_task_fields` — capture the user_prompt passed to `run_sync`, assert it contains task title and acceptance criteria
- `test_output_stored_with_result_key` — verify `ctx.get_node_output("ImplementTaskNode")["result"]` has `summary`, `modified_files`
- `test_returns_task_context` — `assert result is ctx`

**Verify:** `uv run python -m pytest tests/workflows/sdlc_flow/test_implement_task_node.py -v` → all pass

---

### Step 7: TriageTaskNode — Failure Classification Router

#### 7.1 Create `app/prompts/sdlc_triage.j2`
**File:** `app/prompts/sdlc_triage.j2` (new)
**Action:** Create the triage classification prompt.

```
---
description: System prompt for TriageTaskNode — classifies test failures into PASS / RETRYABLE / MAJOR_BAIL.
author: Brandon Redmond
---

You are a build triage specialist. Given the test/lint output below, classify the result.

## Test Output
{{ failure_summary }}

## Task
{{ task_title }} (attempt {{ attempt_count }} of {{ max_attempts }})

## Classify as ONE of:
- PASS — all checks passed, no action needed.
- RETRYABLE — fixable issues (syntax errors, failing unit tests, type mismatches). The coding agent can fix these on another attempt.
- MAJOR_BAIL — structural failures (missing dependencies not in spec, infinite hang, ambiguous spec, environment misconfiguration) OR max attempts reached. Stop trying.

Respond with exactly one word: PASS, RETRYABLE, or MAJOR_BAIL.
Then on the next line, a one-sentence reason.
```

#### 7.2 Create `app/workflows/sdlc_flow_workflow_nodes/triage_task_node.py`
**File:** `app/workflows/sdlc_flow_workflow_nodes/triage_task_node.py` (new)
**Action:** Create the triage router node.

Module docstring on line 1.

**Imports:** `import logging`, `from core.nodes.base import Node`, `from core.nodes.router import BaseRouter, RouterNode`, `from core.task import TaskContext`, `from schemas.sdlc_schema import SDLCTriageVerdict`, `from services.prompt_loader import PromptManager`

Import the target node classes (forward references to avoid import cycles — use local imports inside `determine_next_node` if needed):

**Class `TriageTaskRouterNode(BaseRouter)`:**
- `def __init__(self):` — `self.routes = [_TriageVerdictRouter()]`, `self.fallback = None`

**Class `_TriageVerdictRouter(RouterNode)`:**
- `def determine_next_node(self, task_context: TaskContext) -> Node | None`:
  1. Read `test_result = task_context.get_node_output("TestTaskNode")["result"]`.
  2. If `test_result["all_passed"]`: return `ConsolidatedReviewNode()` (import locally).
  3. Read current task's `attempt_count` and `max_attempts` from `TaskQueueRouterNode` output.
  4. If `attempt_count >= max_attempts`: return `WrapUpNode()` (import locally). This is automatic MAJOR_BAIL.
  5. Otherwise, classify via the triage verdict. For the deterministic router version: parse the `failure_summary` — if it contains structural error indicators, return `WrapUpNode()`. Otherwise return `ImplementTaskNode()` (retry).
  6. Store verdict in `task_context.update_node("TriageTaskRouterNode", result={"verdict": verdict.value, "reason": reason})`.

**Note on the LLM triage decision:** The spec says "Uses a mid-tier model (Sonnet) to classify." However, the `BaseRouter`/`RouterNode` pattern in this codebase is deterministic routing — the router's `determine_next_node` returns a node instance, not an LLM response. There are two approaches:
  - (A) Make the triage an `AgentNode` that stores the verdict, then a separate lightweight router reads it. This adds a node but cleanly separates concerns.
  - (B) Make `_TriageVerdictRouter.determine_next_node` call the LLM directly (via `PromptManager` + an inline agent call). This breaks the pattern slightly.

**Recommended: Approach A.** Create `TriageTaskNode(AgentNode)` that produces the verdict, and `TriageRouterNode(BaseRouter)` that reads the verdict and routes. This matches the `ProposalReviewNode` → `ProposalReviewRouterNode` pattern already in the codebase.

So the actual implementation is:

**Class `TriageTaskNode(AgentNode)`:**
- `OutputType` inner class: `verdict: str`, `reason: str`
- `get_agent_config` returns `AgentConfig(system_prompt=PromptManager.get_prompt("sdlc_triage", ...), output_type=self.OutputType, model_provider=ModelProvider.ANTHROPIC, model_name="claude-sonnet-4-20250514")`
- `process` reads `TestTaskNode` output and current task info, calls `run_agent_recorded`, stores verdict

**Class `TriageRouterNode(BaseRouter)`:**
- `def __init__(self):` — `self.routes = [_TriageVerdictRouter()]`, `self.fallback = None`

**Class `_TriageVerdictRouter(RouterNode)`:**
- `determine_next_node`: reads `TriageTaskNode` output verdict. `PASS` → `ConsolidatedReviewNode()`. `RETRYABLE` → `ImplementTaskNode()`. `MAJOR_BAIL` → `WrapUpNode()`.

#### 7.3 Create `tests/workflows/sdlc_flow/test_triage_task_node.py`
**File:** `tests/workflows/sdlc_flow/test_triage_task_node.py` (new)
**Action:** Create unit tests following the `test_proposal_review_router.py` pattern.

**Test class `TestTriageTaskNode`:** (AgentNode tests)
- `test_pass_verdict` — mock agent returning `{"verdict": "pass", "reason": "all good"}`, verify output stored
- `test_retryable_verdict` — mock agent returning retryable, verify output

**Test class `TestTriageRouterNode`:** (Router tests)
- `test_routes_to_review_on_pass` — seed `TriageTaskNode` output with `verdict="pass"`. Call `_TriageVerdictRouter().determine_next_node(ctx)`. Assert `isinstance(result, ConsolidatedReviewNode)`.
- `test_routes_to_implement_on_retryable` — seed with `verdict="retryable"`. Assert `isinstance(result, ImplementTaskNode)`.
- `test_routes_to_wrapup_on_major_bail` — seed with `verdict="major_bail"`. Assert `isinstance(result, WrapUpNode)`.
- `test_max_attempts_forces_bail` — seed with `attempt_count >= max_attempts`, assert routes to `WrapUpNode` regardless of verdict.
- `test_router_process_records_next_node` — call `router.process(ctx)`, verify `ctx.nodes["TriageRouterNode"]["next_node"]` set correctly.

**Verify:** `uv run python -m pytest tests/workflows/sdlc_flow/test_triage_task_node.py -v` → all pass

---

### Step 8: ConsolidatedReviewNode, PatchDocsNode, WrapUpNode, PullRequestNode — Completion Nodes

#### 8.1 Create `app/prompts/sdlc_review.j2`
**File:** `app/prompts/sdlc_review.j2` (new)
**Action:** Create the review prompt template.

```
---
description: System prompt for ConsolidatedReviewNode — reviews git diff against acceptance criteria.
author: Brandon Redmond
---

You are a senior code reviewer. Review the following git diff against the acceptance criteria.

## Acceptance Criteria
{% for criterion in acceptance_criteria %}
- {{ criterion }}
{% endfor %}

## Git Diff
{{ git_diff }}

## Instructions
Evaluate whether the diff satisfies ALL acceptance criteria.

Respond with:
- verdict: PASS, FAIL, or PARTIAL
- summary: one paragraph explaining your decision
- issues: list of specific issues found (empty if PASS)
```

#### 8.2 Create `app/prompts/sdlc_patch_docs.j2`
**File:** `app/prompts/sdlc_patch_docs.j2` (new)
**Action:** Create the docs patching prompt template.

```
---
description: System prompt for PatchDocsNode — updates documentation for changed symbols.
author: Brandon Redmond
---

You are a documentation specialist. Given the list of modified files and the docs directory contents, update any documentation that references changed symbols.

## Modified Files
{% for file in modified_files %}
- {{ file }}
{% endfor %}

## Instructions
- Search docs/ for references to changed functions, classes, or modules.
- Update stale references to match the new code.
- Do not add new documentation sections — only patch existing references.
- If no docs need updating, say "No documentation changes needed."
```

#### 8.3 Create `app/prompts/sdlc_wrap_up.j2`
**File:** `app/prompts/sdlc_wrap_up.j2` (new)
**Action:** Create the wrap-up prompt template.

```
---
description: System prompt for WrapUpNode — generates status updates, log entries, and reports.
author: Brandon Redmond
---

You are a project scribe. Summarize the completed SDLC run and produce three outputs.

## Run Summary
Spec: {{ spec_slug }}
Tasks completed: {{ tasks_passed }}
Tasks failed: {{ tasks_failed }}
Total attempts: {{ total_attempts }}

## Instructions
1. Write a dated summary entry for log.md (prepend to file).
2. Write a short markdown report suitable for planning/{{ spec_slug }}/reports/.
3. Suggest the status.md update (which block/project to mark done or in progress).
```

#### 8.4 Create `app/workflows/sdlc_flow_workflow_nodes/consolidated_review_node.py`
**File:** `app/workflows/sdlc_flow_workflow_nodes/consolidated_review_node.py` (new)
**Action:** Create the review agent node.

Module docstring on line 1.

**Class `ConsolidatedReviewNode(AgentNode)`:**
- `OutputType` inner class: `verdict: str`, `summary: str`, `issues: list[str] = []`
- `get_agent_config`: `model_provider=ModelProvider.ANTHROPIC`, `model_name="claude-sonnet-4-20250514"`, prompt loaded via `PromptManager.get_prompt("sdlc_review", ...)`
- `process`:
  1. Read `worktree_path` from `SetupWorktreeNode` output.
  2. Run `subprocess.run(["git", "diff", "main..HEAD"], cwd=worktree_path, ...)` to get the diff.
  3. Read `acceptance_criteria` from current task.
  4. Build user prompt with diff + criteria.
  5. Call `self.run_agent_recorded(task_context, user_prompt)`.
  6. Store verdict via `task_context.update_node(node_name=self.node_name, result=output)`.
  7. Return `task_context`.

#### 8.5 Create `app/workflows/sdlc_flow_workflow_nodes/review_router_node.py`
**File:** `app/workflows/sdlc_flow_workflow_nodes/review_router_node.py` (new)
**Action:** Create the review verdict router. (Follows the same pattern as step 7's `TriageRouterNode`.)

**Class `ReviewRouterNode(BaseRouter)`:**
- `__init__`: `self.routes = [_ReviewVerdictRouter()]`, `self.fallback = None`

**Class `_ReviewVerdictRouter(RouterNode)`:**
- `determine_next_node`:
  - Read `ConsolidatedReviewNode` output verdict.
  - `PASS` → `UpdateTaskStatusNode()`.
  - `FAIL`/`PARTIAL` with minor issues → `ImplementTaskNode()` (re-implement).
  - `FAIL` structural → `WrapUpNode()`.

#### 8.6 Create `app/workflows/sdlc_flow_workflow_nodes/patch_docs_node.py`
**File:** `app/workflows/sdlc_flow_workflow_nodes/patch_docs_node.py` (new)
**Action:** Create the docs patching node.

**Class `PatchDocsNode(AgentNode)`:**
- `OutputType`: `summary: str`, `files_patched: list[str] = []`
- `get_agent_config`: `model_provider=ModelProvider.ANTHROPIC`, `model_name="claude-sonnet-4-20250514"`, prompt via `PromptManager.get_prompt("sdlc_patch_docs", ...)`
- `process`: collect all modified files from `ImplementTaskNode` outputs across the run, build prompt, run agent, store result.

#### 8.7 Create `app/workflows/sdlc_flow_workflow_nodes/wrap_up_node.py`
**File:** `app/workflows/sdlc_flow_workflow_nodes/wrap_up_node.py` (new)
**Action:** Create the wrap-up node.

**Class `WrapUpNode(AgentNode)`:**
- `OutputType`: `log_entry: str`, `report: str`, `status_suggestion: str`
- `get_agent_config`: `model_provider=ModelProvider.ANTHROPIC`, `model_name="claude-sonnet-4-20250514"`, prompt via `PromptManager.get_prompt("sdlc_wrap_up", ...)`
- `process`: read `SDLCState` telemetry + completed tasks, build prompt, run agent, store result.

#### 8.8 Create `app/workflows/sdlc_flow_workflow_nodes/pull_request_node.py`
**File:** `app/workflows/sdlc_flow_workflow_nodes/pull_request_node.py` (new)
**Action:** Create the PR creation node (deterministic, no LLM).

**Class `PullRequestNode(Node)`:**
- `process`:
  1. Read `worktree_path` and `branch_name` from `SetupWorktreeNode` output.
  2. Read `auto_pr` from `task_context.event`.
  3. If not `auto_pr`: store `{"pr_url": None, "skipped": True}`, return.
  4. Run `subprocess.run(["git", "push", "origin", branch_name], cwd=worktree_path, ...)`.
  5. Run `subprocess.run(["gh", "pr", "create", "--base", "main", "--head", branch_name, "--title", f"SDLC: {spec_slug}", "--body", "Auto-generated PR — human review required."], cwd=worktree_path, ...)`.
  6. Parse PR URL from stdout.
  7. **Does NOT auto-merge** (human review gate, D25).
  8. Store via `task_context.update_node(node_name=self.node_name, result={"pr_url": pr_url})`.

#### 8.9 Create `tests/workflows/sdlc_flow/test_completion_nodes.py`
**File:** `tests/workflows/sdlc_flow/test_completion_nodes.py` (new)
**Action:** Create tests for all four completion nodes.

**Test class `TestConsolidatedReviewNode`:**
- `test_pass_verdict` — mock agent returning `{"verdict": "pass", ...}`, verify output
- `test_fail_verdict` — mock agent returning `{"verdict": "fail", ...}`, verify output
- `test_reads_git_diff` — mock `subprocess.run` for git diff, verify diff passed to prompt

**Test class `TestReviewRouterNode`:**
- `test_routes_to_update_on_pass` — seed review output with `verdict="pass"`, assert routes to `UpdateTaskStatusNode`
- `test_routes_to_implement_on_fail` — seed with `verdict="fail"`, assert routes to `ImplementTaskNode`
- `test_routes_to_wrapup_on_structural_fail` — seed appropriately, assert routes to `WrapUpNode`

**Test class `TestPatchDocsNode`:**
- `test_produces_summary` — mock agent, verify output has `summary` and `files_patched`

**Test class `TestWrapUpNode`:**
- `test_produces_log_entry_and_report` — mock agent, verify output has `log_entry`, `report`, `status_suggestion`

**Test class `TestPullRequestNode`:**
- `test_happy_path_creates_pr` — mock subprocess for `git push` and `gh pr create`, verify PR URL stored
- `test_auto_pr_false_skips` — set `auto_pr=False` in event, verify subprocess NOT called, `skipped=True`
- `test_no_auto_merge` — verify `gh pr merge` is never called (D25 guard)

**Verify:** `uv run python -m pytest tests/workflows/sdlc_flow/test_completion_nodes.py -v` → all pass

---

### Step 9: SDLCFlowWorkflow — DAG Wiring & Registry

#### 9.1 Create `app/workflows/sdlc_flow_workflow_nodes/task_queue_router_node.py`
**File:** `app/workflows/sdlc_flow_workflow_nodes/task_queue_router_node.py` (new)
**Action:** Create the task queue iterator router.

Module docstring on line 1.

**Class `TaskQueueRouterNode(BaseRouter)`:**
- `def __init__(self):` — `self.routes = [_TaskQueueRouter()]`, `self.fallback = None`

**Class `_TaskQueueRouter(RouterNode)`:**
- `determine_next_node(self, task_context: TaskContext) -> Node | None`:
  1. Read state from `LoadTaskStateNode` or latest `UpdateTaskStatusNode` output.
  2. Parse `SDLCState.model_validate(state_dict)`.
  3. Find the first task with `status == SDLCTaskStatus.PENDING`.
  4. If found: store the current task info in `task_context.update_node("TaskQueueRouterNode", result={"current_task_id": task.task_id, "title": task.title, "description": task.description, "acceptance_criteria": task.acceptance_criteria, "attempt_count": task.attempt_count, "max_attempts": task.max_attempts})`. Return `ImplementTaskNode()`.
  5. If no pending tasks remain: return `PatchDocsNode()`.

#### 9.2 Create `app/workflows/sdlc_flow_workflow.py`
**File:** `app/workflows/sdlc_flow_workflow.py` (new)
**Action:** Wire the complete DAG.

Module docstring on line 1.

**Imports:** All node classes from `workflows.sdlc_flow_workflow_nodes.*`, plus `core.schema.NodeConfig`, `core.schema.WorkflowSchema`, `core.workflow.Workflow`, `schemas.sdlc_schema.SDLCFlowEventSchema`.

**Class `SDLCFlowWorkflow(Workflow)`:**
```python
workflow_schema = WorkflowSchema(
    description="SDLC pipeline: setup → load state → task loop (implement → test → triage → review) → patch docs → wrap up → PR.",
    event_schema=SDLCFlowEventSchema,
    start=SetupWorktreeNode,
    nodes=[
        NodeConfig(node=SetupWorktreeNode, connections=[LoadTaskStateNode]),
        NodeConfig(node=LoadTaskStateNode, connections=[TaskQueueRouterNode]),

        # Task queue router — checks for pending tasks
        NodeConfig(node=TaskQueueRouterNode, connections=[ImplementTaskNode, PatchDocsNode], is_router=True),

        # Task execution loop (linear chain within the loop)
        NodeConfig(node=ImplementTaskNode, connections=[TestTaskNode]),
        NodeConfig(node=TestTaskNode, connections=[TriageTaskNode]),
        NodeConfig(node=TriageTaskNode, connections=[TriageRouterNode]),

        # Triage routing — PASS/RETRYABLE/MAJOR_BAIL
        # Note: connections list only FORWARD targets; retry back-edge to
        # ImplementTaskNode is expressed at runtime by _TriageVerdictRouter,
        # not in declared connections, so WorkflowValidator won't see a cycle.
        NodeConfig(node=TriageRouterNode, connections=[ConsolidatedReviewNode, WrapUpNode, ImplementTaskNode], is_router=True),

        # Review
        NodeConfig(node=ConsolidatedReviewNode, connections=[ReviewRouterNode]),
        NodeConfig(node=ReviewRouterNode, connections=[UpdateTaskStatusNode, ImplementTaskNode, WrapUpNode], is_router=True),

        # Post-task
        NodeConfig(node=UpdateTaskStatusNode, connections=[SaveStateNode]),
        NodeConfig(node=SaveStateNode, connections=[TaskQueueRouterNode]),

        # Completion (after all tasks)
        NodeConfig(node=PatchDocsNode, connections=[WrapUpNode]),
        NodeConfig(node=WrapUpNode, connections=[PullRequestNode]),
        NodeConfig(node=PullRequestNode, connections=[]),
    ],
)
```

**Critical DAG design notes:**
- The `WorkflowValidator._has_cycle` DFS follows `connections` edges. Including `ImplementTaskNode` in `TriageRouterNode.connections` creates the path `TriageRouterNode → ImplementTaskNode → TestTaskNode → TriageTaskNode → TriageRouterNode` which IS a cycle and **will fail validation**.
- **Fix:** Remove `ImplementTaskNode` from `TriageRouterNode.connections` and `ReviewRouterNode.connections`. The retry back-edges are runtime-only (via `determine_next_node` returning `ImplementTaskNode()`). The `_handle_router` method in `Workflow.run()` uses `router.route()` — not `connections` — to determine the next node at runtime. The validator's reachability check treats all router nodes as potentially reaching any node, so `ImplementTaskNode` will still be marked reachable.
- Similarly, remove `ImplementTaskNode` from `ReviewRouterNode.connections`.
- Also: `SaveStateNode → TaskQueueRouterNode` creates a cycle (`TaskQueueRouterNode → ImplementTaskNode → ... → SaveStateNode → TaskQueueRouterNode`). **Fix:** Remove `TaskQueueRouterNode` from `SaveStateNode.connections`. The loop-back is handled at runtime by the `_TaskQueueRouter` returning either `ImplementTaskNode()` or `PatchDocsNode()`. After `SaveStateNode`, the runtime router runs `TaskQueueRouterNode.route()` to pick the next iteration. To make this work, `SaveStateNode` should connect to `TaskQueueRouterNode` but this creates a cycle... 

**Revised approach — model the task loop differently:** Since the DAG validator rejects cycles, and the task loop IS fundamentally cyclic, the cleanest solution is: `SaveStateNode.connections = [TaskQueueRouterNode]` but suppress the cycle by **not declaring the `TaskQueueRouterNode → ImplementTaskNode` connection** (it's a runtime router decision). The validator's cycle check follows declared connections only.

**Revised `connections` (cycle-free declared graph):**
```python
NodeConfig(node=SetupWorktreeNode, connections=[LoadTaskStateNode]),
NodeConfig(node=LoadTaskStateNode, connections=[TaskQueueRouterNode]),
NodeConfig(node=TaskQueueRouterNode, connections=[PatchDocsNode], is_router=True),
    # Runtime: also routes to ImplementTaskNode, but not declared (avoids cycle)
NodeConfig(node=ImplementTaskNode, connections=[TestTaskNode]),
NodeConfig(node=TestTaskNode, connections=[TriageTaskNode]),
NodeConfig(node=TriageTaskNode, connections=[TriageRouterNode]),
NodeConfig(node=TriageRouterNode, connections=[ConsolidatedReviewNode, WrapUpNode], is_router=True),
    # Runtime: also routes to ImplementTaskNode (retry), but not declared
NodeConfig(node=ConsolidatedReviewNode, connections=[ReviewRouterNode]),
NodeConfig(node=ReviewRouterNode, connections=[UpdateTaskStatusNode, WrapUpNode], is_router=True),
    # Runtime: also routes to ImplementTaskNode (re-implement), but not declared
NodeConfig(node=UpdateTaskStatusNode, connections=[SaveStateNode]),
NodeConfig(node=SaveStateNode, connections=[TaskQueueRouterNode]),
    # This creates TaskQueueRouterNode → PatchDocsNode path (forward), but
    # the runtime route to ImplementTaskNode is not in declared connections.
    # Cycle check: SaveStateNode → TaskQueueRouterNode → PatchDocsNode (no cycle declared).
NodeConfig(node=PatchDocsNode, connections=[WrapUpNode]),
NodeConfig(node=WrapUpNode, connections=[PullRequestNode]),
NodeConfig(node=PullRequestNode, connections=[]),
```

**Verify the declared graph has no cycle:** The only declared paths from `TaskQueueRouterNode` is → `PatchDocsNode`. `SaveStateNode → TaskQueueRouterNode → PatchDocsNode → WrapUpNode → PullRequestNode → (end)`. No cycle. ✓

**Reachability:** The validator treats routers as able to reach any node (`_get_reachable_nodes` extends BFS to all `connections`). Since all routers list their forward targets, and the `ImplementTaskNode → TestTaskNode → ... → SaveStateNode → TaskQueueRouterNode` chain is reachable from `TaskQueueRouterNode` (which is reachable from `LoadTaskStateNode`), all nodes are reachable. But wait — `ImplementTaskNode` is NOT in any `connections` list in the revised version. The reachability check does BFS from `start` following `connections` edges. `ImplementTaskNode` would be **unreachable** because no declared connection points to it.

**Fix:** The validator must find `ImplementTaskNode` reachable. Options:
1. Add `ImplementTaskNode` to `TaskQueueRouterNode.connections`: `connections=[ImplementTaskNode, PatchDocsNode]`. Then: cycle check follows `TaskQueueRouterNode → ImplementTaskNode → TestTaskNode → TriageTaskNode → TriageRouterNode → ConsolidatedReviewNode → ReviewRouterNode → UpdateTaskStatusNode → SaveStateNode → TaskQueueRouterNode`. This IS a cycle.
2. Since routers use `is_router=True`, check if the validator's reachability treats routers specially... Looking at `_get_reachable_nodes()`: it just does BFS following `connections`. No special router handling. So `ImplementTaskNode` MUST be in some declared connection.

**Resolution: The validator's cycle detection must be updated to be router-aware, OR the workflow must be restructured to avoid the cycle.**

Since modifying `WorkflowValidator` is a framework change and needs its own tests (and the spec says "if the Workflow.run() engine needs modification to support cycles, that modification belongs in task 9"), the right approach is:

**Task 9 includes a targeted validator patch:** Make `_has_cycle()` skip edges from router nodes (nodes with `is_router=True`). Router edges are runtime-determined, not structural — the validator should only check structural (non-router) edges for cycles. This is a minimal, well-scoped change.

#### 9.3 Patch `app/core/validate.py` — make `_has_cycle()` skip router edges
**File:** `app/core/validate.py`
**Action:** In `_has_cycle`, when iterating `node_config.connections`, skip the DFS traversal if `node_config.is_router is True`. Router nodes determine their next node at runtime — their declared connections represent *possible* targets, not guaranteed structural edges. Cycles through router back-edges are bounded at runtime (by `max_attempts`), not structural.

**Change:** In `_has_cycle()` method, add after line 87 (`if node_config:`):
```python
if node_config.is_router:
    # Router connections are runtime-determined, not structural edges.
    # Skip cycle checking through routers — they are bounded at runtime.
    rec_stack.remove(node)
    return False
```

**This preserves:** cycle detection for linear (non-router) connections, reachability checking (unchanged), and the multi-connection router validation.

#### 9.4 Add test for the validator change
**File:** `tests/core/test_validate.py` (existing — add new test)
**Action:** Add a test that verifies a workflow with a router-mediated cycle passes validation.

```python
def test_router_mediated_cycle_passes_validation():
    """A router that can loop back to an earlier node is not a structural cycle."""
    # Build a schema with: A → B → RouterC → [A, D], D → (end)
    # where RouterC is_router=True
    # This has a declared cycle A → B → C → A, but since C is a router,
    # the validator should NOT reject it.
    ...
    validator = WorkflowValidator(schema)
    validator.validate()  # should not raise
```

#### 9.5 Register `SDLC_FLOW` in `app/workflows/workflow_registry.py`
**File:** `app/workflows/workflow_registry.py`
**Action:** Add import + enum member.

Add import: `from workflows.sdlc_flow_workflow import SDLCFlowWorkflow`
Add enum member: `SDLC_FLOW = SDLCFlowWorkflow`

#### 9.6 Register `SDLCFlowEventSchema` in `app/api/schema_registry.py`
**File:** `app/api/schema_registry.py`
**Action:** Add import + `SCHEMA_MAP` entry.

Add import: `from schemas.sdlc_schema import SDLCFlowEventSchema`
Add entry: `WorkflowRegistry.SDLC_FLOW.name: SDLCFlowEventSchema,`

#### 9.7 Create `tests/workflows/sdlc_flow/test_sdlc_flow_workflow.py`
**File:** `tests/workflows/sdlc_flow/test_sdlc_flow_workflow.py` (new)
**Action:** Create integration tests following the `test_proposal_generator_workflow.py` pattern.

**Test class `TestSDLCFlowWorkflowSchema`:**
- `test_schema_passes_validator` — `WorkflowValidator(SDLCFlowWorkflow.workflow_schema).validate()` (no exception)
- `test_schema_has_correct_start_node` — `assert schema.start is SetupWorktreeNode`
- `test_schema_has_all_nodes` — extract `{nc.node.__name__ for nc in schema.nodes}`, assert matches expected set of 14 node classes
- `test_routers_marked_is_router` — verify `TaskQueueRouterNode`, `TriageRouterNode`, `ReviewRouterNode` all have `is_router=True`

**Test class `TestSDLCFlowRegistration`:**
- `test_registered_in_workflow_registry` — `assert WorkflowRegistry.SDLC_FLOW.value is SDLCFlowWorkflow`
- `test_registered_in_schema_map` — `assert WorkflowRegistry.SDLC_FLOW.name in SCHEMA_MAP`
- `test_schema_registry_completeness` — iterate all `WorkflowRegistry` members, assert all in `SCHEMA_MAP`

**Test class `TestSDLCFlowWorkflowRun`:**
(E2E smoke test with all agents mocked — follows the `_run_workflow` pattern from `test_proposal_generator_workflow.py`)

- `test_happy_path_single_task` — one task, passes on first attempt. Mock all agents. Verify DAG traversal: Setup → Load → TaskQueue → Implement → Test → Triage → TriageRouter → Review → ReviewRouter → UpdateStatus → Save → TaskQueue(no more tasks) → PatchDocs → WrapUp → PR. Assert final `TaskContext` has all expected node outputs.

- `test_retry_loop` — one task, fails first test, triage returns RETRYABLE, succeeds on retry. Verify `ImplementTaskNode` runs twice, `attempt_count` incremented.

- `test_bail_path` — one task, hits MAJOR_BAIL. Verify routes to WrapUp → PR, skipping review and docs.

- `test_auto_pr_false` — set `auto_pr=False`, verify `PullRequestNode` skips PR creation.

**Mocking strategy** (same pattern as `test_proposal_generator_workflow.py`):
```python
with (
    patch.object(AgentNode, "__init__", lambda self: None),
    patch.object(AgentNode, "run_agent_recorded", _fake_run),
    patch("workflows.sdlc_flow_workflow_nodes.setup_worktree_node.subprocess.run", ...),
    patch("workflows.sdlc_flow_workflow_nodes.save_state_node.subprocess.run", ...),
    patch("workflows.sdlc_flow_workflow_nodes.pull_request_node.subprocess.run", ...),
    # etc.
):
```

**Verify:** `uv run python -m pytest tests/workflows/sdlc_flow/test_sdlc_flow_workflow.py -v` → all pass

---

### Step 10: Validate

#### 10.1 Run ruff
**Command:** `uv run python -m ruff check app/`
**Expected:** Clean (exit 0).

#### 10.2 Run pylint
**Command:** `uv run python -m pylint app/`
**Expected:** 10.00/10.

#### 10.3 Run full test suite
**Command:** `uv run python -m pytest`
**Expected:** All tests pass, no regressions in existing workflows.

#### 10.4 Verify dual registry completeness
**Command:** `uv run python -m pytest tests/api/test_endpoint.py::TestSchemaRegistryCompleteness -v`
**Expected:** Pass — every `WorkflowRegistry` member has a corresponding `SCHEMA_MAP` entry.

#### 10.5 Verify prompt templates loadable
**Command:** `uv run python -c "from services.prompt_loader import PromptManager; [PromptManager.get_template_info(t) for t in ['sdlc_implement_task', 'sdlc_triage', 'sdlc_review', 'sdlc_patch_docs', 'sdlc_wrap_up']]"`
**Expected:** No exceptions — all 5 templates found and parseable.

#### 10.6 Verify WorkflowValidator accepts the DAG
**Command:** `uv run python -c "from workflows.sdlc_flow_workflow import SDLCFlowWorkflow; SDLCFlowWorkflow()"`
**Expected:** No exception — `Workflow.__init__` calls `self.validator.validate()`.

**Verify:** All six commands above exit 0.

---

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

1. **Cycle detection vs. runtime loops (critical).** The `WorkflowValidator._has_cycle()` does DFS on declared `NodeConfig.connections` edges. The SDLC retry loop (`Implement → Test → Triage → back to Implement`) and the task queue loop (`SaveState → TaskQueueRouter → back to Implement`) are intentional bounded cycles. These must NOT be declared in `connections` — they are runtime-only (via `BaseRouter.route()` → `_handle_router`). However, this makes `ImplementTaskNode` unreachable in the declared graph, so it MUST appear in at least one router's `connections` list. This creates a declared cycle. **Step 9.3** patches `_has_cycle()` to skip router nodes (runtime-determined edges, bounded by business logic), which is the minimal framework change. This needs its own test.

2. **`update_node` key convention.** `AgentNode.run_agent_recorded` stores output under the key `"output"` (line 114 of `agent.py`: `task_context.update_node(self.node_name, output=to_jsonable(result.output))`). But manual `update_node` calls in nodes like `ProposalWriterNode.process` use `result=` (e.g., `task_context.update_node(node_name=self.node_name, result=roadmap)`). GEMINI.md rule 9 says tests should seed with `{"result": ...}`. The new SDLC nodes should use `result=` for manual stores (matching rule 9 and the proposal_writer pattern), and let `run_agent_recorded` handle the `output=` key for LLM nodes.

3. **`_TriageVerdictRouter` and `_ReviewVerdictRouter` instantiate target nodes.** The `determine_next_node` pattern returns a `Node()` instance (e.g., `return ImplementTaskNode()`). For `AgentNode` subclasses, this triggers `__init__` which builds the `Agent`. Tests should `patch.object(AgentNode, "__init__", lambda self: None)` to avoid real model instantiation.

4. **Triage split into AgentNode + Router.** The spec says `TriageTaskNode` inherits from `BaseRouter` and "uses a mid-tier model." The codebase pattern separates concerns: `ProposalReviewNode` (AgentNode, does LLM review) → `ProposalReviewRouterNode` (BaseRouter, routes on verdict). Step 7 follows this same split: `TriageTaskNode` (AgentNode) + `TriageRouterNode` (BaseRouter).

5. **`ConsolidatedReviewNode` also split.** Same reason: the review LLM call is in `ConsolidatedReviewNode(AgentNode)`, and the routing on verdict is in `ReviewRouterNode(BaseRouter)`. This adds one more node to the DAG (14 nodes total).

6. **`harness.json` real structure differs from spec.** The spec mentions 5 check kinds. The real harness has: `command` (some with no `kind` field — treat missing `kind` as plain command), `forbidden-pattern-scan`, `warning-scan`, `baseline-diff`, `count-delta`. The `enabled` field defaults to `True` if absent. `gates` controls whether a failure blocks the run or is advisory.

7. **Disjoint file ownership.** Steps 1–8 create new files with no overlap. Step 9 modifies 3 existing files: `workflow_registry.py`, `schema_registry.py`, `validate.py`. No step-to-step overlap on existing files. Steps 1–8 can run in parallel; step 9 depends on all of them; step 10 depends on step 9.

8. **`sdlc_schema.py` exists but is empty (0 bytes).** Step 1.1 should overwrite it.

9. **`PromptManager` API.** The real API is `PromptManager.get_prompt("template_name", **kwargs)` (static method, no `.j2` extension). Templates use YAML frontmatter (`---` block with `description` and `author`).

10. **`Node.process` returns `TaskContext`.** All `process()` methods return `task_context` (the same object passed in). This is confirmed in `base.py` line 41: `def process(self, task_context: TaskContext) -> TaskContext`.
