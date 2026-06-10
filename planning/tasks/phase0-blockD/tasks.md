# Task Spec — Phase 0, Block D

## Goal
Build the shared services layer (embedding, transcript, article extraction, search, chunking, raw tool-use node), enable pgvector, scaffold Project A's workflow structure, and make the FastAPI API contract explicit as a documented product surface.

## Context Pointers
- **Plan section:** `planning/MASTER_PLAN.md` — Foundation Block D
- **Technical detail:** `planning/Agentic_Engineering_Projects_and_Learning_Plan.md` — "Infrastructure Gaps to Close First (Phase 0, Foundation Block D)"
- **Firecrawl decision:** `planning/DECISIONS.md` D24
- **API-as-product-surface:** `planning/DECISIONS.md` D16 (Layer 3)
- **Deployment injection discipline:** `planning/DECISIONS.md` D18 (model provider + persistence injected, never hardcoded)
- **CLAUDE.md standing rules:** tests mandatory; all prompts `.j2` files; no deployment conditionals in nodes; Python 3.10+ type syntax; module docstrings before imports

## Step-by-Step Tasks

### 1. Add New Dependencies
- Add runtime deps with `uv add`:
  - `voyageai` (EmbeddingService)
  - `youtube-transcript-api` (TranscriptService)
  - `trafilatura` (ArticleExtractionService default)
  - `firecrawl-py` (ArticleExtractionService fallback + future CrawlSiteNode)
  - `tavily-python` (SearchService)
  - `anthropic` (explicit pin — transitive via pydantic-ai today, pin it)
  - `pymupdf` (PDF parsing — needed by ChunkingService and Project D)
- Verify `uv run python -c "import voyageai, tavily, trafilatura, anthropic, fitz"` succeeds (fitz = pymupdf)
- Commit `pyproject.toml` and `uv.lock`

### 2. pgvector Migration
- Create an Alembic migration: `cd app && uv run alembic revision --autogenerate -m "enable_pgvector_extension"`
- Edit the generated file to add `CREATE EXTENSION IF NOT EXISTS vector;` in `upgrade()` and its inverse in `downgrade()`
- Verify `cd app && uv run alembic upgrade head` runs without error against the running Postgres
- No model changes yet — vector columns come in Projects A and D when their models are defined

### 3. EmbeddingService
- Create `app/services/embedding_service.py`
- Class: `EmbeddingService`
  - Constructor reads `VOYAGE_API_KEY` from env; model name and dims configurable (defaults: `voyage-2`, 1024)
  - `embed_text(text: str) -> list[float]`
  - `embed_batch(texts: list[str]) -> list[list[float]]`
- Design as a config swap: the provider/model are params so a local embedding model (e.g. Qwen3-Embedding via Ollama) slots in without code changes — this is the seam Project H evaluates
- Export from `app/services/__init__.py`
- Write tests in `tests/services/test_embedding_service.py`: mock the Voyage client; assert correct dims returned; assert batch delegates correctly

### 4. TranscriptService
- Create `app/services/transcript_service.py`
- Class: `TranscriptService`
  - `fetch_transcript(url: str) -> str` — extract video ID from YouTube URL, fetch transcript, return clean joined text
  - `fetch_and_chunk(url: str, chunk_size: int = 500, overlap: int = 50) -> list[str]` — delegates to `ChunkingService` (Task 7) after fetching; returns overlapping token-sized chunks
  - Raises a descriptive error on unsupported URL formats or unavailable transcripts (no silent empty-string returns)
- Export from `app/services/__init__.py`
- Write tests in `tests/services/test_transcript_service.py`: mock `youtube_transcript_api`; assert video ID extraction; assert chunk delegation; assert error on bad URL

### 5. ArticleExtractionService
- Create `app/services/article_extraction_service.py`
- Class: `ArticleExtractionService`
  - `extract(url: str) -> ArticleResult` where `ArticleResult` is a Pydantic model with `text: str`, `title: str | None`, `fetch_status: str` (`"ok"` / `"fallback_used"` / `"failed"`)
  - Default path: `trafilatura.fetch_url` + `trafilatura.extract` — free, local, fast for clean articles
  - Fallback path: Firecrawl `scrape_url` — used when trafilatura returns empty or junk (JS-rendered pages)
  - On total failure: return `ArticleResult(text="", fetch_status="failed")` — never raise, never crash the pipeline; log the failure
  - Firecrawl API key read from `FIRECRAWL_API_KEY` env var; if absent, fallback is disabled silently
  - Do NOT add a `max_calls` guard here — that belongs in the node that calls this service inside an agent tool loop (Project B discipline); the service is stateless
- Export from `app/services/__init__.py`
- Write tests in `tests/services/test_article_extraction_service.py`: mock trafilatura fetch + extract; mock Firecrawl client; assert fallback triggers on empty extraction; assert graceful failure returns `fetch_status="failed"`

### 6. SearchService
- Create `app/services/search_service.py`
- Class: `SearchService`
  - Constructor reads `TAVILY_API_KEY` from env
  - `search(query: str, max_results: int = 5) -> list[SearchResult]` where `SearchResult` is a Pydantic model: `title: str`, `url: str`, `content: str`, `score: float | None`
  - Returns clean structured results suitable for feeding into a tool-use agent loop
- Export from `app/services/__init__.py`
- Write tests in `tests/services/test_search_service.py`: mock Tavily client; assert result schema; assert `max_results` respected

