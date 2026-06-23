"""StoreChunksNode — persist embedded ContentChunk rows via GenericRepository.

This node is the single persistence seam for the ingestion pipeline. It mirrors
the ``StorageNode`` pattern from the content pipeline:

- ``_persist`` wraps the DB write in the shared ``db_session`` factory so the
  node stays deployment-agnostic (CLAUDE.md rule 7).
- The ``doc_id`` is read from ``task_context.event`` *before* the persist call
  to avoid ``DetachedInstanceError`` (the expire-on-commit lesson).
- Tests monkeypatch ``_persist`` so no real database is touched.

Output: ``result = {"doc_id": <str>, "chunks_stored": <int>, "embedded": True}``.
"""

from contextlib import contextmanager

from core.nodes.base import Node
from core.task import TaskContext
from database.content_chunk import ContentChunk
from database.repository import GenericRepository
from database.session import db_session


class StoreChunksNode(Node):
    """Persist all embedded ContentChunk rows for the ingested document."""

    def _persist(self, chunks: list[ContentChunk]) -> None:
        """Persist one batch of ContentChunk objects via GenericRepository.

        This is the single persistence seam. Tests monkeypatch this method so
        no real database connection is required.
        """
        with contextmanager(db_session)() as session:
            repo = GenericRepository(session=session, model=ContentChunk)
            for chunk in chunks:
                repo.create(chunk)

    def process(self, task_context: TaskContext) -> TaskContext:
        embed_result = task_context.get_node_output("EmbedChunksNode")["result"]
        embedded_chunks: list[dict] = embed_result["chunks"]

        # Capture doc_id from the event before any DB round-trip (expire-on-commit
        # would make reading it from an ORM object unsafe after the session closes).
        doc_id = task_context.event.doc_id

        orm_chunks = [
            ContentChunk(
                doc_id=doc_id,
                position=c["position"],
                section_title=c.get("section_title"),
                is_section_title=c.get("is_section_title", False),
                content=c["content"],
                embedding=c["embedding"],
            )
            for c in embedded_chunks
        ]

        self._persist(orm_chunks)

        task_context.update_node(
            node_name=self.node_name,
            result={
                "doc_id": str(doc_id),
                "chunks_stored": len(orm_chunks),
                "embedded": True,
            },
        )
        return task_context
