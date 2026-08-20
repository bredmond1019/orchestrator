# CLAUDE.md — Synapse (the Brain repo; formerly `orchestrator`)

**Synapse** is the knowledge layer of Bastion — the corpus, embeddings, structural graph, memory, and
retrieval. It is *not* the orchestrator: `engine-rs` is. Per brain **D52** the name is adopted in
narrative now while block IDs stay `OR.*` and the `brain.toml` slug stays `orchestrator` until one
atomic cross-repo flip (see the `synapse-rename-mechanical-flip-pending` carryover).

Still built on the event-driven pipeline framework: FastAPI → Celery → Workflow DAG → TaskContext.

## THE BOUNDARY TEST — read this before scoping any new work

Brain (Synapse), Engine (engine-rs), or Factory/Doc (mev/okf-core)? Ask in order. Governed by brain **D51** & **D53**; this block is
byte-identical in `core/engine-rs/CLAUDE.md`.

```
THE BOUNDARY TEST — Brain (Synapse), Engine (engine-rs), or Factory/Doc (mev/okf-core)?  Ask in order.

1. Does it need IN-PROCESS access to embeddings, pgvector, brain_edges,
   or the memory tables?                                    YES -> Synapse
2. Does it produce a client- or repo-facing artifact
   (brief, proposal, PDF, PR, code)?                        YES -> engine-rs
3. Is it maintaining the corpus itself (freshness, validation,
   distillation, retrieval quality, scheduled chores)?      YES -> Synapse
4. Does it serialize or write a repo-tracked source document
   (.md with OKF frontmatter)?                              YES -> mev / okf-core (via engine-rs)

TIEBREAKER — if 1 and 2 are both YES, the work is a hybrid.
   SPLIT it at the ingest seam. Never let one repo own both halves.
       engine-rs workflow  --POST /ingest/*-->  Synapse
   engine-rs acquires and reasons; Synapse owns everything behind the endpoint
   (embedding, storage, retrieval, memory, decay).
```

**What this repo keeps:** `DOCUMENT_INGEST`, `DOCUMENT_QA`, `MEMORY_INGEST`, `MEMORY_CONSOLIDATION`,
and the corpus/graph/memory capability itself. **What has left** (per D51, tracked as `OR.X`/
`OR.X2`): all four cuts of `OR.X` have landed (`CUSTOMER_CARE`, the Engine-shaped reference
workflow with no engine-rs counterpart; `RESEARCH_AGENT`; `PROPOSAL_GENERATOR`, whose
`POST /ingest/proposal` contract survives untouched; and `CONTENT_PIPELINE`, including its
telegram integration orphan), and `OR.X2` has landed (the Python `SDLC_FLOW` workflow and
`app/evals/`, with `app/database/eval_record.py` kept — engine-rs owns the `eval_runs`/
`eval_results` tables now — and `app/services/claude_code/` kept, since `AgentNode` still depends
on it). Do not re-add anything shaped like these — fixes only.

## Before you start

- **Strategic context:** `planning/context.md` (read first) → `planning/status.md` (current state)
- **Symlink warning:** the `planning/` directory is actually a local symlink pointing to the company brain repo's `_planning/` vault (e.g. `core/_planning/orchestrator/`). The brain repo is responsible for tracking all planning files under Git. Do not track `planning/` in this project's public Git repository (it is gitignored).
- **Symlink traps:** `rg`/`grep`/`find` are symlink-blind by default — a search that must include `planning/` content needs `-L`/`--follow`. `git mv` fails through the symlink face ("source directory is empty") — move planning files via the real vault path (`.../_planning/<slug>/...`), never via `planning/...`. Planning changes are committed in the brain repo (`agentic-portfolio`) with an explicit pathspec, never in this repo.
- **Role in Bastion:** this repo is the **Brain** — the knowledge layer — of the brain's primary
  program, Bastion. (It was the Engine + Brain half; **D50/D51 divested the Engine role to
  `engine-rs`.**) Cross-repo order + seams are authoritative in the brain
  (`agentic-portfolio/planning/bastion-product/master-plan.md`); current work is
  `planning/master-plan.md` → **Phase S — Synapse consolidation**, with the older Brain-side blocks
  under "Bastion Program Blocks" and `planning/decisions/D36-bastion-engine-brain-role.md`.
