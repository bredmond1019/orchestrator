# Migration Plan: Harvesting PyAgent into the Orchestration System

**Source:** `/Users/brandon/Dev/potential-portfolio-projects/PyAgent` (`agent_lib/`)
**Target:** `/Users/brandon/Dev/agentic-portfolio/python-orchestration-system` (`app/`)
**Date:** 2026-06-17

## TL;DR

PyAgent is 128k lines generated in 2 days. Most of it is bulk: 2–4k-line "agent"
files, many running on simulated/dummy data. **Do not port the engine.** This
target *already has* its own DAG validator (`app/core/validate.py`), `TaskContext`
(`app/core/task.py`), node/router system (`app/core/nodes/`), and persistence
(`GenericRepository`). PyAgent's `workflow_engine`/`workflow_dag`/`agent_registry`
would duplicate or fight what exists here.

The genuinely additive material is a **small set of self-contained utilities**
plus a handful of **real (non-dummy) API client classes**. Everything worth taking
is listed below in priority order. Each item notes *why it helps here*, the source
path, the test path, and how it lands in our layout.

Our house rules apply to everything we copy: rewrite to Python 3.10+ typing
(`list[T]`, `X | None`, `StrEnum`), module docstring on line 1, `raise ... from e`,
no f-strings in logging, prompts stay in `.j2`. PyAgent uses old `typing.List`/
`Optional` and MIT license headers on every file — strip the headers, modernize the
types on the way in.

---

## Tier 1 — Take these (high value, self-contained, fills a real gap)

### 1. Safe expression evaluator
- **Source:** `agent_lib/core/safe_expression_evaluator.py` (428 lines)
- **Why it helps:** Our routers (`app/core/nodes/router.py`) are fully imperative —
  every routing decision is hand-written `determine_next_node` Python. This is an
  AST-allowlist evaluator (`ast` + `operator`, no `eval`) that lets routing/branch
  rules be expressed as *data* (`"score > 0.8 and category == 'urgent'"`) evaluated
  against a context dict. Lets us add declarative routers without opening an `eval`
  hole.
  ```python
  # allowlists ast.Add/Sub/Compare/BoolOp..., rejects calls, imports, attribute access
  SAFE_OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ...}
  ```
- **Tests:** No dedicated test file in source; exercised via
  `tests/unit/test_workflow_engine.py` and `tests/integration/test_workflow_*`.
  **Action: write a fresh focused unit test** — this is exactly the kind of
  security-sensitive code our "every workflow ships with tests" rule covers.
- **Lands as:** `app/core/safe_expression.py` (utility, no deps on PyAgent).

### 2. Correlation ID propagation
- **Source:** `agent_lib/core/correlation.py` (650 lines — trim to the core ~200)
- **Why it helps:** We are FastAPI → Celery → workflow nodes and currently have
  **no correlation/trace ID** threading those hops (confirmed: `grep correlation
  app/` is empty). This is a `contextvars.ContextVar`-based correlation system with
  helpers that are tailor-made for our topology:
  ```python
  extract_correlation_headers(headers)   # read X-Correlation-ID at the API edge
  inject_correlation_headers(headers)    # forward it on outbound calls
  ```
  Set the id in the FastAPI endpoint, stuff it into the Celery task kwargs/event,
  re-bind it in the worker, and every node log line is traceable end-to-end.
- **Tests:** `tests/unit/core/test_correlation.py` — port alongside the module.
- **Lands as:** `app/core/correlation.py`. **Adaptation required:** `contextvars`
  does not cross the Celery process boundary automatically — propagate the id
  explicitly through `send_task` (it belongs in the event payload / task headers),
  then re-enter the context in the worker. Don't assume the async-only flow works
  as-is under Celery.

---

## Tier 2 — Evaluate, then take the idea (maybe the code)

### 3. Declarative workflow conditions
- **Source:** `agent_lib/core/workflow_conditions.py` (620 lines)
- **Exports:** `ComparisonOperator`, `LogicalOperator`, `Condition`,
  `ConditionalBranch`, `LoopCondition`, `ConditionEvaluator`, `BranchingExecutor`
- **Why it helps:** Pairs with #1 to give routers a structured rule model
  (`Condition(field="score", op=GT, value=0.8)`) instead of bespoke Python per
  router. Good fit for a future data-driven router node alongside the existing
  imperative `BaseRouter`.
- **Caution:** `BranchingExecutor` assumes PyAgent's workflow engine — **leave it
  behind.** Take only `Condition` / `ConditionEvaluator` / the operator enums and
  wire them to *our* `TaskContext`. Rewrite `class Foo(str, Enum)` → `StrEnum`.
- **Tests:** covered indirectly in `tests/unit/test_workflow_engine.py`; write our
  own against `TaskContext`.
- **Lands as:** part of `app/core/conditions.py` (only if we decide declarative
  routing earns its keep — otherwise skip and keep routers imperative per the
  existing pattern).

### 4. Structured exception taxonomy + correlation
- **Source:** `agent_lib/core/exceptions.py` (484 lines)
- **Why it helps:** A clean exception hierarchy (`AgentException` base with
  `correlation_id`, structured `to_dict()`, an `ErrorHandler`, `generate_correlation_id`).
  If we adopt #2, a correlation-aware base error that serializes cleanly to a FastAPI
  JSON response is a natural companion.
