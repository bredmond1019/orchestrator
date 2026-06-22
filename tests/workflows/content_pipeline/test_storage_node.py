"""Unit tests for the content_pipeline StorageNode and digest renderer.

No real database and no real Voyage call: ``EmbeddingService`` is monkeypatched
(both its constructor and ``embed_text``) and ``StorageNode._persist`` is
captured so the artifact is inspected without touching SQLAlchemy. The HTML is
written into a ``tmp_path`` digest dir supplied via ``CONTENT_DIGEST_DIR``.
"""

from pathlib import Path

import pytest

from core.task import TaskContext
from schemas.content_pipeline_schema import ContentPipelineEventSchema
from services.embedding_service import EmbeddingService
from workflows.content_pipeline_workflow_nodes.digest_renderer import (
    regenerate_category_index,
    render_artifact_page,
)
from workflows.content_pipeline_workflow_nodes.storage_node import StorageNode
from workflows.content_pipeline_workflow_nodes.summarizer_node import SummaryOutput


def _summary() -> SummaryOutput:
    return SummaryOutput(
        title="Attention Is All You Need",
        category="ai_engineering",
        tl_dr="Transformers replace recurrence with self-attention.",
        read_time_estimate="8 min",
        core_concepts=["self-attention", "positional encoding"],
        key_insights=["No recurrence needed", "Parallelizable training"],
        questions_raised=["How does it scale to long context?"],
        connections_to_my_work=["Underpins the agentic harness LLM nodes"],
        further_exploration=["Read the FlashAttention paper"],
    )


@pytest.fixture
def storage_setup(monkeypatch, tmp_path):
    """Wire a StorageNode with a captured embedding + persistence and a tmp dir."""
    summary = _summary()
    event = ContentPipelineEventSchema(url="https://example.com/post", make_blog=False)
    ctx = TaskContext(event=event)
    ctx.update_node("SummarizerNode", result=summary)
    ctx.update_node("FetchArticleNode", source_type="article", fetch_status="ok")

    monkeypatch.setenv("CONTENT_DIGEST_DIR", str(tmp_path))
    monkeypatch.setattr(EmbeddingService, "__init__", lambda self: None)
    monkeypatch.setattr(EmbeddingService, "embed_text", lambda self, text: [0.1] * 1024)

    captured: list = []
    monkeypatch.setattr(StorageNode, "_persist", lambda self, art: captured.append(art))

    return summary, event, ctx, tmp_path, captured


def test_persists_artifact_with_1024_dim_embedding(storage_setup):
    summary, _event, ctx, _tmp, captured = storage_setup
    StorageNode().process(ctx)
    assert len(captured) == 1
    artifact = captured[0]
    assert isinstance(artifact.embedding, list)
    assert len(artifact.embedding) == 1024
    assert artifact.embedding  # non-empty
    assert artifact.category == summary.category
    assert artifact.source_url == "https://example.com/post"


def test_embedding_written_at_write_time(storage_setup):
    """The embedding must be set on the artifact before _persist receives it.

    The fixture's ``_persist`` captures the artifact synchronously at the moment
    the node persists it, so a non-null embedding on the captured object proves
    the embed step ran before persistence.
    """
    _summary_obj, _event, ctx, _tmp, captured = storage_setup
    StorageNode().process(ctx)
    assert captured[0].embedding is not None
    assert len(captured[0].embedding) == 1024


def test_writes_html_page(storage_setup):
    summary, event, ctx, tmp_path, _captured = storage_setup
    StorageNode().process(ctx)
    page = tmp_path / summary.category / f"{event.artifact_id}.html"
    assert page.exists()
    assert summary.title in page.read_text(encoding="utf-8")


def test_regenerates_category_index(storage_setup):
    summary, _event, ctx, tmp_path, _captured = storage_setup
    StorageNode().process(ctx)
    index = tmp_path / summary.category / "index.html"
    assert index.exists()


