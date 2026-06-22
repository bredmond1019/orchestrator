# Task Breakdown — Incremental Execution Observability

## Source Spec
`planning/incremental-execution-observability/tasks.md`

## Goal
Make workflow execution state observable as it happens — the framework records per-node status, timing, and token usage as each node completes, the worker persists the `events` row at each node boundary, and a read-only endpoint exposes the static workflow graph — without the deployment-agnostic brain ever opening a DB session itself.

## How to Use
Work top to bottom. Each sub-step is a single atomic action. Run the inline **Verify**
checks as you go — do not batch them at the end. Each check must pass before continuing.

All paths are relative to the repo root. Validation commands that start with `cd app`
run from `app/`; bare `uv run …` commands run from the repo root.

---

## Steps

### Step 1: Status/timing envelope on `TaskContext` (Phase 1a)

> Edits `app/core/task.py`. This same file is also edited by Step 6 (adds `usage`
> to `NodeRun`). Step 6 depends on this step — see **Notes / disjoint file ownership**.

#### 1.1 Add `NodeStatus` and `NodeRun` to `app/core/task.py`
**File:** `app/core/task.py`
**Action:** edit imports + add two classes above `class TaskContext`.
- Change the import block (currently `from typing import Any` on line 8) to also import `StrEnum`:
  - Add `from enum import StrEnum` (stdlib — sort it before `from typing import Any`).
- After the imports and before `class TaskContext`, add:
  ```python
  class NodeStatus(StrEnum):
      PENDING = "pending"
      RUNNING = "running"
      SUCCESS = "success"
      FAILED = "failed"


  class NodeRun(BaseModel):
      """Per-node execution envelope: status, timing, error, and token usage.

      Parallel/additive to ``TaskContext.nodes`` — it never replaces node output,
      it records *how* each node ran. Written entirely by the framework (see
      ``Workflow.node_context``) so reference workflows stay frozen.
      """

      status: NodeStatus = NodeStatus.PENDING
      started_at: str | None = None
      completed_at: str | None = None
      error: str | None = None
      usage: dict | None = None
  ```
  - `usage` is added now (Step 6 populates it) so `task.py` is touched once. Document in the
    docstring that `usage` carries `{input_tokens, output_tokens, model}` for LLM nodes.

#### 1.2 Add the `node_runs` field to `TaskContext`
**File:** `app/core/task.py`
**Action:** add one field to the `TaskContext` model, after the `metadata` field (currently lines 38–41).
```python
node_runs: dict[str, NodeRun] = Field(
    default_factory=dict,
    description="Per-node execution envelope (status/timing/usage), keyed by node class name",
)
```
- Do **not** modify `nodes`, `update_node`, or `get_node_output`. `node_runs` is a parallel channel.

**Verify:**
```
cd app && uv run python -c "from core.task import TaskContext, NodeRun, NodeStatus; c=TaskContext(event={}); c.node_runs['N']=NodeRun(status=NodeStatus.SUCCESS, started_at='t'); d=c.model_dump(mode='json'); print(d['node_runs']['N']['status'])"
```
→ prints `success` (enum serialized to its string value; round-trips through `model_dump(mode="json")`).

---

### Step 2: Framework stamps the envelope in `node_context` (Phase 1b)

> Edits `app/core/workflow.py`. This same file is also edited by Step 3 (adds the
> `on_progress` callback to `run()`). Step 3 depends on this step — see **Notes**.

#### 2.1 Add imports for timestamping to `app/core/workflow.py`
**File:** `app/core/workflow.py`
**Action:** extend the import block (top of file, currently lines 9–19).
- Add `from datetime import UTC, datetime` (stdlib — place with the other stdlib imports near `import logging`).
- Add `from core.task import NodeRun, NodeStatus` to the existing `from core.task import TaskContext` line (so it reads `from core.task import NodeRun, NodeStatus, TaskContext`).

