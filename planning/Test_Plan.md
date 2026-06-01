# Test Plan — Option A
## Core Engine + Infrastructure Coverage, Then Per-Project Tests

*Rewritten: May 2026 · Scope decision: Option A*
*Supersedes the original full-sweep plan. The Customer Care workflow is reference-only and is **not** tested.*

---

## 1. Scope & Philosophy

**What this plan covers:** the parts of the codebase that *every future workflow depends on* — the core engine, the database layer, the API layer, the worker, and the shared services. Plus the four known production bugs.

**What this plan deliberately excludes:** the Customer Care workflow and every node used only by it (`FilterSpamNode`, `ValidateTicketNode`, `DetermineTicketIntentNode`, `GenerateResponseNode`, `SendReplyNode`, `CloseTicketNode`, `EscalateTicketNode`, `ProcessInvoiceNode`, the three routers, `CustomerCareEventSchema`, and the customer-care `.j2` prompts). That code is a **reference implementation you will not extend**, so testing it spends effort on disposable code.

**The governing principle:** lock down the foundation everything is built on, fix the latent bugs, then adopt a standing rule — **every new workflow (Projects A–G) ships with its own tests.** You learn the testing patterns by testing code you'll *keep*, not the throwaway example.

**Division of labor:** most test-writing is handed to **Claude Code** and supervised/validated by you. Reviewing and validating agent-written tests is itself an agentic-engineering skill worth building deliberately — treat the supervision time as part of the learning, not overhead.

---

## 2. The Four Bugs to Fix (Highest Priority)

These are documented, latent production failures in the existing code. They are not "coverage" — they will bite during a real engagement if left in place. Fix each, and write the test that pins the fix.

1. **`GenericRepository.exists()` AttributeError.** `self.model.query.filter_by(**kwargs).exists()` raises in production. Fix the implementation; test asserts it returns a correct boolean against the in-memory DB.