- **Caution:** Much of it is agent-lifecycle-specific (`AgentStartupError`,
  `AgentResourceError`) and irrelevant here. Cherry-pick the base class + correlation
  plumbing + `ErrorHandler`; drop the agent-lifecycle subclasses.
- **Tests:** `tests/unit/core/test_exceptions.py`.
- **Lands as:** `app/core/errors.py` (only the generic pieces).

### 5. Input validation
- **Source:** `agent_lib/core/input_validation.py` (636 lines)
- **Exports:** `ValidationLevel`, `ValidationRule`, `ValidationResult`,
  `InputValidator`, `create_mcp_parameter_validator()`
- **Why it helps:** Reusable rule-based validator with sanitization (useful at the
  API event boundary for fields Pydantic can't express, e.g. injection-pattern
  scrubbing).
- **Caution:** We already validate events with Pydantic schemas
  (`app/schemas/*_schema.py`). This is only worth taking for the *sanitization*
  helpers, not as a parallel validation framework. **Likely skip** unless a concrete
  need appears. The `_mcp_` factory is irrelevant (we're not MCP).
- **Tests:** `tests/unit/core/test_validation.py`.

---

## Tier 3 — Real API clients (take per-need, only if we build matching nodes)

PyAgent's "agent" files are mostly bloat, **but each contains one genuinely real
`aiohttp` API client class** (the rest of the 2–4k lines is dummy-mode fallbacks,
enums, and templated MCP handlers). If/when we build a workflow node that talks to
one of these services, lift *only the client class*, drop it into `app/services/`
(where `article_extraction_service`, `search_service`, etc. already live), and
wrap it in a node. Do **not** port the agent wrapper.

| Service | Real client class | Source path:line | Source test |
|---|---|---|---|
| Notion | `NotionAPIClient` | `agent_lib/integrations/notion/agent.py:301` | `agent_lib/integrations/notion/test_notion_agent.py` |
| GitHub | `GitHubAPIClient` | `agent_lib/integrations/github/agent.py:284` | `agent_lib/integrations/github/test_github_agent.py` |
| Slack | `SlackAPIClient` | `agent_lib/integrations/slack/agent.py:272` | — |
| Google Drive | `GoogleDriveAPIClient` | `agent_lib/integrations/google_drive/agent.py:427` | `agent_lib/integrations/google_drive/test_google_drive_agent.py` |
| Shortcut | `ShortcutAPIClient` | `agent_lib/integrations/shortcut/agent.py:490` | — |
| HelpScout | `HelpScoutAPIClient` | `agent_lib/integrations/helpscout/agent.py:468` | — |

**Quality note:** Notion is the best-built of the six (real client + a
`DummyNotionAPIClient` fallback for credential-less runs, clean `request()` method
with rate-limit handling at `agent.py:353`). The others follow the same shape but
are less exercised. Read the `request()`/auth method of any client before trusting
it; verify it actually hits the live API and isn't routed through a dummy path.

---

## Do NOT migrate (duplicates our core or is dead weight)

| PyAgent area | Reason |
|---|---|
| `core/workflow_engine.py`, `workflow_dag.py`, `workflow_state.py` | We already have `app/core/workflow.py` + `validate.py` (DAG + cycle/reachability checks) + `TaskContext`. Direct duplication. |
| `core/workflow_versioning.py`, `workflow_persistence.py`, `workflow_debugger.py` | Parallel persistence/versioning; conflicts with our `GenericRepository` + Alembic. |
| `core/agent_registry.py`, `registry_events.py`, `repository.py` | We have `app/workflows/workflow_registry.py` and `app/database/repository.py`. |
| `shared/base_agent.py` (1229 lines) + `agent_health.py` + `ResourceManager` | Our execution model is Celery workers, not long-lived self-monitoring agents. Health/resource tracking is the worker's job. |
| `core/mcp_protocol.py`, `mcp_validation.py`, `mcp_interfaces.py` | We are event-driven HTTP (FastAPI), not MCP/JSON-RPC. Only revisit if we ever expose an MCP surface. |
| `project_management/*`, `control/*`, `content/*` agents | Heavily simulated (`task_execution/agent.py:539` literally returns fake test results; `sprint/agent.py` fabricates velocity with `random.uniform`). No reusable value. |
| All 18 root `.md` reports + 11 root `test_*.py` scripts | AI process artifacts / redundant smoke scripts. Ignore. |

---

## Suggested order of work

1. **#2 Correlation IDs** — biggest real gap, clear payoff for observability across
   API→Celery→nodes. Port module + `test_correlation.py`, adapt for the Celery
   boundary, add an endpoint + worker re-bind.
2. **#1 Safe expression evaluator** — small, safe, unlocks declarative routing.
   Port + write a dedicated unit test.
3. **#3 Conditions** *(optional)* — only if we commit to a data-driven router node;
   otherwise keep routers imperative per the frozen `customer_care` pattern.
4. **#4 Errors** *(optional)* — fold correlation-aware base error into our API error
   responses if #2 lands.
5. **Tier 3 clients** — strictly on-demand, one at a time, when a node needs it.

## Verification before reusing anything

- Each Tier 1/2 file's PyAgent imports are within `agent_lib.core.*` and small —
  pull the dependency closure, don't drag in `base_agent`.
- Re-run the ported test against the copied module before wiring it into `app/`.
- Modernize types and strip MIT headers to satisfy `ruff`/`pylint` on the way in.
- Honor the standing rule: anything we add ships with tests.