#### 2.2 Thread `task_context` into `node_context` and stamp the envelope
**File:** `app/core/workflow.py`
**Action:** replace the whole `node_context` method (currently lines 55–75).
- New signature: `def node_context(self, node_name: str, task_context: TaskContext):` (keep the `@contextmanager` decorator).
- Body:
  ```python
  run = task_context.node_runs.setdefault(node_name, NodeRun())
  run.status = NodeStatus.RUNNING
  run.started_at = datetime.now(UTC).isoformat()
  logging.info("Starting node: %s", node_name)
  try:
      yield
  except Exception as e:
      run.status = NodeStatus.FAILED
      run.error = str(e)
      run.completed_at = datetime.now(UTC).isoformat()
      logging.error("Error in node %s: %s", node_name, str(e))
      raise
  else:
      run.status = NodeStatus.SUCCESS
      run.completed_at = datetime.now(UTC).isoformat()
  finally:
      logging.info("Finished node: %s", node_name)
  ```
  - Note the `except`/`else` split: `SUCCESS` must only be set on a clean exit, so it goes in
    `else`, not `finally`. `FAILED` + `error` + `completed_at` are set in `except` **before** `raise`.
  - Preserve the existing `logging.info` start/finish and `logging.error` lines verbatim — the
    existing `TestNodeContextLogging` tests assert on them.

#### 2.3 Update the `node_context` call site in `run()`
**File:** `app/core/workflow.py`
**Action:** edit the `with` statement inside `run()` (currently line 126).
- Change `with self.node_context(current_node_class.__name__):`
  to `with self.node_context(current_node_class.__name__, task_context):`.

**Verify:**
```
cd app && uv run pytest ../tests/core/test_workflow.py -q
```
→ all existing workflow tests still pass (logging assertions unchanged; exception still propagates).

---

### Step 3: Injected progress callback on `Workflow.run()` (Phase 1c)

> Edits `app/core/workflow.py` — same file as Step 2. Do Step 2 first.

#### 3.1 Add the `Callable` import
**File:** `app/core/workflow.py`
**Action:** add `from collections.abc import Callable` to the stdlib imports (near `import logging`).

#### 3.2 Add the `on_progress` parameter and seed all nodes PENDING
**File:** `app/core/workflow.py`
**Action:** edit the `run()` method (currently lines 104–133).
- New signature:
  ```python
  def run(
      self,
      event: Any,
      on_progress: Callable[[TaskContext], None] | None = None,
  ) -> TaskContext:
  ```
- Update the docstring `Args:` to document `on_progress` (an injected callback invoked once
  before the first node with every node `PENDING`, then once after each node boundary; default
  `None` → no-op; keep the signature broad — a single `TaskContext` arg — so a future publisher
  can be layered in without changing the framework).
- After `task_context.metadata["nodes"] = self.nodes` (line 121) and before
  `current_node_class = self.workflow_schema.start` (line 122), seed every node PENDING and emit
  the initial snapshot:
  ```python
  for node_class in self.nodes:
      task_context.node_runs.setdefault(node_class.__name__, NodeRun())
  if on_progress:
      on_progress(task_context)
  ```
  - `self.nodes` is `dict[type[Node], NodeConfig]`, so iterating yields node **classes**; key by
    `__name__` to match `node_context`/`task_context.nodes` keys.

#### 3.3 Invoke `on_progress` after each node boundary
**File:** `app/core/workflow.py`
**Action:** inside the `while current_node_class:` loop, after the `with self.node_context(...)` block
exits and before `current_node_class = self._get_next_node_class(...)` (currently between lines 127
and 129), add:
```python
if on_progress:
    on_progress(task_context)
```
- This fires on success. On failure the exception propagates out of the `with` (before this line),
  so the FAILED envelope is already stamped on `task_context` by `node_context`; the worker's
  terminal write (Step 4) persists it. Do **not** add DB/session code here — the framework stays
  deployment-agnostic (CLAUDE.md Rule 7).

**Verify:**
```
cd app && uv run python -c "from core.workflow import Workflow; import inspect; print('on_progress' in inspect.signature(Workflow.run).parameters)"
```
→ prints `True`. Then `cd app && uv run pytest ../tests/core/test_workflow.py -q` still passes (default `on_progress=None` path unchanged).

---

### Step 4: Worker wires persistence at each boundary (Phase 1d)

> Edits `app/worker/tasks.py` only — no overlap with other steps.

