# Task Breakdown — Phase 0, Block D

## Source Spec
`planning/tasks/phase0-blockD/tasks.md`

## Goal
Build the shared services layer (embedding, transcript, article extraction, search, chunking,
raw tool-use node), enable pgvector, scaffold Project A's workflow structure, and make the
FastAPI API contract explicit as a documented product surface.

## How to Use
Work top to bottom. Each sub-step is a single atomic action. Run the inline **Verify**
checks as you go — do not batch them at the end. Each check must pass before continuing.

---

## Steps

### Step 1: Add New Dependencies

#### 1.1 Add runtime dependencies via uv
**Action:** Run from repo root:
```bash
uv add voyageai youtube-transcript-api trafilatura firecrawl-py tavily-python anthropic pymupdf
```
`anthropic` is a transitive dep from `pydantic-ai` today — pin it explicitly so the version
is locked in `uv.lock`. `fitz` is the import name for `pymupdf`.

**Verify:** `uv run python -c "import voyageai, tavily, trafilatura, anthropic, fitz"` → exits 0

---

### Step 2: pgvector Migration

#### 2.1 Generate the Alembic migration skeleton
**Action:** Run from `app/`:
```bash
cd app && uv run alembic revision --autogenerate -m "enable_pgvector_extension"
```
`--autogenerate` detects no model changes (none exist yet) and produces an empty migration.
Edit it next.

#### 2.2 Edit the generated migration to enable the extension
**File:** `app/alembic/versions/<timestamp>_enable_pgvector_extension.py` (the file from 2.1)
**Action:** Replace the empty `upgrade()` and `downgrade()` bodies with:
```python
def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
```

**Verify:** `cd app && uv run alembic upgrade head` → exits 0 (requires Docker stack running:
`cd docker && ./start.sh`)

---

### Step 3: EmbeddingService

#### 3.1 Create `app/services/embedding_service.py`
**File:** `app/services/embedding_service.py`
**Action:** Create with:
```python
"""EmbeddingService wraps VoyageAI (or any provider) to produce float vectors."""

import os

import voyageai


class EmbeddingService:
    def __init__(self, model: str = "voyage-2", dims: int = 1024) -> None:
        api_key = os.environ["VOYAGE_API_KEY"]
        self._client = voyageai.Client(api_key=api_key)
        self._model = model
        self._dims = dims

    def embed_text(self, text: str) -> list[float]:
        result = self._client.embed([text], model=self._model)
        return result.embeddings[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        result = self._client.embed(texts, model=self._model)
        return result.embeddings
```
Note: verify `voyageai.Client` API after install — if the entry point differs (e.g. `voyageai.get_client()`), adapt accordingly. The seam is intentional: `model` and `dims` are constructor params so a local embedding model slots in without code changes.

#### 3.2 Export `EmbeddingService` from `app/services/__init__.py`
**File:** `app/services/__init__.py`
**Action:** Replace the empty file with:
```python
"""Shared services — embedding, transcript, article extraction, search, chunking."""

from services.embedding_service import EmbeddingService

__all__ = ["EmbeddingService"]
```
(This file will grow as Steps 4–7 add more exports; update `__all__` each time.)

#### 3.3 Create `tests/services/test_embedding_service.py`
**File:** `tests/services/test_embedding_service.py`
**Action:** Create with:
```python
"""Unit tests for EmbeddingService."""

from unittest.mock import MagicMock, patch

import pytest

from services.embedding_service import EmbeddingService


@pytest.fixture
def mock_voyage_client():
    with patch("services.embedding_service.voyageai.Client") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def service(mock_voyage_client, monkeypatch):
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    return EmbeddingService()


class TestEmbedText:
    def test_returns_first_embedding(self, service, mock_voyage_client):
        mock_voyage_client.embed.return_value = MagicMock(embeddings=[[0.1, 0.2, 0.3]])
        result = service.embed_text("hello")
        assert result == [0.1, 0.2, 0.3]

    def test_calls_embed_with_single_item_list(self, service, mock_voyage_client):
        mock_voyage_client.embed.return_value = MagicMock(embeddings=[[0.0]])
        service.embed_text("test")
        mock_voyage_client.embed.assert_called_once_with(["test"], model="voyage-2")


class TestEmbedBatch:
    def test_returns_list_of_float_lists(self, service, mock_voyage_client):
        mock_voyage_client.embed.return_value = MagicMock(
            embeddings=[[0.1, 0.2], [0.3, 0.4]]
        )
        result = service.embed_batch(["a", "b"])
        assert len(result) == 2
        assert result[0] == [0.1, 0.2]

    def test_delegates_full_list_to_client(self, service, mock_voyage_client):
        mock_voyage_client.embed.return_value = MagicMock(embeddings=[[], []])
        service.embed_batch(["x", "y"])
        mock_voyage_client.embed.assert_called_once_with(["x", "y"], model="voyage-2")
```

