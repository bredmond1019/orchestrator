# Task Spec — Phase 1, Block 1 (Project A: Content Pipeline)

## Goal
Build a source-routed content pipeline that ingests YouTube URLs or article URLs, produces a categorized personal digest (always) and a self-corrected blog draft (when `make_blog=true`), storing every item as a `LearningArtifact` with an embedding and a static HTML page served privately by Caddy.

## Context Pointers
- **Master Plan:** Phase 1, Block 1 — Project A (Content Pipeline section)
- **Projects Plan:** Part 3, Project A — full build notes, node sequence, `SummaryOutput` schema, test requirements
- **Projects Plan:** Part 1 — `AgentNode`, `RouterNode`, `PromptManager` component reference
- **Projects Plan:** Part 1, Infrastructure Gaps — `EmbeddingService`, `TranscriptService`, `ArticleExtractionService`, `ChunkingService` (should have been built in Phase 0 Block D)
- **DECISIONS:** D18 (no `if running_locally:` in nodes), D21 (digest-always / blog-on-flag), D22 (static HTML for reading surface), D24 (trafilatura-first / Firecrawl-fallback for article extraction)
- **CLAUDE.md:** no hardcoded prompts (all `.j2`), `createworkflow` scaffolder, register in `workflow_registry.py`, tests ship with every workflow

## Step-by-Step Tasks

### 1. Prerequisites check (Phase 0 Block D artifacts)
Phase 0 Block D should have already scaffolded this workflow and built the shared services. Verify before starting:
- `app/services/embedding_service.py` exists with a working `EmbeddingService` (Voyage AI `voyage-2`).
- `app/services/transcript_service.py` exists with a `TranscriptService` wrapping `youtube-transcript-api`.
- `app/services/article_extraction_service.py` exists with `ArticleExtractionService` (trafilatura default, Firecrawl fallback).
- `app/services/chunking_service.py` exists with a `ChunkingService`.
- pgvector migration exists and has been applied (`CREATE EXTENSION IF NOT EXISTS vector` + vector columns).
- `app/workflows/content_pipeline_workflow.py` (stub) and `app/workflows/content_pipeline_workflow_nodes/` directory exist from the Block D scaffold.
- If any of the above is missing, build it now before proceeding; do not skip ahead.

### 2. Add `LearningArtifact` database model and Alembic migration
- Create `app/database/learning_artifact.py` with a `LearningArtifact` SQLAlchemy model:
  - `id` (UUID, primary key, default `uuid4`)
  - `source_url` (String, not null)
  - `source_type` (String — `"youtube"` or `"article"`)
  - `title` (String)
  - `category` (String — matches the classifier output: `ai_engineering`, `physics_relativity`, `music`, `other`, and anything the summarizer adds)
  - `tl_dr` (String)
  - `summary_json` (JSONB — full `SummaryOutput` as stored JSON)
  - `raw_content` (Text — transcript or extracted article text)
  - `embedding` (Vector(1024) — pgvector column; null until `StorageNode` writes it)
  - `fetch_status` (String — `"ok"` or `"failed"`; `"failed"` rows still persist, embedding stays null)
  - `created_at` (DateTime, default `utcnow`)
- Generate the migration: `cd app && uv run alembic revision --autogenerate -m "add learning_artifact"`.
- Apply: `cd app && uv run alembic upgrade head`.
- Export `LearningArtifact` from `app/database/__init__.py`.

### 3. Scaffold and define the event schema
- If not already scaffolded, run `uv run createworkflow` and name it `content_pipeline`.
- Open `app/schemas/content_pipeline_schema.py` and define `ContentEventSchema`:
  ```python
  class ContentEventSchema(BaseModel):
      url: str
      make_blog: bool = False
  ```
- Confirm `ContentEventSchema` is importable.

### 4. Write prompt templates (`.j2` files — never hardcode prompts in Python)
Write four files under `app/prompts/`. All prompts go in `.j2` files with YAML frontmatter.