#### 4.1 Build an `on_progress` closure and pass it to `workflow.run`
**File:** `app/worker/tasks.py`
**Action:** edit the body of `process_incoming_event` (currently lines 42–49, inside the
`with contextmanager(db_session)() as session:` block).
- Replace the block:
  ```python
  # Execute workflow and store results
  workflow = WorkflowRegistry[db_event.workflow_type].value()
  task_context = workflow.run(db_event.data).model_dump(mode="json")

  db_event.task_context = task_context

  # Update event with processing results
  repository.update(obj=db_event)
  ```
  with:
  ```python
  # Execute workflow, persisting node-level progress at each boundary.
  workflow = WorkflowRegistry[db_event.workflow_type].value()

  def persist_progress(task_context: TaskContext) -> None:
      # The worker (which already owns the session) is the only place that
      # knows persistence exists; the framework stays deployment-agnostic.
      db_event.task_context = task_context.model_dump(mode="json")
      session.flush()

  result_context = workflow.run(db_event.data, on_progress=persist_progress)

  # Terminal authoritative write (final state of the run).
  db_event.task_context = result_context.model_dump(mode="json")
  repository.update(obj=db_event)
  ```
- The closure flushes (not commits) inside the existing open transaction — the `db_session`
  context manager owns commit/rollback. `repository.update(...)` remains the final authoritative write.

#### 4.2 Import `TaskContext` for the closure type hint
**File:** `app/worker/tasks.py`
**Action:** add `from core.task import TaskContext` to the import block (top of file, with the
other `from …` imports — keep import sorting: it sorts under the `core` group, before `database`).

**Verify:**
```
cd app && uv run python -c "import worker.tasks"
```
→ imports cleanly (no `ImportError`, no `NameError`).

---

### Step 5: Tests for Phase 1

> Creates `tests/core/test_observability.py` (new file — no conflict with other steps).
> Uses the same stub-node / stub-workflow pattern as `tests/core/test_workflow.py`.

#### 5.1 Create `tests/core/test_observability.py` with stub workflows
**File:** `tests/core/test_observability.py`
**Action:** create the file. Module docstring on line 1, then imports, then stub nodes/workflows
mirroring `tests/core/test_workflow.py`.
```python
"""Unit tests for incremental execution observability (node_runs, on_progress)."""

import pytest
from pydantic import BaseModel

from core.nodes.base import Node
from core.schema import NodeConfig, WorkflowSchema
from core.task import NodeStatus, TaskContext
from core.workflow import Workflow


class StubEventSchema(BaseModel):
    action: str = "default"


class StepNodeA(Node):
    def process(self, task_context: TaskContext) -> TaskContext:
        task_context.update_node("StepNodeA", ran=True)
        return task_context


class StepNodeB(Node):
    def process(self, task_context: TaskContext) -> TaskContext:
        task_context.update_node("StepNodeB", ran=True)
        return task_context


class TwoStepWorkflow(Workflow):
    workflow_schema = WorkflowSchema(
        start=StepNodeA,
        event_schema=StubEventSchema,
        nodes=[
            NodeConfig(node=StepNodeA, connections=[StepNodeB]),
            NodeConfig(node=StepNodeB),
        ],
    )


class BoomNode(Node):
    def process(self, task_context: TaskContext) -> TaskContext:
        raise RuntimeError("boom")


class BoomWorkflow(Workflow):
    workflow_schema = WorkflowSchema(
        start=BoomNode,
        event_schema=StubEventSchema,
        nodes=[NodeConfig(node=BoomNode)],
    )
```

#### 5.2 Add the happy-path status-transition test
**File:** `tests/core/test_observability.py`
**Action:** append a test class.
- `test_node_runs_reach_success` — `ctx = TwoStepWorkflow().run({"action": "x"})`; assert
  `ctx.node_runs["StepNodeA"].status == NodeStatus.SUCCESS` and same for `StepNodeB`; assert each
  has non-null `started_at` and `completed_at`.

#### 5.3 Add the failure-envelope test
**File:** `tests/core/test_observability.py`
**Action:** append.
- `test_failed_node_records_error_and_propagates` — capture the context via a spy callback so the
  envelope is observable despite the raise:
  ```python
  captured = []
  with pytest.raises(RuntimeError, match="boom"):
      BoomWorkflow().run({"action": "x"}, on_progress=lambda c: captured.append(c.model_dump(mode="json")))
  # the seed snapshot fired before the first node; inspect the live context after the raise is
  # not possible, so assert on the FAILED envelope via a direct run wrapped in try/except instead:
  ```
  Simpler/robust form — run inside try/except and inspect the context object directly:
  ```python
  wf = BoomWorkflow()
  ctx_holder = {}
  def grab(c):
      ctx_holder["ctx"] = c
  with pytest.raises(RuntimeError, match="boom"):
      wf.run({"action": "x"}, on_progress=grab)
  ctx = ctx_holder["ctx"]  # seeded snapshot reference; same object mutated in place
  assert ctx.node_runs["BoomNode"].status == NodeStatus.FAILED
  assert ctx.node_runs["BoomNode"].error is not None
  assert ctx.node_runs["BoomNode"].completed_at is not None
  ```
  - This works because `on_progress` is invoked once (seed) before the first node with the **same**
    `task_context` object the framework keeps mutating, so `ctx_holder["ctx"]` is that live object.

