# Task Breakdown — Phase 1, Project A: Content Pipeline (Tasks 5 & 6)

## Source Spec
`planning/phase1-projectA/tasks.md`

## Goal
Build the `content_pipeline` workflow: a source-routed pipeline that turns a YouTube URL or article URL into a categorized, embedded `LearningArtifact` plus a static-HTML personal digest (always), and — only when `make_blog=true` — a self-corrected blog draft.

> **Scope of this breakdown:** only the two flagged tasks — **Task 5 (Storage node)** and **Task 6 (Blog branch)**. Tasks 1–4, 7, 8 remain as written in the spec.

## How to Use
Work top to bottom. Each sub-step is a single atomic action. Run the inline **Verify** checks as you go — do not batch them at the end. Each check must pass before continuing. **Read the Notes section first** — it documents three framework realities (no constructor injection, the pgvector-on-sqlite test hazard, and the exact upstream-read keys) that determine how these nodes are written and tested.

---

## Steps

### Step 5: Storage node (persist + embed + render)

**Owns:** `app/workflows/content_pipeline_workflow_nodes/digest_renderer.py`, `app/workflows/content_pipeline_workflow_nodes/storage_node.py`, `tests/workflows/test_content_storage_node.py`.
**Depends on:** Task 2 (`LearningArtifact` model + migration), Task 4 (`SummarizerNode` + `SummaryOutput`).

#### 5.1 Create the HTML renderer (pure functions, no DB, no node imports)
**File:** `app/workflows/content_pipeline_workflow_nodes/digest_renderer.py`
**Action:** create. Module docstring on line 1 (per CLAUDE.md). Deliberately dumb static HTML — no JS, no search box, no tagging (D22).
Define:
- `def _esc(text: str) -> str:` — minimal HTML escape (`&`,`<`,`>`,`"`) for interpolated values.
- `def render_artifact_page(artifact: dict, output_dir: Path, category: str) -> Path:`
  - Computes `page_dir = output_dir / category`, `page_dir.mkdir(parents=True, exist_ok=True)`.
  - Writes `page_dir / f"{artifact['artifact_id']}.html"` — a single static page showing `title`, `tl_dr`, `read_time_estimate`, `core_concepts`, `key_insights`, `questions_raised`, `connections_to_my_work`, `further_exploration`, and the `source_url` as a link. Use `open(path, "w", encoding="utf-8")` (CLAUDE.md rule).
  - Returns the written `Path`.
- `def regenerate_category_index(output_dir: Path, category: str) -> Path:`
  - Globs `(output_dir / category).glob("*.html")` excluding `index.html`, sorts, and writes `(output_dir / category) / "index.html"` listing each item as an `<a href>` link (filename → link; title pulled from a sidecar is overkill — link text = filename stem is acceptable for the MVP, or accept a passed-in list — keep it dumb).
  - Returns the written `Path`.
- Type syntax: `Path`, `dict`, `str` per Python 3.10+ (CLAUDE.md). Import `from pathlib import Path`.