- **`content_summarizer.j2`** — system prompt for `SummarizerNode`. Focus: extract structured knowledge from AI/agentic/harness engineering content, physics/relativity, and music. Output a JSON object matching `SummaryOutput` (see step 6). Include guidance on the category taxonomy: `ai_engineering`, `physics_relativity`, `music`, `other`. Spend real time on this prompt — it determines the quality of your feed.
- **`blog_writer.j2`** — system prompt for `BlogWriterNode`. Writes in your voice (EN and PT), aimed at `learn-agentic-ai.com`. This is a **long-term asset** — invest real time on voice. The prompt should make drafts that read like you wrote them. Note: the draft only runs when `make_blog=true`.
- **`self_critic.j2`** — system prompt for `SelfCriticNode`. Evaluates a blog draft against criteria: clarity, voice consistency, accuracy, one strong argument or insight per post, bilingual appropriateness. Returns structured feedback: `pass`/`revise` verdict + specific line-level notes.
- **`revise.j2`** — system prompt for `ReviseNode`. Addresses specific `SelfCriticNode` feedback line-by-line; returns a revised draft. Do not re-critique — just fix.

### 5. Build the fetch nodes
All in `app/workflows/content_pipeline_workflow_nodes/`.

**`FetchTranscriptNode`** — fetches and cleans a YouTube transcript:
- Detects YouTube URLs (handle `youtube.com/watch?v=`, `youtu.be/`, playlists — extract the video ID robustly).
- Uses `TranscriptService` to fetch the transcript.
- Writes to `task_context` under key `"FetchTranscriptNode"`: `raw_content` (str), `source_type="youtube"`, `source_url` (str).
- On failure (video has no transcript, network error): write `fetch_status="failed"`, `raw_content=""` — do not raise. The pipeline continues and `StorageNode` persists the failure row.

**`FetchArticleNode`** — fetches and extracts readable text from an article URL:
- Uses `ArticleExtractionService` (trafilatura default → Firecrawl fallback per D24).
- Writes `raw_content`, `source_type="article"`, `source_url` to context.
- On failure: same as above — write `fetch_status="failed"`, do not raise.
- `FetchArticleNode` is a **Company Brain reuse point** — build it cleanly; the real product ingests client web-based knowledge (help docs, wikis) through this same node.

### 6. Build `SourceRouterNode`
A `RouterNode` subclass that reads the event URL and routes:
- If the URL matches YouTube → `FetchTranscriptNode`.
- Otherwise → `FetchArticleNode`.
- No fallback needed — all non-YouTube URLs go to the article branch.

Detection hint: check for `youtube.com` or `youtu.be` in the URL before instantiating the full fetch logic.

### 7. Define `SummaryOutput` and build `SummarizerNode`
**`SummaryOutput` (Pydantic schema in `app/schemas/content_pipeline_schema.py`):**
```python
class SummaryOutput(BaseModel):
    title: str
    category: str          # ai_engineering | physics_relativity | music | other
    tl_dr: str             # one line for skimming
    read_time_estimate: str  # e.g. "4 min"
    core_concepts: list[str]
    key_insights: list[str]
    questions_raised: list[str]
    connections_to_my_work: list[str]
    further_exploration: list[str]
```

**`SummarizerNode`** (`AgentNode` subclass):
- Reads `raw_content` and `source_type` from context.
- If `fetch_status == "failed"`: write minimal placeholder output and return — do not call the model on empty content.
- Uses `content_summarizer.j2` via `PromptManager`.
- Uses `SummaryOutput` as `OutputType` (structured output via pydantic-ai).
- Provider: `ModelProvider.ANTHROPIC`, model `claude-sonnet-4-6` or `claude-haiku-4-5-20251001` (cheap and fast is fine for a structured-extraction node; note your choice in comments for Project H).
- Writes `SummaryOutput` to context under `"SummarizerNode"`.

### 8. Build `StorageNode`
The most important node — this is where the value accumulates.

