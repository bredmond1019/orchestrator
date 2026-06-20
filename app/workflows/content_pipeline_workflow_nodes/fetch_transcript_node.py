"""FetchTranscriptNode — pulls a YouTube transcript for the content pipeline."""

import logging

from core.nodes.base import Node
from core.task import TaskContext
from schemas.content_pipeline_schema import ContentPipelineEventSchema
from services.transcript_service import TranscriptService

log = logging.getLogger(__name__)


class FetchTranscriptNode(Node):
    """Fetch the transcript for the event's YouTube URL.

    Calls ``TranscriptService.fetch_transcript`` and stores the raw text under
    this node's output. The service raises ``ValueError`` (bad URL) or
    ``RuntimeError`` (no transcript / empty); both are caught here and recorded
    as ``fetch_status="failed"`` so the pipeline keeps running rather than
    crashing on a single un-fetchable source.
    """

    def process(self, task_context: TaskContext) -> TaskContext:
        event: ContentPipelineEventSchema = task_context.event
        try:
            text = TranscriptService().fetch_transcript(event.url)
            task_context.update_node(
                self.node_name,
                text=text,
                title=None,
                fetch_status="ok",
            )
        except (ValueError, RuntimeError) as e:
            log.warning("Transcript fetch failed for %s: %s", event.url, e)
            task_context.update_node(
                self.node_name,
                text="",
                title=None,
                fetch_status="failed",
            )
        return task_context