#### 5.2 Create the StorageNode
**File:** `app/workflows/content_pipeline_workflow_nodes/storage_node.py`
**Action:** create. Module docstring on line 1.
```
class StorageNode(Node):
    def _persist(self, artifact: LearningArtifact) -> None:
        # The single persistence seam. Uses the SAME pattern the worker uses
        # (db_session factory + GenericRepository) — deployment-agnostic
        # (connection string comes from DatabaseUtils/env), so this satisfies
        # CLAUDE.md rule 7 "persistence always via GenericRepository". Tests
        # monkeypatch THIS method so no real DB is touched. See Notes §1.
        with contextmanager(db_session)() as session:
            GenericRepository(session=session, model=LearningArtifact).create(artifact)

    def process(self, task_context: TaskContext) -> TaskContext:
        summary = task_context.get_node_output("SummarizerNode")["result"].output
        # source metadata: read whichever fetch node ran (see Notes §3)
        fetched = (task_context.nodes.get("FetchTranscriptNode")
                   or task_context.nodes.get("FetchArticleNode") or {})
        embed_text = f"{summary.title}\n{summary.tl_dr}\n{' '.join(summary.core_concepts)}"
        embedding = EmbeddingService().embed_text(embed_text)   # at write time
        artifact = LearningArtifact(
            source_url=task_context.event.url,
            source_type=fetched.get("source_type", "article"),
            title=summary.title,
            category=summary.category,
            tl_dr=summary.tl_dr,
            summary=summary.model_dump(),
            embedding=embedding,
            fetch_status=fetched.get("fetch_status", "ok"),
            make_blog=task_context.event.make_blog,
        )
        self._persist(artifact)
        output_dir = Path(os.getenv("CONTENT_DIGEST_DIR", "./_digest"))
        page = render_artifact_page(
            {**summary.model_dump(), "artifact_id": str(artifact.id),
             "source_url": task_context.event.url},
            output_dir, summary.category)
        regenerate_category_index(output_dir, summary.category)
        task_context.update_node(self.node_name,
            output={"artifact_id": str(artifact.id), "page": str(page),
                    "category": summary.category, "embedded": True})
        return task_context
```
- Imports: `import os`, `from contextlib import contextmanager`, `from pathlib import Path`, `from core.nodes.base import Node`, `from core.task import TaskContext`, `from database.session import db_session`, `from database.repository import GenericRepository`, `from database.learning_artifact import LearningArtifact`, `from services.embedding_service import EmbeddingService`, and `from workflows.content_pipeline_workflow_nodes.digest_renderer import render_artifact_page, regenerate_category_index`. Sort stdlib → third-party → local (ruff `--fix`).
- `embedding` must be set on the artifact **before** `_persist` is called (acceptance criterion: embedding at write time).