**What it does:**
1. **Writes `LearningArtifact` to Postgres** via `GenericRepository`. Fields populated from context: all `SummaryOutput` fields + `raw_content`, `source_url`, `source_type`, `fetch_status`. 
2. **Calls `EmbeddingService`** and writes the embedding to the `LearningArtifact` row. **This must happen for every item, including `make_blog=false` digest-only items.** This is the seed for Projects F and G — deferring it means paying twice.
3. **Writes a static HTML digest page** to a configured output directory (e.g. `~/knowledge-feed/<category>/<slug>.html`). One clean, readable page per item. The HTML should include: title, category badge, tl_dr, read_time_estimate, core concepts, key insights, questions raised, further exploration links.
4. **Regenerates the category index** (`~/knowledge-feed/<category>/index.html`) — a simple reverse-chronological list of items in that category with tl_dr and read_time_estimate visible without clicking.
5. Writes to context under `"StorageNode"`: `artifact_id` (UUID), `html_path` (str), `make_blog` (bool — forwarded from the event for the router downstream to read).

**Notes:**
- The HTML template should be readable on a Pixel phone browser and Kindle experimental browser — no JS, no heavy CSS, minimal dependencies.
- Static HTML path and category set are configurable via env vars, not hardcoded.
- `GenericRepository` is used for all DB writes — no direct session calls in the node.

### 9. Build the blog branch nodes (only runs when `make_blog=true`)

**`BlogBranchRouterNode`** (`RouterNode`) — checks `task_context.nodes["StorageNode"]["make_blog"]`:
- `True` → `BlogWriterNode`.
- `False` (fallback) → `None` (end of workflow).

**`BlogWriterNode`** (`AgentNode`):
- Reads the `SummaryOutput` from context.
- Uses `blog_writer.j2` via `PromptManager`.
- Writes a full blog draft in both EN and PT to context under `"BlogWriterNode"`: `draft_en` (str), `draft_pt` (str).
- Model: `claude-sonnet-4-6` or better — voice quality matters here.

**`SelfCriticNode`** (`AgentNode`):
- Reads both drafts from context.
- Uses `self_critic.j2`.
- Returns `SelfCriticOutput(verdict: "pass" | "revise", feedback_en: str, feedback_pt: str)`.
- Writes to context under `"SelfCriticNode"`.

**`ReviseNode`** (`AgentNode`):
- Reads drafts + critic feedback.
- Uses `revise.j2`.
- Rewrites the draft(s) that need revision; passes through drafts with `"pass"` unchanged.
- Writes revised `draft_en`, `draft_pt` to context under `"ReviseNode"`.
- After `ReviseNode`, a final step writes the draft(s) to disk at a configured blog drafts path (e.g. `~/blog-drafts/<slug>_en.md`, `~/blog-drafts/<slug>_pt.md`).

**Self-critic loop note:** The validator enforces strict DAGs — no cycles. The critic → revise pattern runs **once** as a linear chain. One pass is sufficient for the quality bar here; if quality is not met, revise the prompt, not the loop count.

### 10. Wire `WorkflowSchema` and register
- Open `app/workflows/content_pipeline_workflow.py`.
- Define the full `WorkflowSchema`: `start=SourceRouterNode`, then the node sequence and connections.
  - `SourceRouterNode` → `FetchTranscriptNode` | `FetchArticleNode`
  - Both fetch nodes → `SummarizerNode`
  - `SummarizerNode` → `StorageNode`
  - `StorageNode` → `BlogBranchRouterNode`
  - `BlogBranchRouterNode` → `BlogWriterNode` | (end)
  - `BlogWriterNode` → `SelfCriticNode` → `ReviseNode`
- Register the workflow in `app/workflows/workflow_registry.py` — add a `CONTENT_PIPELINE = "content_pipeline"` entry and wire it to the `ContentPipelineWorkflow` class.
- Add a Celery task in `app/worker/tasks.py` for `content_pipeline` events that mirrors the `customer_care` task pattern.
- Add the `/events/content` endpoint to `app/api/endpoint.py` (or extend the existing generic dispatcher if one exists). The endpoint accepts `ContentEventSchema`, persists to DB, and enqueues via Celery.
- Treat the endpoint as a **product surface** (D16, Layer 3): clean request/response schema, documented, stable.