**Verify:** `uv run pytest tests/services/test_embedding_service.py -v` → all tests pass

---

### Step 4: TranscriptService

#### 4.1 Create `app/services/transcript_service.py`
**File:** `app/services/transcript_service.py`
**Action:** Create with:
```python
"""TranscriptService fetches and optionally chunks YouTube video transcripts."""

import re

from youtube_transcript_api import YouTubeTranscriptApi

from services.chunking_service import ChunkingService

_VIDEO_ID_RE = re.compile(
    r"(?:v=|youtu\.be/|embed/|shorts/)([a-zA-Z0-9_-]{11})"
)


class TranscriptService:
    def _extract_video_id(self, url: str) -> str:
        match = _VIDEO_ID_RE.search(url)
        if not match:
            raise ValueError(f"Cannot extract video ID from URL: {url!r}")
        return match.group(1)

    def fetch_transcript(self, url: str) -> str:
        video_id = self._extract_video_id(url)
        entries = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join(e["text"] for e in entries)

    def fetch_and_chunk(
        self, url: str, chunk_size: int = 500, overlap: int = 50
    ) -> list[str]:
        text = self.fetch_transcript(url)
        return ChunkingService().chunk_text(text, chunk_size=chunk_size, overlap=overlap)
```

#### 4.2 Export `TranscriptService` from `app/services/__init__.py`
**File:** `app/services/__init__.py`
**Action:** Add to imports and `__all__`:
```python
from services.transcript_service import TranscriptService
```

#### 4.3 Create `tests/services/test_transcript_service.py`
**File:** `tests/services/test_transcript_service.py`
**Action:** Create with:
```python
"""Unit tests for TranscriptService."""

from unittest.mock import MagicMock, patch

import pytest

from services.transcript_service import TranscriptService


@pytest.fixture
def service():
    return TranscriptService()


class TestExtractVideoId:
    def test_standard_watch_url(self, service):
        assert service._extract_video_id(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        ) == "dQw4w9WgXcQ"

    def test_short_url(self, service):
        assert service._extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_invalid_url_raises_value_error(self, service):
        with pytest.raises(ValueError, match="Cannot extract video ID"):
            service._extract_video_id("https://example.com/not-a-video")


class TestFetchTranscript:
    def test_joins_transcript_entries(self, service):
        entries = [{"text": "Hello"}, {"text": "world"}]
        with patch(
            "services.transcript_service.YouTubeTranscriptApi.get_transcript",
            return_value=entries,
        ):
            result = service.fetch_transcript("https://youtu.be/dQw4w9WgXcQ")
        assert result == "Hello world"

    def test_propagates_api_error(self, service):
        with patch(
            "services.transcript_service.YouTubeTranscriptApi.get_transcript",
            side_effect=Exception("no transcript"),
        ):
            with pytest.raises(Exception, match="no transcript"):
                service.fetch_transcript("https://youtu.be/dQw4w9WgXcQ")


class TestFetchAndChunk:
    def test_delegates_to_chunking_service(self, service):
        with (
            patch.object(service, "fetch_transcript", return_value="word " * 100),
            patch(
                "services.transcript_service.ChunkingService.chunk_text",
                return_value=["chunk1", "chunk2"],
            ),
        ):
            result = service.fetch_and_chunk("https://youtu.be/abc1234abcd")
        assert result == ["chunk1", "chunk2"]
```

**Verify:** `uv run pytest tests/services/test_transcript_service.py -v` → all tests pass

---

### Step 5: ArticleExtractionService

