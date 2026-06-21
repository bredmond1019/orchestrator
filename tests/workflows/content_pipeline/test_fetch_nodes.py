"""Unit tests for the content_pipeline source router and fetch nodes.

Covers Task 3 of phase1-projectA: SourceRouterNode routing (YouTube vs
article vs unknown fallback) plus the success and graceful-failure paths of
FetchTranscriptNode and FetchArticleNode.
"""

import pytest
from core.task import TaskContext
from schemas.content_pipeline_schema import ContentPipelineEventSchema
from services.article_extraction_service import ArticleResult
from workflows.content_pipeline_workflow_nodes.fetch_article_node import (
    FetchArticleNode,
)
from workflows.content_pipeline_workflow_nodes.fetch_transcript_node import (
    FetchTranscriptNode,
)
from workflows.content_pipeline_workflow_nodes.source_router_node import (
    SourceRouterNode,
)

TRANSCRIPT_PATH = (
    "workflows.content_pipeline_workflow_nodes.fetch_transcript_node.TranscriptService"
)
ARTICLE_PATH = (
    "workflows.content_pipeline_workflow_nodes.fetch_article_node.ArticleExtractionService"
)


def _context(url: str) -> TaskContext:
    return TaskContext(event=ContentPipelineEventSchema(url=url))


# ---------------------------------------------------------------------------
# SourceRouterNode routing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://youtube.com/shorts/abc12345678",
    ],
)
def test_youtube_url_routes_to_transcript_node(url: str):
    ctx = _context(url)
    SourceRouterNode().process(ctx)
    assert ctx.nodes["SourceRouterNode"]["next_node"] == "FetchTranscriptNode"


@pytest.mark.parametrize(
    "url",
    [
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
    ],
)
def test_youtube_subdomain_routes_to_transcript_node(url: str):
    """Real YouTube subdomains match the ``host.endswith("." + h)`` branch."""
    ctx = _context(url)
    SourceRouterNode().process(ctx)
    assert ctx.nodes["SourceRouterNode"]["next_node"] == "FetchTranscriptNode"


@pytest.mark.parametrize(
    "url",
    [
        "https://youtube.com.evil.com/watch?v=dQw4w9WgXcQ",
        "https://notyoutube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be.evil.com/dQw4w9WgXcQ",
    ],
)
def test_youtube_lookalike_host_falls_back_to_article_node(url: str):
    """A host that only *contains* a YouTube domain must not route to transcript.

    Guards the anti-spoofing in ``_is_youtube_url`` — matching requires an exact
    host or a true subdomain, never a suffix like ``youtube.com.evil.com``.
    """
    ctx = _context(url)
    SourceRouterNode().process(ctx)
    assert ctx.nodes["SourceRouterNode"]["next_node"] == "FetchArticleNode"


def test_article_url_routes_to_article_node():
    ctx = _context("https://example.com/blog/some-article")
    SourceRouterNode().process(ctx)
    assert ctx.nodes["SourceRouterNode"]["next_node"] == "FetchArticleNode"


def test_unknown_url_falls_back_to_article_node():
    ctx = _context("not-a-real-url")
    SourceRouterNode().process(ctx)
    assert ctx.nodes["SourceRouterNode"]["next_node"] == "FetchArticleNode"


# ---------------------------------------------------------------------------
# FetchTranscriptNode
# ---------------------------------------------------------------------------


def test_fetch_transcript_success(mocker):
    service = mocker.patch(TRANSCRIPT_PATH)
    service.return_value.fetch_transcript.return_value = "the transcript text"

    ctx = _context("https://youtu.be/dQw4w9WgXcQ")
    FetchTranscriptNode().process(ctx)

    output = ctx.nodes["FetchTranscriptNode"]
    assert output["text"] == "the transcript text"
    assert output["fetch_status"] == "ok"
    service.return_value.fetch_transcript.assert_called_once_with(ctx.event.url)


@pytest.mark.parametrize("exc", [ValueError("bad url"), RuntimeError("no transcript")])
def test_fetch_transcript_failure_does_not_raise(mocker, exc):
    service = mocker.patch(TRANSCRIPT_PATH)
    service.return_value.fetch_transcript.side_effect = exc

    ctx = _context("https://youtu.be/dQw4w9WgXcQ")
    # Must not raise even though the service raised.
    FetchTranscriptNode().process(ctx)

    output = ctx.nodes["FetchTranscriptNode"]
    assert output["fetch_status"] == "failed"
    assert output["text"] == ""


# ---------------------------------------------------------------------------
# FetchArticleNode
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["ok", "fallback_used"])
def test_fetch_article_success_propagates_status(mocker, status):
    service = mocker.patch(ARTICLE_PATH)
    service.return_value.extract.return_value = ArticleResult(
        text="article body", title="A Title", fetch_status=status
    )

    ctx = _context("https://example.com/post")
    FetchArticleNode().process(ctx)

    output = ctx.nodes["FetchArticleNode"]
    assert output["text"] == "article body"
    assert output["title"] == "A Title"
    assert output["fetch_status"] == status
    service.return_value.extract.assert_called_once_with(ctx.event.url)


def test_fetch_article_failure_does_not_raise(mocker):
    service = mocker.patch(ARTICLE_PATH)
    service.return_value.extract.return_value = ArticleResult(
        text="", fetch_status="failed"
    )

    ctx = _context("https://example.com/dead-link")
    FetchArticleNode().process(ctx)

    output = ctx.nodes["FetchArticleNode"]
    assert output["fetch_status"] == "failed"
    assert output["text"] == ""
