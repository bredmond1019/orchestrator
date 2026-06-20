"""FetchArticleNode — extracts readable article text for the content pipeline."""

from core.nodes.base import Node
from core.task import TaskContext
from schemas.content_pipeline_schema import ContentPipelineEventSchema
from services.article_extraction_service import ArticleExtractionService


class FetchArticleNode(Node):
    """Extract article text from the event's URL.

    Calls ``ArticleExtractionService.extract`` (trafilatura-first, Firecrawl
    fallback — D24). The service never raises: it returns an ``ArticleResult``
    whose ``fetch_status`` is ``"ok"``, ``"fallback_used"``, or ``"failed"``.
    That status is propagated into this node's output so downstream nodes can
    see how the text was obtained.
    """

    def process(self, task_context: TaskContext) -> TaskContext:
        event: ContentPipelineEventSchema = task_context.event
        result = ArticleExtractionService().extract(event.url)
        task_context.update_node(
            self.node_name,
            text=result.text,
            title=result.title,
            fetch_status=result.fetch_status,
        )
        return task_context