#### 5.1 Create `app/services/article_extraction_service.py`
**File:** `app/services/article_extraction_service.py`
**Action:** Create with:
```python
"""ArticleExtractionService — trafilatura first, Firecrawl fallback."""

import logging
import os

import trafilatura
from pydantic import BaseModel

log = logging.getLogger(__name__)


class ArticleResult(BaseModel):
    text: str
    title: str | None = None
    fetch_status: str  # "ok" | "fallback_used" | "failed"


class ArticleExtractionService:
    def __init__(self) -> None:
        self._firecrawl_key = os.getenv("FIRECRAWL_API_KEY")

    def extract(self, url: str) -> ArticleResult:
        downloaded = trafilatura.fetch_url(url)
        text = trafilatura.extract(downloaded) if downloaded else None

        if text:
            return ArticleResult(text=text, fetch_status="ok")

        if self._firecrawl_key:
            try:
                from firecrawl import FirecrawlApp  # noqa: PLC0415
                fc_app = FirecrawlApp(api_key=self._firecrawl_key)
                result = fc_app.scrape_url(url, params={"formats": ["markdown"]})
                content = result.get("markdown") or result.get("content", "")
                if content:
                    return ArticleResult(text=content, fetch_status="fallback_used")
            except Exception as exc:  # noqa: BLE001
                log.warning("Firecrawl fallback failed for %s: %s", url, exc)

        log.warning("Article extraction failed for %s", url)
        return ArticleResult(text="", fetch_status="failed")
```
Note: Firecrawl is imported inline (only when the API key is present) to keep the service
stateless and avoid import errors when the key is absent.

#### 5.2 Export from `app/services/__init__.py`
**File:** `app/services/__init__.py`
**Action:** Add to imports and `__all__`:
```python
from services.article_extraction_service import ArticleExtractionService, ArticleResult
```

#### 5.3 Create `tests/services/test_article_extraction_service.py`
**File:** `tests/services/test_article_extraction_service.py`
**Action:** Create with:
```python
"""Unit tests for ArticleExtractionService."""

from unittest.mock import MagicMock, patch

import pytest

from services.article_extraction_service import ArticleExtractionService, ArticleResult


@pytest.fixture
def service_no_firecrawl(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    return ArticleExtractionService()


@pytest.fixture
def service_with_firecrawl(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "test-key")
    return ArticleExtractionService()


class TestTrafilaturaSuccess:
    def test_returns_ok_status_when_text_extracted(self, service_no_firecrawl):
        with (
            patch(
                "services.article_extraction_service.trafilatura.fetch_url",
                return_value=b"<html>content</html>",
            ),
            patch(
                "services.article_extraction_service.trafilatura.extract",
                return_value="Article text",
            ),
        ):
            result = service_no_firecrawl.extract("https://example.com/article")
        assert result.fetch_status == "ok"
        assert result.text == "Article text"


class TestFirecrawlFallback:
    def test_fallback_triggered_when_trafilatura_empty(self, service_with_firecrawl):
        mock_fc = MagicMock()
        mock_fc.scrape_url.return_value = {"markdown": "Firecrawl content"}
        with (
            patch(
                "services.article_extraction_service.trafilatura.fetch_url",
                return_value=None,
            ),
            patch(
                "services.article_extraction_service.FirecrawlApp",
                return_value=mock_fc,
            ),
        ):
            result = service_with_firecrawl.extract("https://js-heavy.com")
        assert result.fetch_status == "fallback_used"
        assert result.text == "Firecrawl content"

    def test_graceful_failure_when_all_fail(self, service_no_firecrawl):
        with patch(
            "services.article_extraction_service.trafilatura.fetch_url",
            return_value=None,
        ):
            result = service_no_firecrawl.extract("https://broken.com")
        assert result.fetch_status == "failed"
        assert result.text == ""
```

**Verify:** `uv run pytest tests/services/test_article_extraction_service.py -v` → all tests pass

---

### Step 6: SearchService

#### 6.1 Create `app/services/search_service.py`
**File:** `app/services/search_service.py`
**Action:** Create with:
```python
"""SearchService wraps Tavily to produce structured search results."""

import os

from pydantic import BaseModel
from tavily import TavilyClient


class SearchResult(BaseModel):
    title: str
    url: str
    content: str
    score: float | None = None


class SearchService:
    def __init__(self) -> None:
        api_key = os.environ["TAVILY_API_KEY"]
        self._client = TavilyClient(api_key=api_key)

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        response = self._client.search(query, max_results=max_results)
        return [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", ""),
                score=r.get("score"),
            )
            for r in response.get("results", [])
        ]
```

