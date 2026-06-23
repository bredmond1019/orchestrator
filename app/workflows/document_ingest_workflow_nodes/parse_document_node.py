"""ParseDocumentNode — normalises the ingest event into raw text.

Supports two input paths:
- ``content`` (plain text): returned directly.
- ``content_b64`` + ``mime_type`` (binary): base64-decoded and then either
  decoded as UTF-8 (``text/plain``) or extracted via ``pymupdf``
  (``application/pdf``). PDF extraction uses ``fitz.open`` so that tests can
  patch ``fitz.open`` at the module level without needing a real PDF.

Output stored under ``result = {"text": <str>}``.
"""

import base64

import fitz
from core.nodes.base import Node
from core.task import TaskContext


class ParseDocumentNode(Node):
    """Normalise the ingest event into a plain-text string."""

    def process(self, task_context: TaskContext) -> TaskContext:
        event = task_context.event

        if event.content is not None:
            text = event.content
        else:
            raw_bytes = base64.b64decode(event.content_b64)
            if event.mime_type == "text/plain":
                text = raw_bytes.decode("utf-8")
            elif event.mime_type == "application/pdf":
                doc = fitz.open(stream=raw_bytes, filetype="pdf")
                text = "\n".join(page.get_text() for page in doc)
            else:
                raise ValueError(
                    f"Unsupported mime_type for binary content: {event.mime_type!r}"
                )

        task_context.update_node(
            node_name=self.node_name,
            result={"text": text},
        )
        return task_context