2. **Ghost-row inconsistency.** `GenericRepository.create()` commits the `Event` row *before* `celery_app.send_task()` is called. If `send_task` fails, a persisted row has no worker processing it, silently. Fix the ordering (or add compensation); test simulates a `send_task` failure and asserts no orphaned committed row (or that it's marked/handled).

3. **Import-time side effects.** `database/session.py` calls `create_engine()` and `worker/config.py` instantiates `Celery()` at import time. Any import without correct env vars fails at *collection* time. Neutralized by `pytest-env` setting defaults before import; the fix is verified when `pytest --collect-only` succeeds with zero errors.

4. **Router key coupling.** Routers read hard-coded string keys from `task_context.nodes`; a node rename silently breaks routing with a `KeyError`. *Note:* the specific routers live in customer-care (out of scope), **but the coupling pattern is in the core routing mechanism.** Add a `BaseRouter`-level test that a missing expected key produces a clear, intentional error (not a silent `KeyError`), and adopt the keyed-slot convention going forward. Apply the lesson in every new router you write (Projects C, and any client work).

---

## 3. Test Infrastructure

### 3.1 Packages (add to `pyproject.toml`)

```
pytest>=8.0
pytest-asyncio>=0.23
pytest-mock>=3.12
pytest-cov>=5.0
pytest-env>=1.1          # set env vars before any import — critical for bug #3
httpx>=0.27              # TestClient for FastAPI
factory-boy>=3.3         # model factories
freezegun>=1.4           # freeze time for decay/timestamp tests (vital for Project G)
```

### 3.2 `pytest.ini` / `pyproject.toml` config

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
env =
    DATABASE_HOST=localhost
    DATABASE_PORT=5432
    DATABASE_NAME=test_db
    DATABASE_USER=postgres
    DATABASE_PASSWORD=postgres
    REDIS_URL=redis://localhost:6379/0
    ANTHROPIC_API_KEY=test-key-not-real
    VOYAGE_API_KEY=test-key-not-real
    TAVILY_API_KEY=test-key-not-real
    PROJECT_NAME=test_project
```

`pytest-env` sets these before any module import, neutralizing the `create_engine()` and `Celery()` side effects (bug #3).

### 3.3 Core fixtures (`tests/conftest.py`)

- **`db_engine`** — in-memory SQLite, `Base.metadata.create_all()`, session-scoped.
- **`db_session`** — real `Session` on the in-memory engine, rolled back per test (nested transaction) for isolation.
- **`mock_session`** — `MagicMock` spec'd to `sqlalchemy.orm.Session` for pure unit tests.
- **`mock_celery_send_task`** — patches `celery_app.send_task` → mock with `.id = "test-task-id"`. (Also used to *simulate failure* for bug #2.)
- **`mock_generic_repository`** — patches `GenericRepository` so `.create()` returns a mock `Event` with a known UUID.
- **`mock_agent`** — `MagicMock` replacing `pydantic_ai.Agent`; `.run_sync()` returns a mock with configurable `.output`. **Prevents real network I/O at import** (the AgentNode eager-construction risk).
- **`mock_anthropic_client`** — `MagicMock` replacing `anthropic.Anthropic`; scripts a `tool_use` → `end_turn` sequence for ToolUseNode tests (Project B).
- **`mock_embedding_service`** — returns deterministic fixed-dimension vectors so retrieval/ordering is assertable without Voyage.
- **`reset_prompt_manager`** (autouse for services) — sets `PromptManager._env = None` before/after to avoid singleton contamination.
- **`fastapi_test_client`** — `TestClient(app)` with `db_session` dependency override and `send_task` patched.
- **`task_context_factory`** — callable building a `TaskContext` with pre-populated `nodes` slots, to avoid repetitive construction in routing/node tests.

### 3.4 Shared helpers (`tests/helpers/`)

- **`workflow_builders.py`** — minimal `WorkflowSchema` builders (linear, router, parallel) for validator/workflow tests, independent of any real workflow.
- **`db_factories.py`** — `factory_boy` factory for the generic `Event` model (no customer-care specifics).
- **`node_stubs.py`** — trivial pass-through / fixed-output `Node` subclasses for exercising the engine without real agents.

---

## 4. Test File Structure (Option A)

```
tests/
├── conftest.py
├── helpers/
│   ├── __init__.py
│   ├── workflow_builders.py
│   ├── db_factories.py
│   └── node_stubs.py
│
├── unit/
│   ├── core/
│   │   ├── test_task_context.py          # fields, update_node convention
│   │   ├── test_schema.py                # WorkflowSchema, NodeConfig defaults
│   │   ├── test_workflow_validator.py    # DFS cycles, BFS reachability — all branches
│   │   ├── test_workflow.py              # run(), _get_next_node_class, _handle_router
│   │   ├── test_base_router.py           # route(), missing-key → clear error (bug #4)
│   │   ├── test_parallel_node.py         # execute_nodes_in_parallel; keyed-slot merge
│   │   └── test_agent_node.py            # ModelProvider branches, env handling (agent mocked)
│   ├── api/
│   │   ├── test_endpoint.py              # handle_event branches, get_workflow_type, ghost-row (bug #2)
│   │   └── test_worker_config.py         # get_redis_url, get_celery_config
│   ├── database/
│   │   ├── test_database_utils.py        # get_connection_string
│   │   ├── test_event_model.py           # columns, defaults
│   │   ├── test_repository.py            # all CRUD; the exists() fix (bug #1)
│   │   └── test_db_session.py            # generator branches
│   ├── worker/
│   │   └── test_tasks.py                 # process_incoming_event branches (generic)
│   └── services/
│       ├── test_prompt_manager.py        # all branches, render errors
│       ├── test_embedding_service.py     # Voyage wrapper (client mocked)
│       ├── test_transcript_service.py    # id extraction, chunking (api mocked)
│       ├── test_search_service.py        # Tavily wrapper (client mocked)
│       └── test_chunking_service.py      # overlap/boundary correctness
│
├── integration/
│   ├── core/
│   │   ├── test_workflow_run_integration.py     # linear + router + parallel, real engine, stub nodes
│   │   └── test_parallel_node_integration.py    # ThreadPoolExecutor + keyed-slot merge
│   ├── api/
│   │   └── test_endpoint_integration.py         # TestClient through FastAPI routing
│   ├── database/
│   │   ├── test_repository_integration.py       # CRUD against SQLite (incl. exists())
│   │   └── test_db_session_integration.py       # db_session with FastAPI Depends
│   └── worker/
│       └── test_tasks_integration.py            # process_incoming_event with real SQLite
│
└── e2e/
    ├── conftest.py                              # Celery eager mode, test DB
    └── test_api_to_worker_pipeline.py           # HTTP → DB → Celery(eager) → DB update, stub workflow
```

No `tests/unit/workflows/` for customer-care. Project workflows get their own test directories as they're built (Section 6).

---

## 5. Implementation Order (Phase 0, Foundation Block C)

### Step 1 — Infrastructure (~1–2 days)
Add packages; create `pytest.ini` with env defaults; build `tests/conftest.py` and `tests/helpers/`. **Verify `pytest --collect-only` succeeds with zero errors** — this alone proves bug #3 is neutralized.

### Step 2 — Core engine (~2–3 days)
`test_task_context`, `test_schema`, `test_workflow_validator`, `test_workflow`, `test_base_router`, `test_parallel_node`. The engine is the foundation; everything depends on it being correct. Bug #4's clear-error behavior lands in `test_base_router`.

### Step 3 — Database + API + worker (~2 days)
`test_repository` (the `exists()` fix, bug #1), `test_endpoint` (ghost-row, bug #2), `test_database_utils`, `test_event_model`, `test_db_session`, `test_worker_config`, `test_tasks`. The two production bugs get fixed and pinned here.

### Step 4 — Services (~1–2 days)
`test_prompt_manager`, and the shared services as they're built in Foundation Block D (`embedding`, `transcript`, `search`, `chunking`). `test_agent_node` (provider branches, mocked agent).

### Step 5 — Integration + a single E2E (~2 days)
The integration tests above, plus one E2E proving HTTP → DB → Celery(eager) → DB with a stub workflow. This validates the accept-and-delegate backbone every project rides on.

**Target:** 80%+ coverage on `core/`, `database/`, `api/`, `services/`, and `worker/` (generic paths). Customer-care code is excluded from the coverage target.

---

## 6. The Standing Rule: Every Project Ships With Tests

After Phase 0, the foundation is trustworthy. From **Project A onward**, each new workflow ships with its own tests in a matching directory (`tests/unit/workflows/<project>/`, `tests/integration/workflows/<project>/`). This is the per-project testing discipline that the Projects & Learning Plan refers to.

**Baseline per project:**
- **Node unit tests** — each node's `process()` with the agent/client mocked. Assert it reads the right upstream slot and writes the right output.
- **Routing tests** — every branch of any `RouterNode`, including the fallback and the missing-key clear-error behavior.
- **One workflow integration test** — the full chain on the real engine with agents/clients mocked.
- **Schema validation** — structured `OutputType` accepts valid and rejects invalid.

**Project-specific must-haves:**

| Project | Critical tests beyond the baseline |
|---|---|
| **A — Content Pipeline** | Self-critic→revise linear chain produces a revised artifact; `StorageNode` writes embedding at write time (mock embedding). |
| **B — Research Agent** | The hand-built tool loop: assert it injects tool results, continues on `tool_use`, terminates on `end_turn`, **and halts at `max_iterations`** (use `mock_anthropic_client`). |
| **C — Proposal Generator** | Review→revise routing (pass vs revise); proposal generated in both PT and EN; "one recommendation" enforced. |
| **D — Document Q&A** | `RetrieveChunksNode` ordering by cosine distance (mock embeddings); RAG-vs-session-memory assembled correctly; chunk overlap boundaries. |
| **E — Specialization Refactor** | **`ParallelNode` keyed-slot merge** — both parallel outputs present and combined (this is the bug-fix from Part 1 of the Projects plan, pinned by test). |
| **F — Semantic Search** | Ranking/ordering of artifacts (mock embeddings); synthesis node with mocked agent. |
| **G — Memory System** | **The hardest and most important.** Consolidation output schema validity; **decay function** (`freezegun` to advance weeks, assert `confidence * 0.95**weeks`); **contradiction handling** (old fact's confidence drops, new fact created, **no overwrite**); `MemoryLoaderNode` retrieval ordering. Bad memory output is a silent, trust-eroding failure — test it hard. |

---

## 7. What Success Looks Like

- `pytest --collect-only` passes with zero errors (import side effects neutralized).
- The four documented bugs are fixed and each has a test that fails on the old behavior.
- 80%+ coverage on the foundation (`core/`, `database/`, `api/`, `services/`, `worker/` generic paths).
- No test exists for customer-care code (it's reference-only).
- From Project A on, no workflow merges without its tests — and you can demonstrate, to yourself or a client, that the system is validated. That demonstrable trust is the deliverable.

---

*This plan replaces the original full-sweep test plan. The ~221-test sweep (which was mostly customer-care coverage) is intentionally not pursued. Foundation gets locked down; coverage grows per-project with code you keep.*

*Last updated: May 2026*