#### 6.2 Export from `app/services/__init__.py`
**File:** `app/services/__init__.py`
**Action:** Add to imports and `__all__`:
```python
from services.search_service import SearchResult, SearchService
```

#### 6.3 Create `tests/services/test_search_service.py`
**File:** `tests/services/test_search_service.py`
**Action:** Create with:
```python
"""Unit tests for SearchService."""

from unittest.mock import MagicMock, patch

import pytest

from services.search_service import SearchResult, SearchService


@pytest.fixture
def mock_tavily():
    with patch("services.search_service.TavilyClient") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def service(mock_tavily, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    return SearchService()


class TestSearch:
    def test_returns_search_result_instances(self, service, mock_tavily):
        mock_tavily.search.return_value = {
            "results": [
                {"title": "A", "url": "https://a.com", "content": "text", "score": 0.9}
            ]
        }
        results = service.search("test query")
        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].title == "A"
        assert results[0].score == 0.9

    def test_max_results_passed_to_client(self, service, mock_tavily):
        mock_tavily.search.return_value = {"results": []}
        service.search("query", max_results=3)
        mock_tavily.search.assert_called_once_with("query", max_results=3)

    def test_empty_results_returns_empty_list(self, service, mock_tavily):
        mock_tavily.search.return_value = {"results": []}
        assert service.search("nothing") == []
```

**Verify:** `uv run pytest tests/services/test_search_service.py -v` → all tests pass

---

### Step 7: ChunkingService

#### 7.1 Create `app/services/chunking_service.py`
**File:** `app/services/chunking_service.py`
**Action:** Create with:
```python
"""ChunkingService splits text or binary documents into overlapping token chunks."""

import fitz
import tiktoken


class ChunkingService:
    _ENCODING = "cl100k_base"

    def _get_encoder(self) -> tiktoken.Encoding:
        return tiktoken.get_encoding(self._ENCODING)

    def chunk_text(
        self, text: str, chunk_size: int = 500, overlap: int = 50
    ) -> list[str]:
        enc = self._get_encoder()
        tokens = enc.encode(text)
        if not tokens:
            return []
        chunks = []
        step = chunk_size - overlap
        start = 0
        while start < len(tokens):
            chunk_tokens = tokens[start : start + chunk_size]
            chunks.append(enc.decode(chunk_tokens))
            start += step
        return chunks

    def chunk_document(
        self,
        content: bytes,
        mime_type: str,
        chunk_size: int = 500,
        overlap: int = 50,
    ) -> list[str]:
        if mime_type == "text/plain":
            return self.chunk_text(content.decode("utf-8"), chunk_size, overlap)
        if mime_type == "application/pdf":
            doc = fitz.open(stream=content, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc)
            return self.chunk_text(text, chunk_size, overlap)
        raise ValueError(f"Unsupported mime_type: {mime_type!r}")
```
`tiktoken` is already in `pyproject.toml`. `fitz` is the module name for `pymupdf` (added in Step 1).
Both are imported at module level so tests can patch `services.chunking_service.fitz.open`.

#### 7.2 Export from `app/services/__init__.py`
**File:** `app/services/__init__.py`
**Action:** Add to imports and `__all__`:
```python
from services.chunking_service import ChunkingService
```

