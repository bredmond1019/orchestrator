"""ChunkDocumentNode — splits the parsed text into overlapping token chunks.

Section-aware chunking (ported from the rag-engine-rs title-weighting hook):

1. The text is split on markdown headers (``#``, ``##``, ``###``).
2. Each header line becomes a standalone ``is_section_title=True`` chunk whose
   ``section_title`` is the header text.
3. The body of each section is further split via ``ChunkingService.chunk_text``
   (500/50 token windows by default). Each body chunk is tagged with the current
   ``section_title`` and ``is_section_title=False``.
4. Text before the first header has ``section_title=None``.
5. A global ``position`` counter increments across all emitted chunks so the
   original reading order is recoverable.

Output: ``result = {"chunks": [{"position", "section_title", "is_section_title",
"content"}, ...]}``.
"""

import re

from core.nodes.base import Node
from core.task import TaskContext
from services.chunking_service import ChunkingService

_HEADER_RE = re.compile(r"^(#{1,3})\s+(.*)$", re.MULTILINE)


def _split_into_sections(text: str) -> list[tuple[str | None, str]]:
    """Return a list of ``(header_text | None, body_text)`` pairs.

    The first pair may have ``header_text=None`` for any content that precedes
    the first markdown header.
    """
    sections: list[tuple[str | None, str]] = []
    last_end = 0
    current_header: str | None = None
    current_start = 0

    for m in _HEADER_RE.finditer(text):
        header_start = m.start()
        header_line = m.group(2).strip()

        # Body of the previous section (or pre-header content)
        body = text[current_start:header_start]
        sections.append((current_header, body))

        current_header = header_line
        current_start = m.end()
        last_end = m.end()

    # Remainder after the last header (or the whole text if no headers)
    trailing_body = text[current_start:]
    sections.append((current_header, trailing_body))
    _ = last_end  # silence unused-variable warning

    return sections


class ChunkDocumentNode(Node):
    """Split parsed text into section-aware, overlapping token chunks."""

    def process(self, task_context: TaskContext) -> TaskContext:
        parse_result = task_context.get_node_output("ParseDocumentNode")["result"]
        text: str = parse_result["text"]

        event = task_context.event
        chunk_size: int = event.chunk_size
        overlap: int = event.overlap

        svc = ChunkingService()
        chunks: list[dict] = []
        position = 0

        sections = _split_into_sections(text)

        for section_title, body in sections:
            # Emit a standalone heading chunk for each header
            if section_title is not None:
                chunks.append(
                    {
                        "position": position,
                        "section_title": section_title,
                        "is_section_title": True,
                        "content": section_title,
                    }
                )
                position += 1

            # Chunk the body text
            if body.strip():
                body_chunks = svc.chunk_text(body, chunk_size=chunk_size, overlap=overlap)
                for c in body_chunks:
                    chunks.append(
                        {
                            "position": position,
                            "section_title": section_title,
                            "is_section_title": False,
                            "content": c,
                        }
                    )
                    position += 1

        task_context.update_node(
            node_name=self.node_name,
            result={"chunks": chunks},
        )
        return task_context