#### 5.4 Add the callback-invocation-count test (spy)
**File:** `tests/core/test_observability.py`
**Action:** append.
- `test_on_progress_called_once_before_first_node_and_per_boundary`:
  ```python
  calls = []
  TwoStepWorkflow().run({"action": "x"}, on_progress=lambda c: calls.append(
      {n: r.status for n, r in c.node_runs.items()}))
  assert len(calls) == 3  # 1 seed + 2 node boundaries
  # first snapshot: all PENDING
  assert all(s == NodeStatus.PENDING for s in calls[0].values())
  # last snapshot: all SUCCESS
  assert all(s == NodeStatus.SUCCESS for s in calls[-1].values())
  ```

#### 5.5 Add the backward-compatibility test
**File:** `tests/core/test_observability.py`
**Action:** append.
- `test_default_on_progress_none_is_noop` — `ctx = TwoStepWorkflow().run({"action": "x"})`
  (no callback); assert `"nodes" not in ctx.metadata` (terminal cleanup unchanged) and
  `ctx.nodes["StepNodeA"] == {"ran": True}` (existing node-output contract intact).

#### 5.6 Add the mid-run partial-snapshot test (the observability guarantee)
**File:** `tests/core/test_observability.py`
**Action:** append.
- `test_mid_run_snapshot_is_partial` — capture each `model_dump(mode="json")` snapshot via
  `on_progress`; assert that at least one captured snapshot has a mix of statuses (e.g. the
  snapshot after `StepNodeA` shows `StepNodeA` = `"success"` while `StepNodeB` = `"pending"`):
  ```python
  snaps = []
  TwoStepWorkflow().run({"action": "x"}, on_progress=lambda c: snaps.append(c.model_dump(mode="json")))
  mid = snaps[1]["node_runs"]  # after StepNodeA, before StepNodeB
  assert mid["StepNodeA"]["status"] == "success"
  assert mid["StepNodeB"]["status"] == "pending"
  ```

**Verify:**
```
cd app && uv run pytest ../tests/core/test_observability.py -q
```
→ all new tests pass.

---

### Step 6: Per-node token + cost capture (Phase 2)

> Edits `app/core/task.py` (already has the `usage` field from Step 1.1 — no further edit needed
> there) and `app/core/nodes/agent.py` + `app/core/nodes/tool_use.py`. **Do not touch any
> `customer_care` node.** See **Notes** for the AgentNode design wrinkle.

#### 6.1 Add a usage-recording helper to `AgentNode`
**File:** `app/core/nodes/agent.py`
**Action:** add a concrete helper method to `class AgentNode` (after `__init__`, before the
abstract methods). The base class cannot intercept `self.agent.run_sync(...)` calls that
subclasses make directly, so provide a helper that new nodes call to run the agent **and** record
usage in one place.
```python
def run_agent_recorded(self, task_context: TaskContext, user_prompt: str):
    """Run the agent and record token usage onto this node's NodeRun.

    New AgentNode subclasses should call this instead of ``self.agent.run_sync``
    so per-node usage is captured by the framework. Returns the pydantic-ai result.
    """
    result = self.agent.run_sync(user_prompt=user_prompt)
    usage = result.usage()
    run = task_context.node_runs.get(self.node_name)
    if run is not None:
        run.usage = {
            "input_tokens": getattr(usage, "input_tokens", None)
            or getattr(usage, "request_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None)
            or getattr(usage, "response_tokens", None),
            "model": self.get_agent_config().model_name,
        }
    return result
```
- Import note: `TaskContext` is already imported in `agent.py` (line 24). Confirm the
  pydantic-ai `result.usage()` attribute names at implementation time (`input_tokens`/`output_tokens`
  in newer versions, `request_tokens`/`response_tokens` in older — the `getattr(... ) or getattr(...)`
  fallback covers both; remove the dead branch once confirmed). pydantic-ai is pinned `>=0.1.5`.
