"""StorageNode — persist, embed, and render every ingested artifact.

For every item (digest-only included) this node: (a) embeds the summary text at
write time via ``EmbeddingService``; (b) persists a ``LearningArtifact`` row
through ``GenericRepository`` using the same ``db_session`` factory the worker
uses — the single persistence seam, so no connection string or deployment
decision lives inside the node (CLAUDE.md rule 7); (c) writes a static HTML
digest page for the item and regenerates its category index.

The output directory comes from ``CONTENT_DIGEST_DIR`` (config/env), never a
hardcoded deployment path. Tests monkeypatch ``_persist`` and the embedding
service so no real DB or Voyage call is made.
"""

import os
from contextlib import contextmanager
from pathlib import Path

from core.nodes.base import Node
from core.task import TaskContext
from database.learning_artifact import LearningArtifact
from database.repository import GenericRepository
from database.session import db_session
from services.embedding_service import EmbeddingService

from workflows.content_pipeline_workflow_nodes.digest_renderer import (
    regenerate_category_index,
    render_artifact_page,
)

# Fetch node names, in priority order. Exactly one runs per request (the source
# router routes to one fetch node); a transcript fetch implies a YouTube source.
_DEFAULT_DIGEST_DIR = "./_digest"


class StorageNode(Node):
    """Persist + embed + render the summarized artifact."""

    def _persist(self, artifact: LearningArtifact) -> None:
        """Persist one artifact via the shared db_session + GenericRepository.

        This is the single persistence seam. It reuses the framework's
        ``db_session`` factory (connection string supplied by
        ``DatabaseUtils``/env), so the node stays deployment-agnostic. Tests
        monkeypatch this method so no real database is touched.
        """
        with contextmanager(db_session)() as session:
            GenericRepository(session=session, model=LearningArtifact).create(artifact)

    def _read_source_meta(self, task_context: TaskContext) -> tuple[str, str]:
        """Return ``(source_type, fetch_status)`` from whichever fetch node ran.

        A ``FetchTranscriptNode`` output implies a YouTube source; otherwise the
        item is treated as an article. An explicit ``source_type`` on the fetch
        node output (if present) wins.
        """
        transcript = task_context.nodes.get("FetchTranscriptNode")
        if transcript is not None:
            fetched, source_type = transcript, "youtube"
        else:
            fetched = task_context.nodes.get("FetchArticleNode") or {}
            source_type = "article"
        source_type = fetched.get("source_type", source_type)
        return source_type, fetched.get("fetch_status", "ok")

    def process(self, task_context: TaskContext) -> TaskContext:
        summary = task_context.get_node_output("SummarizerNode")["result"]
        source_type, fetch_status = self._read_source_meta(task_context)

        embed_text = (
            f"{summary.title}\n{summary.tl_dr}\n{' '.join(summary.core_concepts)}"
        )
        embedding = EmbeddingService().embed_text(embed_text)  # at write time

        # Capture the id before persisting. ``_persist`` commits and closes its
        # session; SQLAlchemy's default ``expire_on_commit`` then expires the
        # instance, so reading ``artifact.id`` afterward would refresh a detached
        # instance and raise ``DetachedInstanceError``. The id is the event's
        # ``artifact_id`` (the row's PK), so read it from the event, not the ORM
        # object, for the digest render and node output below.
        artifact_id = task_context.event.artifact_id
        artifact = LearningArtifact(
            id=artifact_id,
            source_url=task_context.event.url,
            source_type=source_type,
            title=summary.title,
            category=summary.category,
            tl_dr=summary.tl_dr,
            summary=summary.model_dump(),
            embedding=embedding,
            fetch_status=fetch_status,
            make_blog=task_context.event.make_blog,
        )
        self._persist(artifact)

        output_dir = Path(os.getenv("CONTENT_DIGEST_DIR", _DEFAULT_DIGEST_DIR))
        page = render_artifact_page(
            {
                **summary.model_dump(),
                "artifact_id": str(artifact_id),
                "source_url": task_context.event.url,
            },
            output_dir,
            summary.category,
        )
        regenerate_category_index(output_dir, summary.category)

        task_context.update_node(
            self.node_name,
            output={
                "artifact_id": str(artifact_id),
                "page": str(page),
                "category": summary.category,
                "embedded": True,
            },
        )
        return task_context