#### 7.3 Create `tests/services/test_chunking_service.py`
**File:** `tests/services/test_chunking_service.py`
**Action:** Create with:
```python
"""Unit tests for ChunkingService."""

from unittest.mock import MagicMock, patch

import pytest

from services.chunking_service import ChunkingService


@pytest.fixture
def service():
    return ChunkingService()


class TestChunkText:
    def test_short_text_returns_single_chunk(self, service):
        result = service.chunk_text("hello world", chunk_size=500, overlap=50)
        assert len(result) == 1
        assert "hello" in result[0]

    def test_empty_text_returns_empty_list(self, service):
        assert service.chunk_text("") == []

    def test_overlap_shared_between_adjacent_chunks(self, service):
        long_text = "word " * 600
        chunks = service.chunk_text(long_text, chunk_size=100, overlap=20)
        assert len(chunks) >= 2
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        tail = enc.encode(chunks[0])[-20:]
        head = enc.encode(chunks[1])[:20]
        assert tail == head


class TestChunkDocument:
    def test_plain_text_returns_chunk_list(self, service):
        result = service.chunk_document(b"hello world", "text/plain")
        assert len(result) >= 1
        assert "hello" in result[0]

    def test_pdf_uses_fitz_open(self, service):
        mock_page = MagicMock()
        mock_page.get_text.return_value = "PDF page content"
        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        with patch("services.chunking_service.fitz.open", return_value=mock_doc):
            result = service.chunk_document(b"%PDF-fake", "application/pdf")
        assert any("PDF page content" in c for c in result)

    def test_unsupported_mime_raises_value_error(self, service):
        with pytest.raises(ValueError, match="Unsupported mime_type"):
            service.chunk_document(b"data", "image/png")
```

**Verify:** `uv run pytest tests/services/test_chunking_service.py -v` → all tests pass

---

### Step 8: ToolUseNode

#### 8.1 Create `app/core/nodes/tool_use.py`
**File:** `app/core/nodes/tool_use.py`
**Action:** Create with:
```python
"""ToolUseNode — abstract base for raw Anthropic SDK tool-use loops."""

import logging
import os
from abc import abstractmethod

import anthropic

from core.nodes.base import Node
from core.task import TaskContext

log = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class ToolUseNode(Node):
    max_iterations: int = 10

    def __init__(self) -> None:
        self._client = anthropic.Anthropic()
        self._model = os.getenv("TOOL_USE_MODEL", _DEFAULT_MODEL)

    @property
    @abstractmethod
    def tools(self) -> list[dict]:
        """Anthropic tool definitions for this node."""

    @abstractmethod
    def handle_tool_call(
        self,
        tool_name: str,
        tool_input: dict,
        task_context: TaskContext,
    ) -> str:
        """Execute a single tool call and return the result string."""

    def _build_initial_messages(self, task_context: TaskContext) -> list[dict]:
        """Override to customise the initial user message for the loop."""
        return [{"role": "user", "content": str(task_context.nodes)}]

    def process(self, task_context: TaskContext) -> TaskContext:
        messages: list[dict] = self._build_initial_messages(task_context)
        iterations = 0

        while iterations < self.max_iterations:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                tools=self.tools,
                messages=messages,
            )
            iterations += 1

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = self.handle_tool_call(
                            block.name, block.input, task_context
                        )
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            }
                        )
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
            else:
                break

        if iterations >= self.max_iterations:
            log.warning(
                "ToolUseNode %s hit max_iterations=%d; returning partial result",
                self.node_name,
                self.max_iterations,
            )

        return task_context
```

#### 8.2 Export `ToolUseNode` from `app/core/nodes/__init__.py`
**File:** `app/core/nodes/__init__.py`
**Action:** Replace the empty file with:
```python
"""Core node abstractions."""

from core.nodes.tool_use import ToolUseNode

__all__ = ["ToolUseNode"]
```