- **Architecture reference:** `docs/app-architecture-overview.md`
- **SDLC pipeline config:** `planning/harness.json` — the validation suite the SDLC engines run
  (11 checks, 8 of them gating, externalized via base-template's richer check kinds). This is the
  source of truth for `/test`; keep the lint/test commands below in sync with it. **Caveat:**
  `hooks/pre-push` stage 2 selects checks by their `command` field, so the one gating check that has
  none — `standing-rules`, a `forbidden-pattern-scan` — is silently skipped at push time and runs
  only in the engines' Test stage. A push reporting "7 gated check(s)" is that, not a regression.
- **Decisions log:** `planning/decisions/` (start at `planning/decisions/index.md`) — check before relitigating any settled choice

---

## Standing rules

1. **Every new function, module, or behaviour change ships with tests.** No exceptions — this applies to ad-hoc fixes and one-off changes just as much as formal blocks/tasks. If you add or change code, add or update the tests that cover it. Per-project test requirements are in `planning/master-plan.md` Project Library.
2. **Never hardcode a system prompt in Python.** All prompts are `.j2` files in `app/prompts/`, loaded via `PromptManager`.
3. **The first `OR.X` cut removed the Engine-shaped reference workflow.** Per D51 it had no engine-rs counterpart to wait for, so it was the first divestment. Do not re-add anything shaped like it, and do not treat it as a pattern to copy for new workflows.
4. **New workflows go to `engine-rs`, not here.** Run the boundary test above first. A genuinely Brain-side workflow (one that needs embeddings/pgvector/memory in-process) still uses `app/workflows/<name>_workflow.py` + `app/workflows/<name>_workflow_nodes/` + `app/schemas/<name>_schema.py` via `createworkflow` — but that should be rare. **A hybrid is never built whole here:** engine-rs runs it and hands the artifact over `POST /ingest/*`.
5. **This repo is the Brain; `engine-rs` is the Engine.** Per brain **D42** engine-rs is the graduation target for the Engine layer, and **D50/D51** completed the split: execution workflows, business artifacts, and the SDLC harness are engine-rs's; knowledge, embeddings, the structural graph, memory, and retrieval are this repo's. The **data contract** (`docs/data-contract.md`, D20/D30) is the seam both write — preserve it byte-for-byte, and note that `OR.Q` bumps it with the ingest endpoint. `engine-rs` embeds in `bastion serve` (which reads this repo's contract). This repo also owns the **workspace contract** (`docs/workspace-contract.md`, brain D47) — the shared "knowledge workspace" convention (`OR.C` ⇄ bastion `BA.6.B`: names = `brain.toml` slugs, resolution precedence, OKF corpus rules); bump its version + re-pin `bastion/docs/workspace-contract.md` when any rule changes. (Brain D24/D41; local D6/D36 are narrowed, not deleted.)
6. **Register every new workflow in both registries.** Add the enum member to `app/workflows/workflow_registry.py` AND add the corresponding event schema entry to `app/api/schema_registry.py`. Missing the second step causes the API dispatcher to 422 every request for that workflow. `tests/api/test_endpoint.py::TestSchemaRegistryCompleteness` enforces this automatically.
7. **No deployment logic inside nodes.** This framework is the deployment-agnostic *brain* — it must not know where it runs. The two things that vary by deployment are **injected, never hardcoded**: model choice (per-node `model_provider` config) and persistence (always via `GenericRepository`). The first `if running_locally:` inside a node means two products have started being built. Keep deployment decisions in config and in the shell, never here. (See `planning/decisions/` D16, D18.)
8. **The eval rubric, the validator, the test-runner, and any consolidation prompt are human-owned gates.** If self-improving / agent-contribution features are ever built, agents may *propose* changes to these by PR but never self-approve them, and never author-and-deploy new node code without human review. (See `planning/decisions/` D20. Not in scope until a node library exists to compose over — Phase 3+.)
9. **Seed TaskContext with the real storage structure in tests.** `AgentNode` stores output via `update_node(node_name=..., result=output)`, which produces `{"result": output}` in `task_context.nodes`. Tests that seed an upstream node as `ctx.nodes["X"] = raw_dict` instead of `ctx.nodes["X"] = {"result": raw_dict}` will pass silently (agent is mocked) but prove the wrong key contract. Always mirror what the actual node writes. When in doubt, check the `update_node` call in the source node.
10. **Extract on the second consumer, never on the first.** The shared `app/brain/` service layer is not designed up front — it *accretes*. Each block factors out only the slice its own feature needs (`OR.N1` → `recall`/`walk`/`health`; `OR.Q` → `ingest`; `OR.N2` → `embed`/`stale`), so **no block is a pure refactor and none gates a phase**. Every block must ship something a user or agent can do that they could not do before; if you cannot name that, the block is wrong. Note this is deliberately *not* engine-rs's `EN.4.0` shape — that block generalizes machinery whose consumers are all known and imminent, whereas Synapse's surfaces arrive months apart. (Brain D51.)
11. **Every new `.md` under `docs/` or `planning/` must open with OKF YAML frontmatter.** The governing standard is D27 in the company brain; the canonical authoring guide is `agentic-portfolio/docs/okf-frontmatter.md`. Required fields: `type`, `title`, `description`. Optional but strongly encouraged: `doc_id` (kebab-case, defaults to filename stem), `layer` (closed set: `brain` · `engine` · `factory` · `console` · `surface` · `infra` · `business` · `content` · `meta`), `project` (use `orchestrator` for this repo; omit for cross-cutting docs), `status` (`active` · `draft` · `deprecated` · `superseded` · `archived`), `keywords` (3–7 free-form topic terms), `related` (list of `doc_id`s). Adding a file to a directory requires updating that directory's `index.md`; propagate up the tree if the parent scope changes.

---

## Core hardening (Block C fixed these four production bugs — don't reintroduce them)

These were the documented production bugs; all are fixed and covered by tests. The table now records the **guard to preserve** when you touch the code, not an open TODO.

| Location | Bug that was fixed | Guard to keep |
|---|---|---|
| `database/repository.py` `GenericRepository.exists()` | `self.model.query.filter_by(...).exists()` — SQLAlchemy 1.x, errors on 2.x | uses `self.session.query(self.model).filter_by(**kwargs).first() is not None` |
| `api/endpoint.py` | committed before `send_task`; a `send_task` failure orphaned the row (ghost row) | `session.flush()` (not commit) assigns the id inside the open transaction; `db_session` rolls back if `send_task` raises |
| `database/session.py` | `create_engine(...)` ran at import time | engine is lazy via `_get_engine()` (created on first use, not module load) |
| Router nodes / `core/task.py` | mis-ordered nodes surfaced a raw, silent `KeyError` | router nodes read via `TaskContext.get_node_output()`, which raises a descriptive error naming the missing node and listing completed ones |

Note: `worker/config.py` still constructs `celery_app` at import — that is **intentional and required** (it must be importable as `-A worker.config.celery_app`). What was removed is the config-assembly side effect: Redis URL and Celery settings are now pure functions (`get_redis_url()`, `get_celery_config()`).

---

## Build / test / run

```bash
# Install dependencies (from repo root)
uv sync

# Run the API (from app/)
cd app && uv run uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# Run the Celery worker (from app/)
cd app && uv run celery -A worker.config.celery_app worker --loglevel=info

# Apply DB migrations (from app/)
cd app && alembic upgrade head

# Lint (ruff first — fast; pylint second — deep)
# NOTE: the SDLC pipeline runs these (and more) from planning/harness.json — keep in sync.
# Use `python -m <tool>` so the PROJECT venv's tool runs, not a global uv-tool install
# (a bare `uv run pytest`/`uv run pylint` can resolve to a global tool missing this repo's deps).
uv run python -m ruff check app/ tests/
uv run python -m pylint app/

# Run tests
uv run python -m pytest

# Full Docker stack
cd docker && ./start.sh    # up (reads docker/.env)
cd docker && ./stop.sh     # down

# Refresh the brain corpus (brain_documents) + structural graph (brain_edges) — prefer this
# over running the two underlying scripts by hand; see docs/scripts.md for the full reference.
uv run syn refresh
```

---

## Adding a new workflow

```bash
# From repo root — interactive, prompts for snake_case name
uv run createworkflow
```

This scaffolds:
- `app/workflows/<name>_workflow.py` — Workflow subclass with a stub `WorkflowSchema`
- `app/workflows/<name>_workflow_nodes/__init__.py` + `initial_node.py`
- `app/schemas/<name>_schema.py` — Pydantic event schema

After scaffolding:
1. Fill in the schema fields.
2. Add real nodes under `<name>_workflow_nodes/`.
3. Wire the `WorkflowSchema` (`start`, `nodes`, `connections`).
4. Register in `app/workflows/workflow_registry.py`.
5. Add a `app/prompts/<name>_*.j2` for every system prompt.
6. Write tests before marking the workflow done.

---

## Code style rules (avoid re-introducing lint debt)

- **Module docstrings go on line 1**, before imports — not after them.
- **Use Python 3.10+ type syntax:** `list[T]`, `type[T]`, `X | Y`, `X | None`, `StrEnum` — never `List`, `Type`, `Union`, `Optional`, or `class Foo(str, Enum)`.
- **Never name a parameter `id`** — it shadows the built-in. Use `obj_id` or `record_id`.
- **Sort imports** (stdlib → third-party → local). `ruff --fix` handles this automatically.
- **`open()` always takes `encoding="utf-8"`.**
- **In `except` blocks, always `raise ... from e`** to preserve the exception chain.
- **No f-strings in `logging` calls** — use `logging.info("msg: %s", value)`.

Run `uv run python -m ruff check app/ tests/ --fix` before committing to auto-resolve most violations.

---

## What NOT to touch

- `app/core/commands/` — excluded from ruff and pylint, do not reformat
- `app/alembic/` — migration history, excluded from pylint, never hand-edit generated files

---

## Documentation

Developer reference docs in `docs/`:

| File | Contents |
|---|---|
| [docs/api-reference.md](docs/api-reference.md) | Precise class-level reference for every public abstraction in app/core/, app/database/, app/services/, and app/workflows/ that a developer must understand and subclass when writing a new workflow. |
| [docs/configuration.md](docs/configuration.md) | Complete reference for every environment variable, connection string assembly, and Docker service topology so a developer can configure the stack for local development or a Docker deployment without guessing. |
| [docs/scripts.md](docs/scripts.md) | Reference for every script in `scripts/`: setup, dev server, inspection, and the brain corpus/graph pipeline (`index_brain.py`, `load_brain_edges.py`, `query_brain.py`, the `syn` CLI). |
| [docs/brain-rag.md](docs/brain-rag.md) | The Brain RAG layer end to end: the `BrainDocument`/`BrainEdge` models, `index_brain.py`, the two-stage hybrid retrieval pipeline, age decay, memory expansion, and the answer-time grounding/abstain gate. |

---

## Brain RAG measurement — where the data lives

**`planning/retrieval-eval-runs/` is the RAG observatory. Start at its
[`index.md`](planning/retrieval-eval-runs/index.md) before comparing any two retrieval numbers.**

| Path | What it holds |
|---|---|
| `planning/retrieval-eval-runs/*.json` | Dated golden-set eval runs — the metric time series. Written by `syn eval`. |
| `planning/retrieval-eval-runs/snapshots/` | Corpus + ranking constants + `brain.toml` config + gate status at a point in time |
| `planning/retrieval-eval-runs/query-log/` | Exported `retrieval_queries` rows — **real** traffic, and the only copy that survives a DB reset |
| `planning/artifacts/rag-diagnosis-*.md` and the other `artifacts/*.md` | The written analyses, indexed from the observatory's `index.md` |
| `<HQ>/planning/artifacts/review/runs/<date>/census.json` | System-review census; its `retrieval`/`corpus` blocks are extra time-series points |

**Rules that exist because breaking them has cost real runs:**

1. **Never compare two eval runs without checking the corpus they were measured against.** Run files
   are *not* self-describing — they record metrics but not the corpus fingerprint or the ranking
   constants. `OR.0.C` compared a pre-prune "before" to a post-prune "after" and attributed the whole
   delta to the wrong variable; the same trap voided `OR.0.A`'s sweep, which was measured on a corpus
   that no longer exists.
2. **Re-fingerprint (`brain_documents` count, `brain_edges` count, `max(indexed_at)`) immediately
   before and after every eval run.** If any moves between a control and its arm, that pair is void.
3. **Never modify an existing run file**, and never re-scope a golden-set case to flatter a metric —
   factual path corrections are allowed and go in the case's `notes:` (precedent: `archive-01-rates`).
4. **`syn eval` always writes a tracked run file.** For throwaway experiments use `syn eval
   --no-write` — same scoring and exit-code behaviour, zero files written.
5. **A `python -c` one-liner silently connects to the WRONG (empty) database.** `load_dotenv()`
   resolves `core/.env` (`DATABASE_NAME=orchestration_dev`) only when running a *script file*; with
   `-c` it falls back to `postgres`, which has 0 brain rows. Always put diagnostics in a `.py` file.

<!-- BEGIN:response-style -->
## Response Style

You are read by an operator scanning several concurrent agent sessions. Long prose is the failure
mode, not thoroughness.

1. **First line = the outcome** — what happened, and whether it needs them.
2. **Then the specifics** — bullets, one line each, max ~6. Facts, not narration.
3. **Last line = the ask**, if there is one. One question, answerable in a word.

**Ceiling: 10 lines for a normal turn, 20 for an end-of-run report.** Only depth the operator
explicitly asked for may exceed it.

Durable detail goes to disk — the commands already require that. **Link the path; do not restate
the file.** Lead with failures, blocks, and anything that did not match the ask, in plain words with
the real error text. Cut reasoning narration, unasked-for next steps, and self-assessment.

Full rationale, the complete cut-list, and worked before/after examples: the
**`report-to-the-operator`** skill.
<!-- END:response-style -->
