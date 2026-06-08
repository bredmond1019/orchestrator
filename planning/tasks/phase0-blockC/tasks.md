# Task Spec — Phase 0, Block C (Test Infrastructure + Core Hardening)

## Goal
Make the orchestration framework trustworthy before any client-facing system is built on it: establish a pytest suite with working fixtures, fix the four documented production bugs, and write unit tests for the core engine, database layer, API, and services — without touching the reference-only `customer_care` workflow.

## Context Pointers
- **Master Plan:** Phase 0 → Foundation Block C (Test Infrastructure + Core Hardening section)
- **Projects Plan:** Part 1 — Component reference; Test Plan Option A scope (core only, no customer_care)
- **CONTEXT.md:** Test Plan summary — "test the core engine, infrastructure, and services; do not test customer_care; fix four documented bugs; then every new workflow ships with its own tests"
- **CLAUDE.md:** Known bugs table (four bugs to fix); standing rules (no hardcoded prompts, customer_care frozen, no deployment decisions in nodes)
- **Key files to fix:**
  - `app/database/repository.py:71–73` — `GenericRepository.exists()` SQLAlchemy 2.x error
  - `app/api/endpoint.py:66–70` — commit before `send_task` ghost-row risk
  - `app/database/session.py:15–16` — `create_engine(...)` and `SessionLocal` at import time
  - `app/worker/config.py:45–46` — `Celery(...)` and `config_from_object(...)` at import time
  - `app/core/nodes/router.py` — hard-coded string keys in router nodes give silent misses instead of clear errors
- **Scope boundary:** Do NOT write tests for `app/workflows/customer_care_workflow*` or `app/schemas/customer_care_schema.py`. Those are reference-only (CLAUDE.md rule 3).

## Step-by-Step Tasks

### 1. Add test dependencies and pytest configuration
No `pytest` is currently in `pyproject.toml`. This is the prerequisite for everything else.

- Add to `[dependency-groups] dev` in `pyproject.toml`:
  ```
  "pytest>=8.0",
  "pytest-mock>=3.14",
  "httpx>=0.27",
  "freezegun>=1.5",
  "pytest-env>=1.1",
  ```
  (`httpx` is required for FastAPI's `TestClient`; `freezegun` enables time-travel in future tests; `pytest-env` sets env vars in `pytest.ini`.)
- Run `uv sync` to install.
- Create `pytest.ini` at the repo root:
  ```ini
  [pytest]
  testpaths = tests
  pythonpath = app
  env =
      DATABASE_URL=sqlite:///:memory:
      PROJECT_NAME=test
      REDIS_URL=redis://localhost:6379/0
  ```
  (`pythonpath = app` ensures `import database.session` resolves correctly in tests. `DATABASE_URL` and `PROJECT_NAME` prevent import-time failures before the side-effect fix is in place.)
- Create the test directory tree:
  ```
  tests/
  ├── __init__.py
  ├── conftest.py
  ├── core/
  │   └── __init__.py
  ├── database/
  │   └── __init__.py
  ├── api/
  │   └── __init__.py
  └── services/
      └── __init__.py
  ```
- Write a stub `tests/conftest.py` (expand in step 3 after the side-effect fix):
  ```python
  # Fixtures added after import-time side effects are fixed (Step 3)
  ```
- Verify: `uv run pytest --collect-only` exits with zero errors (no tests collected yet, but no import errors either).

### 2. Fix Bug 1 — `GenericRepository.exists()` (SQLAlchemy 2.x)

**Location:** `app/database/repository.py:71–73`

**Current broken code:**
```python
def exists(self, **kwargs) -> bool:
    return self.session.query(
        self.model.query.filter_by(**kwargs).exists()
    ).scalar()
```
`self.model.query` is the SQLAlchemy 1.x legacy interface — raises `AttributeError` in 2.x.

**Fix:** Replace with a 2.x-compatible query:
```python
def exists(self, **kwargs) -> bool:
    return (
        self.session.query(self.model).filter_by(**kwargs).first() is not None
    )
```

**Write the test** at `tests/database/test_repository.py` (the full DB fixture suite comes in step 3, but this test validates the fix):
- Test `exists()` returns `True` when a matching row is in the DB.
- Test `exists()` returns `False` when no matching row exists.
- Test that the old `AttributeError` is NOT raised (i.e., the method is callable at all).
- Use the in-memory SQLite engine and `Base.metadata.create_all` from the conftest fixture (step 3).

### 3. Fix Bug 3 — Import-time side effects (`session.py` + `worker/config.py`)

This is the prerequisite for a clean test suite. Both files run code with external side effects at import time.

#### `app/database/session.py` (line 15)

**Current broken code:**
```python
engine = create_engine(DatabaseUtils.get_connection_string())       # side effect at import
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

**Fix:** make engine creation lazy; keep `Base` at module level (it has no side effects):
```python
Base = declarative_base()

_engine = None

def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DatabaseUtils.get_connection_string())
    return _engine