#### 8.3 Create `tests/core/test_nodes_tool_use.py`
**File:** `tests/core/test_nodes_tool_use.py`
**Action:** Create with:
```python
"""Unit tests for ToolUseNode in app/core/nodes/tool_use.py."""

from unittest.mock import MagicMock, patch

import pytest

from core.nodes.tool_use import ToolUseNode
from core.task import TaskContext


class ConcreteToolUseNode(ToolUseNode):
    """Minimal concrete subclass for testing the abstract loop."""

    @property
    def tools(self) -> list[dict]:
        return [
            {
                "name": "echo",
                "description": "Echoes input",
                "input_schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                },
            }
        ]

    def handle_tool_call(
        self, tool_name: str, tool_input: dict, task_context: TaskContext
    ) -> str:
        return f"echo:{tool_input.get('text', '')}"


@pytest.fixture
def mock_anthropic_client():
    with patch("core.nodes.tool_use.anthropic.Anthropic") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def node(mock_anthropic_client, monkeypatch):
    monkeypatch.setenv("TOOL_USE_MODEL", "claude-haiku-4-5-20251001")
    return ConcreteToolUseNode()


@pytest.fixture
def ctx():
    return TaskContext(event={"input": "test"})


def _end_turn_response():
    r = MagicMock()
    r.stop_reason = "end_turn"
    r.content = []
    return r


def _tool_use_response(tool_id: str, name: str, tool_input: dict):
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = tool_input
    r = MagicMock()
    r.stop_reason = "tool_use"
    r.content = [block]
    return r


class TestLoopTerminatesOnEndTurn:
    def test_single_end_turn_makes_exactly_one_api_call(
        self, node, mock_anthropic_client, ctx
    ):
        mock_anthropic_client.messages.create.return_value = _end_turn_response()
        result = node.process(ctx)
        assert mock_anthropic_client.messages.create.call_count == 1
        assert result is ctx


class TestToolCallDispatch:
    def test_handle_tool_call_invoked_then_loop_continues(
        self, node, mock_anthropic_client, ctx
    ):
        mock_anthropic_client.messages.create.side_effect = [
            _tool_use_response("id1", "echo", {"text": "hello"}),
            _end_turn_response(),
        ]
        node.process(ctx)
        assert mock_anthropic_client.messages.create.call_count == 2

    def test_tool_result_appended_to_messages_on_second_call(
        self, node, mock_anthropic_client, ctx
    ):
        mock_anthropic_client.messages.create.side_effect = [
            _tool_use_response("id1", "echo", {"text": "world"}),
            _end_turn_response(),
        ]
        node.process(ctx)
        second_call = mock_anthropic_client.messages.create.call_args_list[1]
        messages = second_call.kwargs.get("messages") or second_call[1]["messages"]
        user_msgs = [m for m in messages if m["role"] == "user"]
        last_user_content = user_msgs[-1]["content"]
        assert any(
            isinstance(r, dict) and r.get("type") == "tool_result"
            for r in last_user_content
        )


class TestMaxIterationsGuard:
    def test_loop_exits_at_max_iterations(self, node, mock_anthropic_client, ctx):
        node.max_iterations = 3
        mock_anthropic_client.messages.create.return_value = _tool_use_response(
            "id1", "echo", {"text": "x"}
        )
        node.process(ctx)
        assert mock_anthropic_client.messages.create.call_count == 3

    def test_does_not_raise_on_max_iterations(self, node, mock_anthropic_client, ctx):
        node.max_iterations = 2
        mock_anthropic_client.messages.create.return_value = _tool_use_response(
            "id1", "echo", {"text": "x"}
        )
        result = node.process(ctx)
        assert result is ctx
```

**Verify:** `uv run pytest tests/core/test_nodes_tool_use.py -v` → all tests pass

---

### Step 9: Scaffold Project A

#### 9.1 Run createworkflow interactively
**Action:** From repo root:
```bash
uv run createworkflow
```
At the prompt enter: `content_pipeline`

Expected files created:
- `app/workflows/content_pipeline_workflow.py`
- `app/workflows/content_pipeline_workflow_nodes/__init__.py`
- `app/workflows/content_pipeline_workflow_nodes/initial_node.py`
- `app/schemas/content_pipeline_schema.py`

Do NOT edit any generated file — leave stubs exactly as generated.

#### 9.2 Read the generated schema class name
**File:** `app/schemas/content_pipeline_schema.py`
**Action:** Read the file and note the exact class name (likely `ContentPipelineEventSchema`).
This name is needed in Step 10.2.

#### 9.3 Register `ContentPipelineWorkflow` in WorkflowRegistry
**File:** `app/workflows/workflow_registry.py`
**Action:** Replace file contents with:
```python
"""Workflow registry — maps enum members to concrete Workflow subclasses."""

from enum import Enum

from workflows.content_pipeline_workflow import ContentPipelineWorkflow
from workflows.customer_care_workflow import CustomerCareWorkflow


class WorkflowRegistry(Enum):
    CUSTOMER_CARE = CustomerCareWorkflow
    CONTENT_PIPELINE = ContentPipelineWorkflow
```

**Verify:**
```bash
cd app && uv run python -c "from workflows.workflow_registry import WorkflowRegistry; print(WorkflowRegistry.CONTENT_PIPELINE)"
```
→ prints `WorkflowRegistry.CONTENT_PIPELINE`

---

### Step 10: Clean API Contract