- Do **not** alter the existing `AgentNode.__init__`/abstract signature, and do **not** edit
  `customer_care` nodes — they keep calling `run_sync` directly and simply record no usage.

#### 6.2 Record usage in `ToolUseNode.process`
**File:** `app/core/nodes/tool_use.py`
**Action:** edit `process` (currently lines 51–93). `ToolUseNode.process` is concrete and owns the
Anthropic response, so capture usage directly.
- Accumulate token counts across loop iterations. Before the `while` loop (after `iterations = 0`,
  line 53) add:
  ```python
  input_tokens = 0
  output_tokens = 0
  ```
- Inside the loop, immediately after `response = self._client.messages.create(...)` /
  `iterations += 1` (after line 62), add:
  ```python
  usage = getattr(response, "usage", None)
  if usage is not None:
      input_tokens += getattr(usage, "input_tokens", 0) or 0
      output_tokens += getattr(usage, "output_tokens", 0) or 0
  ```
- Before `return task_context` (line 93), record onto the NodeRun:
  ```python
  run = task_context.node_runs.get(self.node_name)
  if run is not None:
      run.usage = {
          "input_tokens": input_tokens,
          "output_tokens": output_tokens,
          "model": self._model,
      }
  ```

#### 6.3 Add usage tests for both node bases
**File:** `tests/core/test_nodes_usage.py`
**Action:** create the file. Module docstring line 1.
- `TestToolUseNodeUsage` — reuse the mocking pattern from `tests/core/test_nodes_tool_use.py`
  (patch `core.nodes.tool_use.anthropic.Anthropic`). Build a `_tool_use`/`_end_turn` response whose
  `.usage.input_tokens` / `.usage.output_tokens` are set (e.g. `MagicMock(input_tokens=11, output_tokens=7)`).
  Seed the node's NodeRun first so the helper finds it:
  ```python
  ctx = TaskContext(event={"input": "x"})
  ctx.node_runs[node.node_name] = NodeRun(status=NodeStatus.RUNNING)
  node.process(ctx)
  assert ctx.node_runs[node.node_name].usage["input_tokens"] == 11
  assert ctx.node_runs[node.node_name].usage["output_tokens"] == 7
  assert ctx.node_runs[node.node_name].usage["model"]  # the injected TOOL_USE_MODEL
  ```
- `TestAgentNodeUsage` — define a minimal concrete `AgentNode` subclass; patch its `agent`
  attribute with a `MagicMock` whose `run_sync(...).usage()` returns
  `MagicMock(input_tokens=5, output_tokens=9)`; call `run_agent_recorded(ctx, "hi")` after seeding
  the NodeRun; assert `ctx.node_runs[node.node_name].usage == {"input_tokens": 5, "output_tokens": 9, "model": <config model_name>}`.
- `test_non_llm_node_has_no_usage` — run a plain `Node` (or use `TwoStepWorkflow` from Step 5) and
  assert `ctx.node_runs["StepNodeA"].usage is None`.

**Verify:**
```
cd app && uv run pytest ../tests/core/test_nodes_usage.py -q
```
→ all pass.

---

### Step 7: Workflow graph introspection endpoint (Phase 3)

> Creates `app/api/graph.py`, edits `app/api/router.py` and `app/api/models.py`. No overlap with
> Steps 1–6. Read-only introspection of the frozen `customer_care` schema is allowed (no edit to it).

#### 7.1 Add typed response models to `app/api/models.py`
**File:** `app/api/models.py`
**Action:** append two models after `EventPayload`.
```python
class WorkflowListResponse(BaseModel):
    workflows: list[str]


class WorkflowGraphResponse(BaseModel):
    nodes: list[str]
    edges: list[tuple[str, str]]
```