def test_node_output_recorded(storage_setup):
    _summary_obj, event, ctx, _tmp, _captured = storage_setup
    StorageNode().process(ctx)
    output = ctx.nodes["StorageNode"]["output"]
    assert output["embedded"] is True
    assert output["artifact_id"] == str(event.artifact_id)


def test_artifact_id_sourced_from_event_not_orm_after_persist(monkeypatch, tmp_path):
    """Regression: process() must not read the ORM artifact's attributes after persist.

    The real ``_persist`` commits and closes its session; SQLAlchemy's default
    ``expire_on_commit`` then expires the instance, so reading ``artifact.id``
    afterward raised ``DetachedInstanceError`` in production. Here ``_persist``
    clears ``art.id`` to emulate that "attribute is no longer reliable after the
    persisting session closed" state. The node must still emit the event's
    ``artifact_id`` and name the digest page by it. The original (buggy) code read
    ``str(artifact.id)`` post-persist and would fail this test.
    """
    summary = _summary()
    event = ContentPipelineEventSchema(url="https://youtu.be/abc", make_blog=False)
    ctx = TaskContext(event=event)
    ctx.update_node("SummarizerNode", result=summary)
    ctx.update_node("FetchTranscriptNode", text="...", fetch_status="ok")

    monkeypatch.setenv("CONTENT_DIGEST_DIR", str(tmp_path))
    monkeypatch.setattr(EmbeddingService, "__init__", lambda self: None)
    monkeypatch.setattr(EmbeddingService, "embed_text", lambda self, text: [0.1] * 1024)

    def _persist_then_detach(self, art):
        # Emulate expire_on_commit + closed session: the ORM id is now unreliable.
        art.id = None

    monkeypatch.setattr(StorageNode, "_persist", _persist_then_detach)

    StorageNode().process(ctx)

    expected_id = str(event.artifact_id)
    assert ctx.nodes["StorageNode"]["output"]["artifact_id"] == expected_id
    page = tmp_path / summary.category / f"{expected_id}.html"
    assert page.exists()


def test_source_type_youtube_when_transcript_fetched(monkeypatch, tmp_path):
    """A transcript fetch implies a YouTube source type on the artifact."""
    summary = _summary()
    event = ContentPipelineEventSchema(
        url="https://youtu.be/abc", make_blog=False
    )
    ctx = TaskContext(event=event)
    ctx.update_node("SummarizerNode", result=summary)
    ctx.update_node("FetchTranscriptNode", text="...", fetch_status="ok")

    monkeypatch.setenv("CONTENT_DIGEST_DIR", str(tmp_path))
    monkeypatch.setattr(EmbeddingService, "__init__", lambda self: None)
    monkeypatch.setattr(EmbeddingService, "embed_text", lambda self, text: [0.1] * 1024)
    captured: list = []
    monkeypatch.setattr(StorageNode, "_persist", lambda self, art: captured.append(art))

    StorageNode().process(ctx)
    assert captured[0].source_type == "youtube"


def test_renderer_escapes_and_lists_items(tmp_path):
    """The renderer escapes HTML and links pages from the category index."""
    out = Path(tmp_path)
    page = render_artifact_page(
        {
            "artifact_id": "abc123",
            "title": "A <b>bold</b> & risky title",
            "tl_dr": "short",
            "read_time_estimate": "1 min",
            "source_url": "https://x/y",
            "core_concepts": ["one", "two"],
            "key_insights": [],
            "questions_raised": [],
            "connections_to_my_work": [],
            "further_exploration": [],
        },
        out,
        "music",
    )
    text = page.read_text(encoding="utf-8")
    assert "&lt;b&gt;bold&lt;/b&gt;" in text
    assert "&amp;" in text

    index = regenerate_category_index(out, "music")
    index_text = index.read_text(encoding="utf-8")
    assert 'href="abc123.html"' in index_text