#### 10.1 Create `app/api/health.py`
**File:** `app/api/health.py`
**Action:** Create with:
```python
"""Health check endpoint."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", version="0.1.0")
```

#### 10.2 Create `app/api/schema_registry.py`
**File:** `app/api/schema_registry.py`
**Action:** Create with (adjust schema class name if it differs from what Step 9.2 shows):
```python
"""Maps WorkflowRegistry enum names to their event schema classes."""

from pydantic import BaseModel

from schemas.content_pipeline_schema import ContentPipelineEventSchema
from schemas.customer_care_schema import CustomerCareEventSchema
from workflows.workflow_registry import WorkflowRegistry

SCHEMA_MAP: dict[str, type[BaseModel]] = {
    WorkflowRegistry.CUSTOMER_CARE.name: CustomerCareEventSchema,
    WorkflowRegistry.CONTENT_PIPELINE.name: ContentPipelineEventSchema,
}
```

#### 10.3 Create `app/api/models.py`
**File:** `app/api/models.py`
**Action:** Create with:
```python
"""Typed Pydantic response and request models for the API layer."""

from pydantic import BaseModel


class TaskAcceptedResponse(BaseModel):
    task_id: str
    message: str


class EventPayload(BaseModel):
    workflow_type: str
    data: dict
```

#### 10.4 Rewrite `app/api/endpoint.py` with generic dispatcher
**File:** `app/api/endpoint.py`
**Action:** Replace the entire file with:
```python
"""Event submission endpoint — generic dispatcher over registered workflow schemas."""

import json
from http import HTTPStatus

from database.event import Event
from database.session import db_session
from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.responses import Response
from worker.config import celery_app

from api.models import EventPayload, TaskAcceptedResponse
from api.schema_registry import SCHEMA_MAP

router = APIRouter()


@router.post("/", status_code=HTTPStatus.ACCEPTED)
def handle_event(
    payload: EventPayload,
    session: Session = Depends(db_session),
) -> Response:
    schema_cls = SCHEMA_MAP.get(payload.workflow_type)
    if schema_cls is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown workflow_type: {payload.workflow_type!r}. "
                f"Valid types: {list(SCHEMA_MAP.keys())}"
            ),
        )

    try:
        schema_cls.model_validate(payload.data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    event = Event(data=payload.data, workflow_type=payload.workflow_type)
    session.add(event)
    session.flush()

    task = celery_app.send_task("process_incoming_event", args=[str(event.id)])

    return Response(
        content=json.dumps(
            TaskAcceptedResponse(
                task_id=str(task.id),
                message=f"process_incoming_event started `{task.id}`",
            ).model_dump()
        ),
        status_code=HTTPStatus.ACCEPTED,
        media_type="application/json",
    )
```
Note: module docstring is on line 1, before imports — required by CLAUDE.md standing rule.

#### 10.5 Update `app/api/router.py` to include the health router
**File:** `app/api/router.py`
**Action:** Replace file contents with:
```python
"""API router — event ingestion and health check."""

from fastapi import APIRouter

from api import endpoint, health

router = APIRouter()
router.include_router(endpoint.router, prefix="/events", tags=["events"])
router.include_router(health.router, tags=["health"])
```

#### 10.6 Add OpenAPI metadata to `app/main.py`
**File:** `app/main.py`
**Action:** Replace file contents with:
```python
"""FastAPI application entry point."""

from api.router import router as process_router
from fastapi import FastAPI

app = FastAPI(
    title="Agentic Orchestration API",
    description=(
        "Event-driven AI pipeline framework: "
        "FastAPI → Celery → Workflow DAG → TaskContext."
    ),
    version="0.1.0",
)
app.include_router(process_router)
```