#### 7.2 Create the graph router `app/api/graph.py`
**File:** `app/api/graph.py`
**Action:** create the file. Module docstring line 1. Build the graph by reading each workflow's
`workflow_schema` ClassVar directly (no instantiation needed; `workflow_schema` is a class
attribute — see `customer_care_workflow.py`).
```python
"""Read-only workflow graph introspection endpoints."""

from fastapi import APIRouter, HTTPException

from api.models import WorkflowGraphResponse, WorkflowListResponse
from workflows.workflow_registry import WorkflowRegistry

router = APIRouter()


@router.get("/workflows", response_model=WorkflowListResponse)
def list_workflows() -> WorkflowListResponse:
    return WorkflowListResponse(workflows=[w.name for w in WorkflowRegistry])


@router.get("/workflows/{workflow_type}/graph", response_model=WorkflowGraphResponse)
def workflow_graph(workflow_type: str) -> WorkflowGraphResponse:
    try:
        workflow_cls = WorkflowRegistry[workflow_type].value
    except KeyError as e:
        raise HTTPException(
            status_code=404, detail=f"Unknown workflow_type: {workflow_type!r}"
        ) from e

    schema = workflow_cls.workflow_schema
    nodes: list[str] = []

    def _add(node_cls) -> None:
        name = node_cls.__name__
        if name not in nodes:
            nodes.append(name)

    _add(schema.start)
    edges: list[tuple[str, str]] = []
    for node_config in schema.nodes:
        _add(node_config.node)
        for connection in node_config.connections:
            _add(connection)
            edges.append((node_config.node.__name__, connection.__name__))

    return WorkflowGraphResponse(nodes=nodes, edges=edges)
```
- Node identity is the class `__name__` — matches `task_context.nodes` / `node_runs` keys.
- `WorkflowRegistry[workflow_type]` raises `KeyError` for an unknown name → mapped to 404
  (per CLAUDE.md: `raise … from e`).

#### 7.3 Wire the graph router into the API
**File:** `app/api/router.py`
**Action:** edit the file (currently 9 lines).
- Change `from api import endpoint, health` to `from api import endpoint, graph, health`.
- After the existing `router.include_router(health.router, tags=["health"])` line, add:
  ```python
  router.include_router(graph.router, tags=["workflows"])
  ```

#### 7.4 Add endpoint tests
**File:** `tests/api/test_graph.py`
**Action:** create the file. Module docstring line 1. Use `TestClient(app)` (no DB needed — these
endpoints don't touch the session, so the heavy `endpoint_context` fixture from
`tests/api/test_endpoint.py` is unnecessary; a bare `TestClient(app)` suffices).
- `test_list_workflows_contains_registered_types` — `GET /workflows`; assert 200 and that
  `"CUSTOMER_CARE"` and `"CONTENT_PIPELINE"` are in `response.json()["workflows"]`.
- `test_customer_care_graph_nodes_and_edges` — `GET /workflows/CUSTOMER_CARE/graph`; assert 200;
  assert the node set equals
  `{"AnalyzeTicketNode","TicketRouterNode","GenerateResponseNode","CloseTicketNode","EscalateTicketNode","ProcessInvoiceNode","SendReplyNode"}`
  and the edge set (as a set of tuples) equals:
  ```python
  {
      ("AnalyzeTicketNode", "TicketRouterNode"),
      ("TicketRouterNode", "CloseTicketNode"),
      ("TicketRouterNode", "EscalateTicketNode"),
      ("TicketRouterNode", "GenerateResponseNode"),
      ("TicketRouterNode", "ProcessInvoiceNode"),
      ("GenerateResponseNode", "SendReplyNode"),
  }
  ```
  (JSON serializes tuples as lists — compare with `{tuple(e) for e in response.json()["edges"]}`.)
- `test_unknown_workflow_type_returns_404` — `GET /workflows/NOPE/graph`; assert 404.

**Verify:**
```
cd app && uv run pytest ../tests/api/test_graph.py -q
```
→ all pass.

---

### Step 8: Validate

#### 8.1 Auto-fix lint, then run the full validation suite
**File:** (no file change)
**Action:** run, from the repo root unless noted:
```
uv run ruff check app/ --fix
uv run ruff check app/
cd app && uv run python -c 'import main'
cd app && uv run python -c 'import worker.config'
cd app && uv run python -c 'import database.session'
cd app && uv run python -c 'import database.repository'
uv run pylint app/
uv run pytest --collect-only -q
uv run pytest
```
- All `gates: true` checks green; pytest authoritative; collected-test count strictly greater than
  the pre-change count (Steps 5, 6.3, 7.4 add tests).

#### 8.2 Confirm no `bastion` reference was introduced
**File:** (no file change)
**Action:**
```
grep -rni "bastion" app/ ; echo "exit=$?"
```
→ no matches (grep exit code `1`).

**Verify:** the full suite passes and the grep finds nothing.

---

