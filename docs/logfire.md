---
type: ExternalSDKReference
title: Logfire Observability Reference
description: How to add Logfire tracing to the orchestration framework — instrumentation setup, pydantic-ai integration, and querying trace data for eval work.
---

# Logfire Observability

Logfire is Pydantic's observability platform (OpenTelemetry-based). The two things that matter for this
project: (1) **instrumentation** — wiring Logfire into FastAPI, Celery, and pydantic-ai so every agent
run produces a trace; (2) **querying** — reading that trace data back via SQL for Project H eval work.

The existing `NodeRun` / `on_progress` observability tracks framework-level state (node status, timing,
token counts per node). Logfire operates at a lower level — it traces the actual pydantic-ai model calls
and tool invocations inside each `AgentNode`, giving you LLM request/response payloads, per-call token
usage, and a visual span hierarchy. The two are complementary.

## When to Add This

Logfire is a **pre-Project H prerequisite**. Project H builds a model eval harness; Logfire provides the
trace store that eval analysis queries against. Add instrumentation before starting H, or whenever live
debugging of agent runs becomes painful.

---

## Instrumentation Setup

### Install Extras

```bash
uv add 'logfire[fastapi,celery,pydantic-ai]'
```

Extras needed: `fastapi` for the API, `celery` for the worker, `pydantic-ai` for agent-run tracing.

### Configure in `app/main.py`

`logfire.configure()` must be called **before** any `instrument_*()` call and before the app starts.
Call it once per process.

```python
import logfire
from fastapi import FastAPI

app = FastAPI()

logfire.configure()                    # always first
logfire.instrument_fastapi(app)        # needs the app instance
logfire.instrument_pydantic_ai()       # traces every AgentNode run
```

### Configure in the Celery Worker

Celery workers are separate processes — each worker needs its own `logfire.configure()`. Add it to
`app/worker/config.py` after the `celery_app` is constructed (not at module level; follow the same
lazy pattern used for Redis/Celery config):

```python
import logfire

logfire.configure()
# No instrument_celery() call needed — logfire captures tasks via FastAPI spans automatically,
# but you can add logfire.instrument_celery() if you want per-task spans.
```

### Environment

Set `LOGFIRE_TOKEN` in `app/.env` (get it from logfire.pydantic.dev after creating a project).
Add `LOGFIRE_TOKEN=` to `app/.env.example`.

---

## What You Get from `instrument_pydantic_ai()`

Each `AgentNode.run()` call becomes a parent span. Under it:
- One child span per LLM request (model, input tokens, output tokens, latency)
- One child span per tool call (tool name, arguments, result)
- Exception spans on failures

This is exactly the data Project H needs for per-model latency and cost comparisons without writing
custom eval storage.

---

## Structured Logging in Nodes

Replace any `logging.*` calls in nodes with Logfire structured logging. Use `{key}` placeholders —
not f-strings — so attributes are queryable:

```python
import logfire

logfire.info('Node {node_name} completed in {duration_ms}ms', node_name=self.name, duration_ms=elapsed)
logfire.exception('Node {node_name} failed', node_name=self.name)  # captures traceback automatically
```

For grouping a node's work into a named span:

```python
with logfire.span('AgentNode {name}', name=self.name):
    result = await self._run_agent(...)
```

---

## Querying Trace Data (Project H / Eval)

Logfire exposes trace data via SQL against a `records` table (DataFusion dialect, Postgres-like).

### REST API

```
GET https://logfire-api.pydantic.dev/v1/query
Authorization: Bearer <read_token>
?sql=<query>&min_timestamp=<iso>&max_timestamp=<iso>
```

Use a **read token** (not the write token set in `LOGFIRE_TOKEN`). Get it from the Logfire project
settings. Store as `LOGFIRE_READ_TOKEN` in `app/.env`.

### Key Schema

```sql
-- records table — spans and logs
start_timestamp    -- when span started
duration           -- seconds (NULL for logs)
span_name          -- low-cardinality label (e.g. 'pydantic_ai.agent.run')
service_name       -- set by logfire.configure(service_name='orchestration')
is_exception       -- boolean
attributes         -- JSON; use ->>'key' to extract
```

### Useful Queries for Eval Work

```sql
-- Token usage per model across all agent runs (last 24h)
SELECT
  attributes->>'gen_ai.request.model' AS model,
  sum(CAST(attributes->>'gen_ai.usage.input_tokens' AS INTEGER)) AS input_tokens,
  sum(CAST(attributes->>'gen_ai.usage.output_tokens' AS INTEGER)) AS output_tokens,
  count(*) AS calls
FROM records
WHERE span_name = 'chat claude-*'
  AND start_timestamp > now() - interval '24 hours'
GROUP BY model
ORDER BY calls DESC
LIMIT 50

-- Slowest agent runs
SELECT span_name, duration, start_timestamp
FROM records
WHERE duration > 5.0
ORDER BY duration DESC
LIMIT 20

-- Recent errors
SELECT start_timestamp, message, exception_type, exception_message
FROM records
WHERE is_exception = true
ORDER BY start_timestamp DESC
LIMIT 20
```

### Python Client (for eval scripts)

```python
import logfire

# Sync
client = logfire.db_api.LogfireQueryClient(read_token="<token>")
result = client.query("SELECT ... FROM records LIMIT 100")

# Async
from logfire.integrations.query_client import AsyncLogfireQueryClient
client = AsyncLogfireQueryClient(read_token="<token>")
```

---

## What NOT to Use

- **`logfire-ui` skill** — Codex Desktop-only browser control skill; irrelevant to the Python app.
- **`pydantic-ai-harness` / `CodeMode`** — collapses tool calls into sandboxed Python via the pydantic-ai
  `Agent` class; conflicts with the node-based DAG architecture.

---

## References

- Logfire docs: https://logfire.pydantic.dev/docs/
- Pydantic skills repo: https://github.com/pydantic/skills
  - `skills/logfire-instrumentation/SKILL.md` — Python/JS/Rust setup guide with ordering rules
  - `skills/logfire-query/SKILL.md` — SQL schema, MCP query tool, REST API client patterns
- Project H spec: `planning/master-plan.md` (model eval harness)