### 11. Write tests
All in `tests/workflows/test_content_pipeline.py` (and supporting files in `tests/`). Agents are mocked — no live API calls in tests.

**Unit tests (each node in isolation with mocked dependencies):**

- **`SourceRouterNode`:** YouTube URL → routes to `FetchTranscriptNode`; non-YouTube URL → routes to `FetchArticleNode`; edge cases (`youtu.be`, `youtube.com/watch?v=`).
- **`FetchTranscriptNode`:** mock `TranscriptService`; assert `raw_content` written to context and `source_type="youtube"` set; mock a failure → assert `fetch_status="failed"` and no exception raised.
- **`FetchArticleNode`:** mock `ArticleExtractionService`; assert `raw_content` written and `source_type="article"` set; mock a failure → assert `fetch_status="failed"` and no exception raised.
- **`SummarizerNode`:** mock the `AgentNode` LLM call; assert `SummaryOutput` written to context; if `fetch_status="failed"` → assert LLM not called, placeholder written.
- **`StorageNode`:** mock `GenericRepository.create` and `EmbeddingService.embed`; assert (a) `LearningArtifact` row created, (b) embedding written **at write time** (not deferred), (c) HTML file written to the configured path, (d) category index regenerated. Run for both `make_blog=true` and `make_blog=false`.
- **`BlogBranchRouterNode`:** `make_blog=True` → routes to `BlogWriterNode`; `make_blog=False` → routes to end.
- **`BlogWriterNode` / `SelfCriticNode` / `ReviseNode`:** mock LLM calls; assert correct context keys written; assert `"pass"` verdict skips revision; assert `"revise"` verdict triggers `ReviseNode`.

**Integration test (full workflow, all agents mocked):**
- **Path 1 — YouTube digest-only:** POST `{url: youtube_url, make_blog: false}` → assert `LearningArtifact` created with embedding, HTML page written, blog nodes never called.
- **Path 2 — article with blog:** POST `{url: article_url, make_blog: true}` → assert `LearningArtifact` created with embedding, HTML page written, blog draft files written to disk.
- Both integration tests should confirm the full `TaskContext` shape: every expected node key present with the correct fields.

### 12. Validate
- Run the validation commands below and confirm all pass.
- End-to-end smoke test (real services, Docker running): POST a real YouTube URL with `make_blog=false`; inspect the Postgres row and the HTML file on disk.
- Confirm no system prompts are hardcoded in Python — all prompts go through `PromptManager.get_prompt()`.
- Confirm `model_provider` is set via `AgentConfig` on each `AgentNode` subclass — no literal model strings outside config.

---

## Acceptance Criteria
- POST `{"url": "<youtube_url>", "make_blog": false}` → Celery runs the pipeline; a `LearningArtifact` row with a non-null embedding exists in Postgres; a `.html` file exists in the configured digest directory; blog nodes were not called.
- POST `{"url": "<article_url>", "make_blog": false}` → same as above with `source_type="article"`.
- POST `{"url": "<youtube_url>", "make_blog": true}` → all of the above, plus `draft_en.md` and `draft_pt.md` written to the configured blog drafts directory.
- A fetch failure (bad URL, no transcript, extraction error) produces a `LearningArtifact` row with `fetch_status="failed"` and no uncaught exception.
- `LearningArtifact` embedding is written at write time in `StorageNode` for **every** item (including digest-only).
- Static HTML category index is regenerated after every successful `StorageNode` write.
- All four prompt templates are `.j2` files loaded via `PromptManager` — zero hardcoded strings in Python.
- Workflow is registered in `workflow_registry.py` and importable without error.
- `uv run pytest` passes (all new tests green, no regressions).
- `uv run pylint app/` exits clean.

---

## Validation Commands
```bash
uv run pylint app/
uv run pytest
cd app && uv run python -c "from main import app"
cd app && uv run python -c "from worker.config import celery_app"
cd app && uv run python -c "from workflows.content_pipeline_workflow import ContentPipelineWorkflow"
cd app && uv run python -c "from schemas.content_pipeline_schema import ContentEventSchema, SummaryOutput"
```

---

## Notes
*(filled in as work happens)*