def db_session() -> Generator:
    session: Session = sessionmaker(
        autocommit=False, autoflush=False, bind=_get_engine()
    )()
    try:
        yield session
        session.commit()
    except Exception as ex:
        session.rollback()
        logging.error(ex)
        raise ex
    finally:
        session.close()
```

Remove the module-level `engine` and `SessionLocal` names. Verify that `alembic/env.py` still works (it imports `Base` from `database.session` — that import must keep working; it uses `engine_from_config` for its own engine, so removing module-level `engine` does not break it).

#### `app/worker/config.py` (lines 45–46)

**Current:**
```python
celery_app = Celery("tasks")
celery_app.config_from_object(get_celery_config())
```

`config_from_object(get_celery_config())` calls `get_redis_url()` which reads env vars at import time. If `REDIS_URL` and `PROJECT_NAME` are unset, this produces a malformed broker URL silently.

**Fix:** pass config directly through the Celery constructor so the object is self-contained and readable, while keeping the module-level `celery_app` name that the rest of the app imports:
```python
celery_app = Celery(
    "tasks",
    broker=get_redis_url(),
    backend=get_redis_url(),
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)
celery_app.autodiscover_tasks(["worker"], force=True)
```
`get_redis_url()` still reads env vars, but the `pytest.ini` `[env]` block sets `REDIS_URL` and `PROJECT_NAME` before test collection, so this is safe in tests. The `Celery(...)` constructor does not attempt a connection — it configures an object. No behavioral change in production.

**After both fixes:** Expand `tests/conftest.py` with working fixtures:
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.session import Base

@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()
```
Verify: `uv run pytest --collect-only` still exits clean (no import errors, no connection attempts).

### 4. Fix Bug 2 — Ghost row in `app/api/endpoint.py`

**Location:** `app/api/endpoint.py:66–70`

**Current broken code:**
```python
repository.create(obj=event)          # commits to DB immediately
task_id = celery_app.send_task(        # if this raises, the row is orphaned
    "process_incoming_event",
    args=[str(event.id)],
)
```
`GenericRepository.create()` calls `session.commit()` before `send_task`. If `send_task` raises (Redis unavailable, etc.), the committed row is orphaned — no task will ever process it.

**Fix:** Stage the row without committing, attempt `send_task`, then commit only on success:
```python
# Stage the event row (no commit yet)
event = Event(data=raw_event, workflow_type=get_workflow_type())
repository.session.add(event)
repository.session.flush()   # assigns event.id without committing

# Enqueue — if this fails, the session rolls back (no orphan)
task_id = celery_app.send_task(
    "process_incoming_event",
    args=[str(event.id)],
)
# Commit only after task is enqueued successfully
repository.session.commit()
```
The session's `db_session()` generator already handles rollback on exception — so if `send_task` raises, the session rolls back automatically and the row is never persisted.

**Note:** This changes the semantics of `repository.create()` for the endpoint. The endpoint now bypasses `GenericRepository.create()` and manages the session directly. That's intentional — this endpoint has a two-phase commit need that the generic method doesn't model.

**Write the test** at `tests/api/test_endpoint.py`:
- Mock `celery_app.send_task` to raise an exception.
- POST a valid event payload to `/`.
- Assert the response is a 500 (or whatever the endpoint propagates).
- Assert the `Event` table is empty (no ghost row committed).
- Separately, mock `send_task` to return a fake task ID and assert the row IS committed.
- Use FastAPI `TestClient` with an overridden `db_session` dependency that points at the in-memory SQLite engine.

### 5. Fix Bug 4 — Router key coupling (silent misses on missing node outputs)

**Location:** `app/core/task.py` (additive fix) and any new router nodes going forward.

**Problem:** Router nodes look up upstream node outputs via hard-coded dict keys:
```python
output = task_context.nodes["FilterSpamNode"]["result"].output
```
If `"FilterSpamNode"` is missing (e.g., wrong workflow ordering), this raises a raw `KeyError: 'FilterSpamNode'` — which the `BaseRouter.route()` loop does NOT catch. The error propagates with no context about *which router* needed it or *what workflow ordering is wrong*.