#### 10.7 Update `tests/api/test_endpoint.py` to cover the new contract
**File:** `tests/api/test_endpoint.py`
**Action:** Replace file contents with:
```python
"""Tests for the API endpoint layer — generic dispatch, validation, and health."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.event import Event
from database.session import Base, db_session
from main import app
from worker.config import celery_app

VALID_CUSTOMER_CARE_PAYLOAD = {
    "workflow_type": "CUSTOMER_CARE",
    "data": {
        "from_email": "sender@example.com",
        "to_email": "support@example.com",
        "sender": "Test User",
        "subject": "Test Subject",
        "body": "This is a test message.",
    },
}


@pytest.fixture
def endpoint_context():
    """Yields (TestClient, session) sharing one in-memory SQLite DB."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    def override_db_session():
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    app.dependency_overrides[db_session] = override_db_session
    client = TestClient(app, raise_server_exceptions=False)

    yield client, session

    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


class TestEventDispatch:
    def test_valid_payload_returns_202(self, endpoint_context):
        client, _ = endpoint_context
        with patch.object(celery_app, "send_task", return_value=MagicMock()):
            response = client.post("/events/", json=VALID_CUSTOMER_CARE_PAYLOAD)
        assert response.status_code == 202

    def test_unknown_workflow_type_returns_422(self, endpoint_context):
        client, _ = endpoint_context
        response = client.post(
            "/events/",
            json={"workflow_type": "NONEXISTENT", "data": {}},
        )
        assert response.status_code == 422

    def test_failed_enqueue_does_not_commit_event(self, endpoint_context):
        client, session = endpoint_context
        with patch.object(
            celery_app, "send_task", side_effect=RuntimeError("Redis unavailable")
        ):
            response = client.post("/events/", json=VALID_CUSTOMER_CARE_PAYLOAD)
        assert response.status_code == 500
        assert session.query(Event).count() == 0

    def test_successful_enqueue_commits_event(self, endpoint_context):
        client, session = endpoint_context
        with patch.object(celery_app, "send_task", return_value=MagicMock()):
            response = client.post("/events/", json=VALID_CUSTOMER_CARE_PAYLOAD)
        assert response.status_code == 202
        assert session.query(Event).count() == 1


class TestHealthCheck:
    def test_health_returns_200(self, endpoint_context):
        client, _ = endpoint_context
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
```

**Verify:** `uv run pytest tests/api/test_endpoint.py -v` → all tests pass

---

### Step 11: Validate

#### 11.1 Run full test suite
**Action:** `uv run pytest`
→ all tests pass, zero failures, zero skips

#### 11.2 Lint check
**Action:** `uv run ruff check app/`
→ zero errors

#### 11.3 Pylint
**Action:** `uv run pylint app/`
→ score ≥ previous baseline

#### 11.4 Import smoke-tests
**Action:** Run each line:
```bash
cd app && uv run python -c "from main import app"
cd app && uv run python -c "from worker.config import celery_app"
cd app && uv run python -c "from services.embedding_service import EmbeddingService; from services.transcript_service import TranscriptService; from services.article_extraction_service import ArticleExtractionService; from services.search_service import SearchService; from services.chunking_service import ChunkingService"
cd app && uv run python -c "from core.nodes.tool_use import ToolUseNode"
cd app && uv run python -c "from workflows.workflow_registry import WorkflowRegistry; WorkflowRegistry.CONTENT_PIPELINE"
```
→ all exit 0

**Verify:** All five lines above exit 0 with no error output

---

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
- `app/services/__init__.py` and `app/core/nodes/__init__.py` are currently empty — they need export entries added per Steps 3.2 / 8.2.
- `voyageai.Client` API: verify the exact constructor signature after `uv add voyageai`. If it uses a different entry point (e.g. `voyageai.get_client()`), adapt `embedding_service.py` accordingly.
- Step 9.2 exists to read the generated schema class name before writing `schema_registry.py` in Step 10.2 — the class name is derived from the workflow name by `createworkflow` and may differ from `ContentPipelineEventSchema`.
- `ChunkingService` uses `tiktoken` (already in `pyproject.toml`). `fitz` is imported at module level so tests can patch `services.chunking_service.fitz.open`.
- The Alembic autogenerate in Step 2.1 will produce an empty migration (no model changes detected) — this is expected. Edit it per Step 2.2 before running `alembic upgrade head`.
- `app/api/endpoint.py` currently has its module docstring *after* the imports — the rewrite moves it to line 1 per CLAUDE.md rule.
- `ToolUseNode` reads `TOOL_USE_MODEL` from env; default is `claude-haiku-4-5-20251001`.
- `ArticleExtractionService` is intentionally stateless with no `max_calls` guard — that limit belongs in the calling node (agent tool loop discipline).
- `TranscriptService` imports `ChunkingService` at module level (not inline) to keep it easily patchable in tests.