## Acceptance Criteria
- `TaskContext` has `node_runs: dict[str, NodeRun]` with `NodeStatus`/`NodeRun` (incl. `usage`); it survives `model_dump(mode="json")`.
- `Workflow.node_context` stamps `RUNNING`/`SUCCESS`/`FAILED` + timestamps + `error` without any node being edited; `customer_care` and its nodes are unchanged.
- `Workflow.run(event, on_progress=None)` is backward-compatible; with a callback it fires once before the first node (all `PENDING`) and once per node boundary.
- `app/worker/tasks.py` persists `db_event.task_context` incrementally (flush per boundary, inside the existing transaction) and retains the terminal authoritative write; no DB/session code exists in `workflow.py` or any node.
- `AgentNode` and `ToolUseNode` populate `NodeRun.usage` with `{input_tokens, output_tokens, model}`; non-LLM nodes leave it `None`.
- `GET /workflows` and `GET /workflows/{type}/graph` return the correct nodes/edges for `customer_care`; unknown type → 404.
- No string "bastion" anywhere in `app/`; no breaking change to `nodes[name]` or `get_node_output()`.
- New tests cover every phase above; `uv run pytest` passes and the collected-test count is strictly greater than before.

## Validation Commands
```
cd app && uv run python -c 'import main'
cd app && uv run python -c 'import worker.config'
cd app && uv run python -c 'import database.session'
cd app && uv run python -c 'import database.repository'
uv run ruff check app/
uv run pylint app/
uv run pytest --collect-only -q
uv run pytest
```

## Notes

### Disjoint file ownership (read before running steps as parallel tasks)
Two existing files are each edited under more than one step. These are **sequential dependencies**,
not parallel-safe — declare them in `execution-plan.json` so the block does not merge conflicting branches:

| File | Edited by | Ordering required |
|---|---|---|
| `app/core/task.py` | Step 1 (`NodeStatus`/`NodeRun`/`node_runs`, incl. the `usage` field) and Step 6 (uses `usage`) | Step 1 adds the `usage` field up front so Step 6 makes **no** edit to `task.py` — Step 6 only depends on Step 1, no co-edit. |
| `app/core/workflow.py` | Step 2 (`node_context`) and Step 3 (`run` + `on_progress`) | Step 3 depends on Step 2; run them in order, same wave is fine only if serialized. |
| `app/api/models.py` | Step 7 only | no conflict |
| `app/api/router.py` | Step 7 only | no conflict |

Dependency summary for wave computation: **1 → {2 → 3 → 4 → 5}, 1 → 6, 7 (independent), 8 (last)**.
The only genuinely parallelizable units are `{2-chain, 6, 7}` after Step 1 lands. Step 5 depends on 1–4;
Step 8 depends on everything. This spec is largely a sequential chain — expect narrow waves.

### AgentNode usage-capture wrinkle (affects Step 6)
`AgentNode.process` is **abstract** — concrete subclasses (e.g. `customer_care`'s
`GenerateResponseNode`, `generate_response_node.py:29`) call `self.agent.run_sync(...)` directly,
so the base class has no seam to intercept the response transparently. The breakdown therefore adds
an opt-in helper `run_agent_recorded(...)` on the base that new nodes call instead of `run_sync`.
Consequence: **existing `customer_care` nodes record no usage** (they keep calling `run_sync`
directly) — this is acceptable and required, since `customer_care` is frozen (CLAUDE.md Rule 3).
`ToolUseNode.process` is concrete and owns its response, so its usage capture is unconditional.

### pydantic-ai usage attribute names
pydantic-ai is pinned `>=0.1.5`. `result.usage()` returns a usage object whose token attribute
names differ across versions (`input_tokens`/`output_tokens` vs `request_tokens`/`response_tokens`).
The Step 6 helper uses a `getattr(... ) or getattr(...)` fallback; at implementation time confirm
the actual attribute names for the installed version and drop the dead branch.

### House style (CLAUDE.md) — applies to every new/edited file
Module docstring on line 1 (before imports); `list[T]`/`X | None`/`StrEnum` typing (already used);
never a param named `id`; `encoding="utf-8"` on any `open()`; `raise … from e` in `except`; no
f-strings in `logging` calls; sort imports (`ruff --fix`). Every new workflow/feature ships with
tests (Rule 1). No deployment/DB/session logic in `workflow.py` or any node (Rule 7) — persistence
lives only in `worker/tasks.py`.