**Fix (additive — does not break existing code):** Add a `get_node_output()` helper to `TaskContext` in `app/core/task.py`:
```python
def get_node_output(self, node_name: str) -> Any:
    if node_name not in self.nodes:
        raise KeyError(
            f"Router expected output from node '{node_name}', but it has not run. "
            f"Nodes completed so far: {list(self.nodes.keys())}. "
            f"Check that '{node_name}' appears before the router in the WorkflowSchema."
        )
    return self.nodes[node_name]
```
**Do NOT modify existing `customer_care` router nodes** — they are reference-only. New router nodes (starting with Project A) use `task_context.get_node_output("NodeName")` instead of direct `task_context.nodes["NodeName"]` access.

**Write the test** in `tests/core/test_task.py`:
- Call `get_node_output("MissingNode")` on a `TaskContext` with no nodes — assert a `KeyError` is raised.
- Assert the error message contains the missing node name.
- Assert the error message lists the available nodes.
- Call `get_node_output("PresentNode")` on a context where that node exists — assert the correct value is returned.

### 6. Write `TaskContext` and `WorkflowSchema` unit tests

Create `tests/core/test_task.py` (expanding the file started in step 5):
- `TaskContext` creation with `event`, `nodes`, `metadata`.
- `update_node(name, **kwargs)` — single key, multiple keys, merging into an existing key.
- `get_node_output()` — covered in step 5.

Create `tests/core/test_schema.py`:
- `NodeConfig` — default values (`connections=[]`, `is_router=False`), override values.
- `WorkflowSchema` — create with stub `Node` subclasses; assert `start`, `nodes`, `event_schema` are set correctly.
- `WorkflowSchema` with `is_router=True` on a node — assert the flag is stored.

### 7. Write `WorkflowValidator` unit tests

Create `tests/core/test_validate.py`. Use minimal stub `Node` subclasses (3–4 lines each, no logic — just satisfy the `Node` ABC) defined in the test file or a `tests/core/fixtures.py`.

Tests to cover:
- **Valid linear workflow** — A → B → C; `validate()` raises no error.
- **Cycle detection** — A → B → A; assert `ValueError` with "cycle" in the message.
- **Unreachable node** — A → B declared, C declared but not reachable from A; assert `ValueError` with "unreachable" in the message.
- **Non-router with multiple connections** — A declared with `connections=[B, C]` and `is_router=False`; assert `ValueError`.
- **Router node with multiple connections** — A declared with `connections=[B, C]` and `is_router=True`; assert no error.
- **`_has_cycle()`** — call directly; assert `True` for a cyclic graph, `False` for an acyclic graph.
- **`_get_reachable_nodes()`** — call directly; assert the returned set matches expected reachable nodes.

### 8. Write `Workflow.run()` unit tests

Create `tests/core/test_workflow.py`. Build a minimal concrete `Workflow` subclass in the test (or in a test fixtures module) using stub node classes that write predictable values to `task_context`.

Tests to cover:
- **Linear pipeline** — three stub nodes in sequence; assert each node's output is in `task_context.nodes` at the end, in the correct order.
- **Router workflow** — a router node that reads from the prior node's output and branches; assert only the correct branch node ran.
- **Schema-level `event_schema` parsing** — pass a raw dict as the event; assert `task_context.event` is the parsed Pydantic schema object after `run()`.
- **`node_context` logging** — assert that node start/finish log messages are emitted (use `caplog`).
- **Node exception propagates** — a node that raises `RuntimeError`; assert the exception propagates out of `run()`.
- **`metadata["nodes"]` is cleaned up** — assert `task_context.metadata` does not contain `"nodes"` after `run()` completes.

### 9. Write `BaseRouter` and `RouterNode` unit tests

Create `tests/core/test_nodes_router.py`.

Tests to cover:
- **`BaseRouter.process()`** — assert it calls `route()` and writes `{"next_node": <name>}` to `task_context.nodes`.
- **`BaseRouter.route()` — first-match wins** — two `RouterNode`s where both could match; assert the first one's return value is used.
- **`BaseRouter.route()` — fallback** — no routes match; assert `fallback` node is returned.
- **`BaseRouter.route()` — no fallback, no match** — assert `None` is returned.
- **`RouterNode.determine_next_node()` returns `None`** — assert `route()` skips it and tries the next.
- **`KeyError` from a missing node key propagates** — a `RouterNode` that calls `task_context.get_node_output("Missing")`; assert `KeyError` with a clear message propagates (not swallowed by `route()`).

### 10. Write `ParallelNode` unit tests

Create `tests/core/test_nodes_parallel.py`. Read `app/core/nodes/parallel.py` first to understand the current implementation.

