# Task Spec — Incremental Execution Observability

## Goal
Make workflow execution state observable as it happens — the framework records per-node status, timing, and token usage as each node completes, the worker persists the `events` row at each node boundary, and a read-only endpoint exposes the static workflow graph — without the deployment-agnostic brain ever opening a DB session itself.

## Context Pointers
- **Source plan:** `planning/plans/incremental-execution-observability.md` (Phases 1–5). This spec covers **Phase 1 (required, load-bearing)**, **Phase 2 (token/cost capture)**, and **Phase 3 (graph endpoint)**. **Phase 4** (promoted indexed `status` column) is deferred — out of scope. **Phase 5** (push/pub-sub/SSE) is explicitly not built; only keep the `on_progress` signature broad enough not to architect against it.
- **Decision:** `planning/decisions/D28-node-level-execution-state.md` — the *why*, and the injected-callback discipline.
- **Files to change:** `app/core/task.py` (status envelope), `app/core/workflow.py` (`node_context` + `run()` callback), `app/worker/tasks.py` (wire persistence), `app/core/nodes/agent.py` + `app/core/nodes/tool_use.py` (usage capture), `app/api/router.py` (+ a graph endpoint, likely a new `app/api/graph.py`), `app/api/models.py` (typed responses), `app/workflows/workflow_registry.py` (read for graph serialization).
- **Standing rules (CLAUDE.md):** Rule 1 (every change ships with tests), Rule 3 (`customer_care` frozen — zero node edits), Rule 7 (no deployment logic in nodes / `workflow.py`; persistence injected only via `GenericRepository`). House style: module docstring line 1, `X | None`/`StrEnum`/`list[T]` typing, never a param named `id`, `encoding="utf-8"`, `raise ... from e`, no f-strings in `logging` calls.
- **Boundary check (from the plan — must hold):** no reference to bastion anywhere in `app/`; no DB/session access inside `workflow.py` or any node; no change to `customer_care` or its nodes; no breaking change to `nodes[name]` payloads or `get_node_output()` semantics.

## Step-by-Step Tasks

### 1. Status/timing envelope on `TaskContext` (Phase 1a)
- In `app/core/task.py`, add `NodeStatus(StrEnum)` with `PENDING`/`RUNNING`/`SUCCESS`/`FAILED`.
- Add `NodeRun(BaseModel)` with `status: NodeStatus = NodeStatus.PENDING`, `started_at: str | None = None` (ISO-8601 UTC), `completed_at: str | None = None`, `error: str | None = None`.
- Add `node_runs: dict[str, NodeRun] = Field(default_factory=dict)` to `TaskContext`.
- Keep `nodes` and `get_node_output()` untouched — `node_runs` is a parallel, additive channel. Confirm `model_dump(mode="json")` round-trips the new field (enum serializes to its string value).

### 2. Framework stamps the envelope in `node_context` (Phase 1b)
- Extend `Workflow.node_context` (`app/core/workflow.py:55-75`) so it receives the active `TaskContext` (thread it through from `run()` — it is already in scope at the call site, `workflow.py:126`).
- On entry: set the node's `NodeRun` to `RUNNING` + `started_at` (UTC ISO-8601, e.g. `datetime.now(UTC).isoformat()`).
- On clean exit: `SUCCESS` + `completed_at`.
- In the `except` branch (before re-raising with `raise`): `FAILED` + `error` (str of the exception) + `completed_at`.
- Do **not** edit any node. The envelope is written entirely by the framework so `customer_care` stays frozen.

### 3. Injected progress callback on `Workflow.run()` (Phase 1c)
- Add `on_progress: Callable[[TaskContext], None] | None = None` to `Workflow.run()`. Default `None` → no-op (a tiny local `_noop` or an `if on_progress:` guard).
- Before the first node, seed every node in the schema as `PENDING` in `node_runs`, then invoke `on_progress` once so a freshly-dispatched run shows the full DAG pending.
- Invoke `on_progress(task_context)` after each node boundary (after `node_context` exits, success or — via the persisted FAILED envelope — failure).
- Keep the signature broad (single `TaskContext` arg) so a future publisher (Phase 5) can be layered in without changing the brain. No DB/session code here.

### 4. Worker wires persistence at each boundary (Phase 1d)
- In `app/worker/tasks.py`, build an `on_progress` closure (inside the existing `db_session` transaction) that assigns `db_event.task_context = task_context.model_dump(mode="json")` and **flushes** via the existing `GenericRepository`/session at each boundary.
- Pass it: `workflow.run(db_event.data, on_progress=...)`. Keep the terminal `repository.update(...)` as the final authoritative write.
- The brain stays agnostic: only the worker (which already owns the session) knows persistence exists.

### 5. Tests for Phase 1
- `node_runs` transitions `PENDING → RUNNING → SUCCESS` for a happy-path workflow (use an existing test workflow / fixture in `tests/core/`, not `customer_care`).
- A node that raises yields `FAILED` + non-null `error` + `completed_at`, and the exception still propagates.
- `on_progress` is invoked once before the first node and once per boundary — assert call count/order with a spy.
- Default path (`on_progress=None`) leaves behavior identical to today (existing tests still pass; terminal `task_context` unchanged).
- Add a test asserting a mid-run `model_dump(mode="json")` snapshot contains a partial `node_runs` (some `SUCCESS`, some still `PENDING`) — the observability guarantee.

### 6. Per-node token + cost capture (Phase 2)
- In the framework node base classes only — `app/core/nodes/agent.py` (`AgentNode`) and `app/core/nodes/tool_use.py` (`ToolUseNode`) — capture token usage + model id from the provider response into a consistent slot on the node's `NodeRun` (e.g. `usage: dict | None` with `{input_tokens, output_tokens, model}`). Add the field to `NodeRun` in `task.py`.
- These are framework-owned nodes — do **not** touch `customer_care` nodes.
- **Tests:** a stubbed/mocked provider response yields the expected `NodeRun.usage` token counts; a non-LLM node records no usage (`usage is None`).

### 7. Workflow graph introspection endpoint (Phase 3)
- Add read-only `GET /workflows` (list registered workflow types from `WorkflowRegistry`) and `GET /workflows/{workflow_type}/graph` returning `{nodes: [...], edges: [[from, to], ...]}` serialized from each workflow's `WorkflowSchema` (`start`, `nodes`, `connections`). Node identity = class `__name__` (matches `task_context.nodes` / `node_runs` keys).
- Wire into `app/api/router.py` (a new `app/api/graph.py` module is acceptable); add typed Pydantic response models in `app/api/models.py`. Unknown type → 404.
- **Tests:** the endpoint returns the correct node/edge set for `customer_care` (read-only introspection of the frozen workflow is fine); unknown type → 404.

### 8. Validate
- Run the Validation Commands listed below and confirm all pass (all `gates: true` checks green, pytest authoritative, collection count not decreased).
- Grep `app/` to confirm no reference to "bastion" was introduced.

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
- Scope decision: this spec lands Phases 1–3 of the source plan. Phase 4 (promoted indexed `status` column via Alembic migration) is deferred until query volume justifies denormalizing state out of the JSON `task_context`. Phase 5 (push via Redis pub/sub or SSE) is a recorded future seam — not built; only keep the `on_progress` signature broad.