### 7. ChunkingService
- Create `app/services/chunking_service.py`
- Class: `ChunkingService`
  - `chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]` — splits on token boundaries using `tiktoken` (already a dep); produces overlapping chunks
  - `chunk_document(content: bytes, mime_type: str, chunk_size: int = 500, overlap: int = 50) -> list[str]` — dispatches to the right parser: `text/plain` → direct; `application/pdf` → pymupdf (`fitz`) text extraction, then chunk
  - Raise `ValueError` for unsupported `mime_type` with a clear message naming it
- Export from `app/services/__init__.py`
- Write tests in `tests/services/test_chunking_service.py`: plain text produces correct overlap; chunks near the boundary are correct; PDF extraction (mock fitz or use a tiny real PDF fixture); unsupported type raises

### 8. ToolUseNode (raw Anthropic SDK)
- Create `app/core/nodes/tool_use.py`
- Abstract class: `ToolUseNode(Node)`
  - Subclasses define `tools: list[dict]` (Anthropic tool definitions) and implement `handle_tool_call(tool_name: str, tool_input: dict, task_context: TaskContext) -> str`
  - `process(task_context: TaskContext) -> TaskContext` runs the loop:
    ```
    while True:
        response = client.messages.create(model=..., tools=self.tools, messages=messages)
        if response.stop_reason == "end_turn" or iterations >= self.max_iterations:
            break
        # extract tool_use blocks, dispatch to handle_tool_call, append tool_result
    ```
  - `max_iterations: int = 10` (non-optional guard — never infinite)
  - Model read from `TOOL_USE_MODEL` env var (default `claude-haiku-4-5-20251001`) — never hardcoded
  - On `max_iterations` hit: log a warning and return; do not raise (the partial result is still useful context)
- Export from `app/core/nodes/__init__.py`
- Write tests in `tests/core/test_nodes_tool_use.py`: mock `anthropic.Anthropic().messages.create`; assert loop terminates on `end_turn`; assert loop terminates at `max_iterations`; assert `handle_tool_call` is invoked with correct args on `tool_use` stop reason

### 9. Scaffold Project A
- From repo root, run `uv run createworkflow` and enter `content_pipeline` as the workflow name
- This generates:
  - `app/workflows/content_pipeline_workflow.py`
  - `app/workflows/content_pipeline_workflow_nodes/__init__.py`
  - `app/workflows/content_pipeline_workflow_nodes/initial_node.py`
  - `app/schemas/content_pipeline_schema.py`
- **Do not add any logic.** Leave stubs exactly as generated.
- Register the new workflow in `app/workflows/workflow_registry.py` (add `CONTENT_PIPELINE` entry)
- Verify `cd app && uv run python -c "from workflows.workflow_registry import WorkflowRegistry; print(WorkflowRegistry.CONTENT_PIPELINE)"` succeeds

### 10. Clean API Contract
- Update `app/api/endpoint.py` to replace the hardcoded `CustomerCareEventSchema` with a generic event dispatcher:
  - Accept a generic `EventPayload` (Pydantic model with `workflow_type: str` and `data: dict`)
  - Look up the correct schema from a registry mapping `WorkflowRegistry` → schema class; validate `data` against it
  - Raise `422 Unprocessable Entity` with a clear message for unknown `workflow_type`
- Add a `GET /health` endpoint in a new `app/api/health.py` returning `{"status": "ok", "version": "0.1.0"}`
- Add OpenAPI metadata to `app/main.py`: `title`, `description`, `version`
- Ensure all response models are typed Pydantic models, not raw `dict` — the `202 Accepted` response body should have a typed `TaskAcceptedResponse(task_id: str, message: str)` model
- Update `tests/api/test_endpoint.py` to cover: valid dispatch, unknown `workflow_type` → 422, health check → 200

### 11. Validate
- Run the Validation Commands listed below and confirm all pass.

## Acceptance Criteria
- `uv run pytest` passes with all new service and node tests included (no skips)
- `uv run ruff check app/` reports zero errors
- `uv run pylint app/` passes (score ≥ previous baseline — do not regress)
- `cd app && uv run python -c "from main import app"` imports cleanly
- `cd app && uv run python -c "from worker.config import celery_app"` imports cleanly
- `cd app && uv run python -c "from services.embedding_service import EmbeddingService; from services.transcript_service import TranscriptService; from services.article_extraction_service import ArticleExtractionService; from services.search_service import SearchService; from services.chunking_service import ChunkingService"` all import without error
- `cd app && uv run python -c "from core.nodes.tool_use import ToolUseNode"` imports cleanly
- `cd app && uv run alembic upgrade head` runs against a running Postgres without error
- `cd app && uv run python -c "from workflows.workflow_registry import WorkflowRegistry; WorkflowRegistry.CONTENT_PIPELINE"` succeeds
- `GET /health` returns `{"status": "ok"}` (manual curl or test)
- No system prompt is hardcoded in Python — any prompt files are `.j2` in `app/prompts/`
- No `if running_locally:` or deployment conditionals in any new node or service

## Validation Commands
```bash
uv run pytest
uv run ruff check app/
uv run pylint app/
cd app && uv run python -c "from main import app"
cd app && uv run python -c "from worker.config import celery_app"
cd app && uv run python -c "from services.embedding_service import EmbeddingService; from services.transcript_service import TranscriptService; from services.article_extraction_service import ArticleExtractionService; from services.search_service import SearchService; from services.chunking_service import ChunkingService"
cd app && uv run python -c "from core.nodes.tool_use import ToolUseNode"
cd app && uv run python -c "from workflows.workflow_registry import WorkflowRegistry; WorkflowRegistry.CONTENT_PIPELINE"
```

## Notes
*Filled in as work happens.*