#### 5.3 Output directory configuration
**File:** `app/workflows/content_pipeline_workflow_nodes/storage_node.py` (within 5.2).
**Action:** read the output dir from `os.getenv("CONTENT_DIGEST_DIR", "./_digest")` — config-supplied, never a hardcoded deployment path (CLAUDE.md rule 7). Do **not** edit the shared `app/.env.example` here (it is touched by other tasks — keep it out of this task's file set to avoid a merge collision); documenting the var can be folded into Task 7's doc/wrap-up.

**Verify:** `cd app && uv run python -c 'import workflows.content_pipeline_workflow_nodes.storage_node'` → exits 0 (no import error). *(Requires Task 2's `database/learning_artifact.py` and Task 4's `summarizer_node.py` already merged.)*

#### 5.4 Unit tests for StorageNode + renderer
**File:** `tests/workflows/test_content_storage_node.py`
**Action:** create. Module docstring line 1. Use `monkeypatch` and `tmp_path`. **No real DB, no real Voyage call** (see Notes §1, §2).
Fixtures/helpers:
- A `_FakeSummary` Pydantic model (or import the real `SummaryOutput` from Task 4's module) with all `SummaryOutput` fields populated.
- Build a `TaskContext(event=ContentPipelineEventSchema(url="https://x", make_blog=False))`, seed `ctx.nodes["SummarizerNode"] = {"result": MagicMock(output=summary)}` and `ctx.nodes["FetchArticleNode"] = {"source_type": "article", "fetch_status": "ok"}`.
- `monkeypatch.setenv("CONTENT_DIGEST_DIR", str(tmp_path))`.
- `monkeypatch.setattr(EmbeddingService, "embed_text", lambda self, text: [0.1] * 1024)`.
- Capture persistence: `captured = []; monkeypatch.setattr(StorageNode, "_persist", lambda self, art: captured.append(art))`.
Tests (`describe`-equivalent functions):
- `test_persists_artifact_with_1024_dim_embedding` — after `StorageNode().process(ctx)`, `captured[0].embedding` is a list of length 1024 and non-empty.
- `test_embedding_written_at_write_time` — assert the captured artifact already has its `embedding` set when `_persist` receives it (the capture lambda inspects `art.embedding is not None`).
- `test_writes_html_page` — assert `(tmp_path / summary.category / f"{captured[0].id}.html")` exists and its text contains `summary.title`.
- `test_regenerates_category_index` — assert `(tmp_path / summary.category / "index.html")` exists.
- `test_node_output_recorded` — assert `ctx.nodes["StorageNode"]["output"]["embedded"] is True` and carries `artifact_id`.

**Verify:** `uv run python -m pytest tests/workflows/test_content_storage_node.py -q` → all pass, 0 failures.

---

### Step 6: Blog branch (writer → self-critic → revise) + blog router

**Owns:** `app/workflows/content_pipeline_workflow_nodes/{blog_decision_router_node.py, blog_writer_node.py, self_critic_node.py, revise_node.py}`, `app/prompts/{blog_writer.j2, blog_self_critic.j2, blog_reviser.j2}`, `tests/workflows/test_content_blog_branch.py`.
**Depends on:** Task 4 (`SummarizerNode` + `SummaryOutput`).

#### 6.1 Blog writer prompt
**File:** `app/prompts/blog_writer.j2`
**Action:** create. Frontmatter block (`---` … `---`) with `description:` and `author:` (generic placeholder, e.g. `author: Brandon Redmond` — **not** a real employer; mirror `ticket_analysis.j2`'s frontmatter shape). Body = the system prompt: write a blog post in Brandon's voice (clear, builder-practical, subject-on-the-author per the public-narrative rule) from a structured content summary, for `learn-agentic-ai.com`. This voice prompt is a long-term asset reused in Project C — write it well. Keep it a **static** system prompt (no required Jinja variables; the summary arrives via the user prompt).

#### 6.2 Self-critic prompt
**File:** `app/prompts/blog_self_critic.j2`
**Action:** create. Frontmatter + body: critique a draft blog post for clarity, accuracy vs. the source summary, voice consistency, and structure; return concrete issues. Static system prompt.

#### 6.3 Reviser prompt
**File:** `app/prompts/blog_reviser.j2`
**Action:** create. Frontmatter + body: given a draft and a critique, produce a revised draft addressing each issue while preserving the author's voice. Static system prompt.

**Verify:** `cd app && uv run python -c "from services.prompt_loader import PromptManager; [PromptManager.get_prompt(p) for p in ('blog_writer','blog_self_critic','blog_reviser')]"` → exits 0 (templates load + render).

#### 6.4 BlogWriterNode
**File:** `app/workflows/content_pipeline_workflow_nodes/blog_writer_node.py`
**Action:** create. Module docstring line 1. Follow `generate_response_node.py`, but call `run_agent_recorded` (per CLAUDE.md telemetry rule, Notes §4):
```
class BlogWriterNode(AgentNode):
    class OutputType(AgentNode.OutputType):
        title: str = Field(...)
        body_markdown: str = Field(...)
        reasoning: str = Field(...)
    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt=PromptManager().get_prompt("blog_writer"),
            output_type=self.OutputType, deps_type=None,
            model_provider=ModelProvider.ANTHROPIC,
            model_name="claude-sonnet-4-6")     # top-tier on first run-through (D19)
    def process(self, task_context: TaskContext) -> TaskContext:
        summary = task_context.get_node_output("SummarizerNode")["result"].output
        result = self.run_agent_recorded(task_context, summary.model_dump_json())
        task_context.update_node(self.node_name, result=result)
        return task_context
```
Imports mirror `generate_response_node.py` (`from core.nodes.agent import AgentNode, AgentConfig, ModelProvider`, `from pydantic import Field`, `from services.prompt_loader import PromptManager`, `from core.task import TaskContext`).

#### 6.5 SelfCriticNode
**File:** `app/workflows/content_pipeline_workflow_nodes/self_critic_node.py`
**Action:** create, same shape as 6.4.
- `OutputType`: `critique: str`, `issues: list[str]`, `approved: bool`.
- `get_agent_config()` → `PromptManager().get_prompt("blog_self_critic")`, `ModelProvider.ANTHROPIC`, `model_name="claude-sonnet-4-6"`.
- `process()`: read the draft via `task_context.get_node_output("BlogWriterNode")["result"].output`; send `draft.model_dump_json()` as the user prompt through `run_agent_recorded`; store `result=result`.

#### 6.6 ReviseNode
**File:** `app/workflows/content_pipeline_workflow_nodes/revise_node.py`
**Action:** create, same shape.
- `OutputType`: `title: str`, `body_markdown: str`.
- `get_agent_config()` → `PromptManager().get_prompt("blog_reviser")`, `ModelProvider.ANTHROPIC`, `model_name="claude-sonnet-4-6"`.
- `process()`: read both `BlogWriterNode` draft and `SelfCriticNode` critique via `get_node_output(...)["result"].output`; compose a user prompt containing both (`json.dumps({"draft": ..., "critique": ...})` or two `model_dump_json()` blocks); run via `run_agent_recorded`; store `result=result`. This is the terminal node of the blog branch (no further connection).

#### 6.7 BlogDecisionRouterNode
**File:** `app/workflows/content_pipeline_workflow_nodes/blog_decision_router_node.py`
**Action:** create. Follow `ticket_router_node.py`. The router decides whether the blog branch runs at all:
```
class BlogDecisionRouterNode(BaseRouter):
    def __init__(self):
        self.routes = [MakeBlogRouter()]
        self.fallback = None    # digest-only path ENDS here (BaseRouter.route
                                # returns None when no route + no fallback)

class MakeBlogRouter(RouterNode):
    def determine_next_node(self, task_context: TaskContext) -> Node | None:
        if task_context.event.make_blog:
            return BlogWriterNode()
        return None
```
Imports: `from core.nodes.base import Node`, `from core.nodes.router import BaseRouter, RouterNode`, `from core.task import TaskContext`, `from workflows.content_pipeline_workflow_nodes.blog_writer_node import BlogWriterNode`. Use `Node | None` return type (Python 3.10+; the reference file uses `Optional` but CLAUDE.md mandates `X | None` for new code).

**Verify:** `cd app && uv run python -c 'import workflows.content_pipeline_workflow_nodes.blog_decision_router_node'` → exits 0.

#### 6.8 Unit tests for the blog branch
**File:** `tests/workflows/test_content_blog_branch.py`
**Action:** create. Module docstring line 1. Mock agents — **never construct the real pydantic-ai `Agent`** (no API key/network in tests). Use the established no-op-`__init__` pattern from `tests/core/test_nodes_usage.py` (Notes §4):
```
def _make(node_cls, output):
    with patch.object(AgentNode, "__init__", lambda self: None):
        node = node_cls()
    node.agent = MagicMock()
    result = MagicMock(); result.output = output
    result.usage.return_value = MagicMock(input_tokens=1, output_tokens=1)
    node.agent.run_sync.return_value = result
    return node
```
Tests:
- `test_router_routes_to_writer_when_make_blog_true` — `ctx.event = ContentPipelineEventSchema(url="https://x", make_blog=True)`; assert `MakeBlogRouter().determine_next_node(ctx)` is a `BlogWriterNode` instance.
- `test_router_terminates_when_make_blog_false` — `make_blog=False`; assert `BlogDecisionRouterNode().route(ctx) is None`.
- `test_blog_writer_reads_summary_and_records_result` — seed `ctx.nodes["SummarizerNode"] = {"result": MagicMock(output=<summary>)}`; seed `ctx.node_runs["BlogWriterNode"] = NodeRun(status=RUNNING)`; run `process`; assert `ctx.nodes["BlogWriterNode"]["result"].output.body_markdown` is set.
- `test_self_critic_reads_draft` — seed a `BlogWriterNode` draft output; run `SelfCriticNode.process`; assert an `issues`/`approved` result is stored.
- `test_revise_reads_draft_and_critique` — seed both upstream outputs; run `ReviseNode.process`; assert a revised `body_markdown` is stored.

**Verify:** `uv run python -m pytest tests/workflows/test_content_blog_branch.py -q` → all pass, 0 failures.

---

## Acceptance Criteria
*(verbatim from the spec — the criteria these two tasks contribute to)*
- POSTing `{"workflow_type":"CONTENT_PIPELINE","data":{"url":"<youtube-or-article>","make_blog":false}}` to `/events/` runs `SourceRouterNode → fetch → SummarizerNode → StorageNode` and produces a `LearningArtifact` row **with a non-null 1024-dim embedding written at write time** plus a static HTML digest page and a regenerated category index — and the blog nodes do **not** execute.
- With `make_blog=true`, the same chain additionally runs `BlogWriterNode → SelfCriticNode → ReviseNode` (linear, no cycle) and writes a blog draft.
- All prompts are `.j2` files in `app/prompts/` loaded via `PromptManager` — zero prompt strings hardcoded in Python.
- No persistence/session or deployment-path logic lives inside any node (injected repository/services + config-supplied output dir only); `customer_care` is untouched.
- `uv run python -m pytest` passes with **more** tests than before this spec, and the `pytest-count` gate never decreases across tasks.

## Validation Commands
*(verbatim from the spec)*
```
cd app && uv run python -c 'import main'
cd app && uv run python -c 'import worker.config'
cd app && uv run python -c 'import database.session'
cd app && uv run python -c 'import database.repository'
cd app && alembic upgrade head
uv run python -m ruff check app/
uv run python -m pylint app/
uv run python -m pytest --collect-only -q
uv run python -m pytest
```

## Notes
Discoveries made while reading the source — these change how the spec's Tasks 5 & 6 must be implemented:

1. **§1 — There is NO constructor injection seam; the spec's "injected repository, never open a session in the node" is not literally achievable here.** `Workflow.run()` and `_get_next_node_class()` instantiate every node as `node_class()` with **zero arguments** (`app/core/workflow.py`). A node therefore cannot receive a `GenericRepository`/`Session` via its constructor. The deployment-agnostic pattern the codebase actually uses is the one in `app/worker/tasks.py`: `with contextmanager(db_session)() as session: GenericRepository(session, Model)...`. `db_session` pulls its connection string from `DatabaseUtils.get_connection_string()` (env-driven, lazy engine) — so using it inside `StorageNode._persist` is deployment-agnostic and satisfies CLAUDE.md rule 7's "persistence **always via `GenericRepository`**." What rule 7 forbids is a deployment *branch* (`if running_locally:`) or a hardcoded connection string — not using the standard session factory. The `_persist` method is the single seam, kept tiny so tests monkeypatch it.

2. **§2 — pgvector `Vector` columns and the sqlite test DB do not mix; keep StorageNode tests off the real DB.** `tests/conftest.py` builds an in-memory **sqlite** engine and runs `Base.metadata.create_all` over every `Base` model. Task 2's `LearningArtifact` carries a `pgvector.sqlalchemy.Vector(1024)` column, which has no sqlite equivalent. To stay robust: (a) StorageNode tests **monkeypatch `_persist`** (above) so they never create the table or hit Postgres; (b) Task 2's own model test should assert structure via `LearningArtifact.__tablename__` / `__table__.columns` introspection + Python instantiation rather than relying on `create_all` against sqlite. Flag this to Task 2's implementer.

3. **§3 — Exact upstream-read keys.** A node that calls `run_agent_recorded` AND then `task_context.update_node(self.node_name, result=result)` stores **two** keys under `nodes[name]`: `result` (the pydantic-ai result; typed output at `["result"].output`) and `output` (a JSON dict, written by `run_agent_recorded`). Downstream nodes read the **typed** value via `task_context.get_node_output("SummarizerNode")["result"].output` (see `ticket_router_node.py`, `send_reply_node.py`). Non-LLM fetch nodes store plain dicts, so StorageNode reads `task_context.nodes["FetchArticleNode"].get("fetch_status")` directly. Use `get_node_output(...)` (not raw `nodes[...]`) so a mis-ordered graph raises the descriptive error.

4. **§4 — AgentNode telemetry + test construction.** New `AgentNode` subclasses must call `self.run_agent_recorded(task_context, user_prompt)` (not `self.agent.run_sync`) so per-node token/input telemetry is captured (`app/core/nodes/agent.py` docstring; CLAUDE.md / D30). In tests, never let the real `Agent` build (it needs API keys + network): use the `patch.object(AgentNode, "__init__", lambda self: None)` then `node.agent = MagicMock()` pattern proven in `tests/core/test_nodes_usage.py::StubAgentNode`.

5. **§5 — Test-file path correction (parallel-merge safety).** The spec listed per-node tests under `tests/workflows/content_pipeline/` — that directory needs a shared new `__init__.py`, which **multiple parallel tasks would each create → merge collision.** This breakdown instead places each task's test file directly under the existing `tests/workflows/` package with a unique name (`test_content_storage_node.py`, `test_content_blog_branch.py`, and similarly `test_content_fetch_nodes.py` / `test_content_summarizer.py` for Tasks 3/4). No shared `__init__.py` is created. Apply the same correction to Tasks 3 and 4 when they run.

6. **§6 — Router `Node | None` typing.** The reference `ticket_router_node.py` uses `Optional[Node]`, but CLAUDE.md mandates `X | None` for new code. Write `BlogDecisionRouterNode`/`MakeBlogRouter` with `Node | None` to keep ruff/pylint clean. `BaseRouter.route()` already returns `None` when there is no matching route and `fallback is None` — that cleanly ends the run for the digest-only path; no `EndNode` is needed.
```
