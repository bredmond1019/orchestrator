"""SourceRouterNode — routes a content URL to the matching fetch node.

YouTube URLs (``youtube.com`` / ``youtu.be``) route to ``FetchTranscriptNode``;
everything else falls back to ``FetchArticleNode``. Follows the
``ticket_router_node.py`` shape: ``BaseRouter`` holds an ordered list of
``RouterNode`` rules plus a fallback, and stamps ``{"next_node": ...}`` onto the
task context.
"""

from urllib.parse import urlparse

from core.nodes.base import Node
from core.nodes.router import BaseRouter, RouterNode
from core.task import TaskContext
from schemas.content_pipeline_schema import ContentPipelineEventSchema

from workflows.content_pipeline_workflow_nodes.fetch_article_node import (
    FetchArticleNode,
)
from workflows.content_pipeline_workflow_nodes.fetch_transcript_node import (
    FetchTranscriptNode,
)

_YOUTUBE_HOSTS = ("youtube.com", "youtu.be")


def _is_youtube_url(url: str) -> bool:
    """Return True when ``url``'s host is a YouTube domain (any subdomain)."""
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in _YOUTUBE_HOSTS)


class SourceRouterNode(BaseRouter):
    """Classify the event URL and route to the matching fetch node."""

    def __init__(self):
        self.routes = [YouTubeRouter()]
        self.fallback = FetchArticleNode()


class YouTubeRouter(RouterNode):
    """Route YouTube URLs to the transcript fetch node."""

    def determine_next_node(self, task_context: TaskContext) -> Node | None:
        event: ContentPipelineEventSchema = task_context.event
        if _is_youtube_url(event.url):
            return FetchTranscriptNode()
        return None