Tests to cover:
- All parallel nodes run (mock each to write a unique key to `task_context`; assert all keys present after `execute_nodes_in_parallel()`).
- Parallel execution is actually concurrent (use `threading.Event` or timing to verify nodes overlap).
- A node that raises in a parallel context — assert the exception propagates.

Note: The known gap (parallel nodes write to shared `task_context` directly, results list is discarded) is **not fixed here** — that fix is intentionally deferred to Project E where parallelism is genuinely first needed. Write a test that **documents the current behavior** with a comment noting "fixed in Project E" — so the regression is caught when E lands.

### 11. Write `PromptManager` service tests

Create `tests/services/test_prompt_loader.py`. Use a temporary directory with a fixture `.j2` file — do not depend on the real `app/prompts/` files.

Tests to cover:
- `get_prompt("template_name", var=value)` renders the Jinja2 template correctly with variables substituted.
- A template with YAML frontmatter — assert frontmatter is parsed separately from the body (if `PromptManager` exposes frontmatter metadata).
- A missing template name — assert a clear `FileNotFoundError` or `KeyError`.
- A template with a missing variable — assert Jinja2 raises `UndefinedError` (not a silent empty string).

### 12. Write `GenericRepository` CRUD tests

Expand `tests/database/test_repository.py` (started in step 2) with the full CRUD suite. Use the in-memory SQLite engine and a minimal model (define a simple `TestModel` in the test file — do not use `Event` for unit tests).

Tests to cover:
- `create()` — assert the object is committed and returned with an `id`.
- `get(id)` — returns the object; returns `None` for a missing id.
- `get_all()` — returns all rows; returns `[]` for an empty table.
- `update()` — assert the field change is persisted.
- `delete(id)` — assert the row no longer exists.
- `get_latest(n)` — assert the `n` most recent rows are returned in descending order.
- `count()` — assert correct count before and after inserts.
- `exists(**kwargs)` — `True` for a matching row (the fixed bug from step 2); `False` for no match; `True` for a partial-key match; `False` after the row is deleted.

### 13. Prepare the LinkedIn visibility post
The Block C visibility task: a post on testing agentic systems — "why an untested orchestration core is a liability, the four bugs, how you closed them." Draft the post now while the bugs are fresh. Frame it around the four concrete bugs and what each one could have caused in production. Use the public-narrative rule: subject-on-you throughout, no company names.

This is a ~30-minute drafting task, not a full write. Save the draft to a `planning/` scratch file if needed. Publish after validation confirms all tests pass.

### 14. Validate
- Run the Validation Commands below and confirm all pass.
- `pytest --collect-only` — confirm all tests are collected with no import errors.
- `pytest -v` — all tests pass, zero failures, zero errors.
- Manually verify that importing `database.session` in a Python shell (with no DB available) no longer raises a connection error.
- Manually verify that importing `worker.config` works cleanly with `DATABASE_URL=sqlite:///:memory: PROJECT_NAME=test REDIS_URL=redis://localhost/0` set.

---

## Acceptance Criteria
- `uv run pytest` passes with **zero failures and zero errors**. All four bug fixes have specific regression tests that would have caught the original bugs.
- `pytest --collect-only` exits with zero errors — no import-time connection attempts, even without Postgres or Redis running.
- `GenericRepository.exists()` no longer raises `AttributeError` on SQLAlchemy 2.x; the fix is covered by a test.
- Ghost-row regression test: mocking `send_task` to raise → `Event` table remains empty after the request (no committed orphan).
- `TaskContext.get_node_output("MissingNode")` raises `KeyError` with a message that names the missing node and lists available nodes.
- `WorkflowValidator` raises `ValueError` on cycles; raises `ValueError` on unreachable nodes; passes on a valid DAG.
- `Workflow.run()` correctly passes `TaskContext` through a linear chain and a router branch in tests.
- `ParallelNode` test documents the current behavior (shared-context mutation) with a "fixed in Project E" comment.
- `PromptManager` tests pass against a fixture template without touching real prompt files.
- `GenericRepository` all-CRUD tests pass using in-memory SQLite.
- `uv run pylint app/` exits clean (no new errors introduced by the four fixes).
- `customer_care` workflow files are untouched — no new tests reference them.

---

## Validation Commands
```bash
uv run pytest --collect-only
uv run pytest -v
uv run pylint app/
cd app && uv run python -c "from main import app"
cd app && uv run python -c "from worker.config import celery_app"
cd app && uv run python -c "from database.session import Base, db_session"
cd app && uv run python -c "from database.repository import GenericRepository"
```

---

## Notes
*(filled in as work happens)*
