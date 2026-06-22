"""StorageNode — persist and embed the final AutomationRoadmap.

Reads the finished roadmap from either ``ProposalReviseNode`` (revise branch) or
``ProposalWriterNode`` (pass branch), embeds a summary string via
``EmbeddingService``, and stores a ``BrainDocument`` row through
``GenericRepository`` using the ``db_session`` factory seam.

The artifact id is captured from ``task_context.event.artifact_id`` *before*
the session commits, avoiding the ``DetachedInstanceError`` that ``expire_on_commit``
would cause if the id were read from the ORM object after the session closes.
No deployment logic lives here — connection strings and deployment choices
stay in config and the shell (CLAUDE.md rule 7).

Key reading contract:
  - ``ProposalWriterNode`` stores: ``{"result": AutomationRoadmap}``
  - ``ProposalReviseNode`` stores: ``{"result": ProposalReviseNode.OutputType}``
Both use the ``"result"`` key (standard framework agent-node convention).
The revise OutputType carries the corrected roadmap fields; ``_read_final_roadmap``
reconstructs an ``AutomationRoadmap`` from it.
"""

import json
from contextlib import contextmanager

from core.nodes.base import Node
from core.task import TaskContext
from database.brain_document import BrainDocument
from database.repository import GenericRepository
from database.session import db_session
from schemas.proposal_generator_schema import AutomationRoadmap, ScoredCandidate, WorkflowProfile
from services.embedding_service import EmbeddingService


class StorageNode(Node):
    """Persist the final proposal roadmap as a ``BrainDocument`` with embedding."""

    def _build_embed_text(self, roadmap: AutomationRoadmap) -> str:
        """Construct the text string to embed for semantic search.

        Encodes the situation summary and candidate names so future "similar
        past diagnostics" queries can retrieve this proposal.
        """
        candidate_names = "; ".join(c.name for c in roadmap.candidates)
        return f"{roadmap.situation_summary}\n{candidate_names}"

    def _persist(self, doc: BrainDocument) -> None:
        """Persist one BrainDocument via the shared db_session + GenericRepository.

        The single persistence seam — no connection string or deployment
        decision lives inside this node. Tests monkeypatch this method so no
        real database is touched.
        """
        with contextmanager(db_session)() as session:
            GenericRepository(session=session, model=BrainDocument).create(doc)

    def _roadmap_from_revise_output(self, revise_result) -> AutomationRoadmap:
        """Reconstruct an ``AutomationRoadmap`` from a ``ProposalReviseNode.OutputType``.

        The revise node exposes the corrected roadmap via JSON-encoded fields
        (``candidates_json``, ``top_profiles_json``) plus scalar fields.
        This method reassembles them into a validated ``AutomationRoadmap``.
        """
        if isinstance(revise_result, dict):
            candidates_raw = json.loads(revise_result.get("candidates_json", "[]"))
            profiles_raw = json.loads(revise_result.get("top_profiles_json", "[]"))
            return AutomationRoadmap(
                situation_summary=revise_result.get("situation_summary", ""),
                candidates=[ScoredCandidate(**c) for c in candidates_raw],
                top_profiles=[WorkflowProfile(**p) for p in profiles_raw],
                recommended_workflow=revise_result.get("recommended_workflow", ""),
                engagement_scope=revise_result.get("engagement_scope", ""),
                price_range_brl=(
                    revise_result.get("price_range_brl_min", 0),
                    revise_result.get("price_range_brl_max", 0),
                ),
                body_pt=revise_result.get("body_pt"),
                body_en=revise_result.get("body_en"),
            )
        # Pydantic model (ProposalReviseNode.OutputType)
        candidates_raw = json.loads(revise_result.candidates_json)
        profiles_raw = json.loads(revise_result.top_profiles_json)
        return AutomationRoadmap(
            situation_summary=revise_result.situation_summary,
            candidates=[ScoredCandidate(**c) for c in candidates_raw],
            top_profiles=[WorkflowProfile(**p) for p in profiles_raw],
            recommended_workflow=revise_result.recommended_workflow,
            engagement_scope=revise_result.engagement_scope,
            price_range_brl=(revise_result.price_range_brl_min, revise_result.price_range_brl_max),
            body_pt=revise_result.body_pt,
            body_en=revise_result.body_en,
        )

    def _read_final_roadmap(self, task_context: TaskContext) -> AutomationRoadmap:
        """Return the final roadmap from whichever terminal writer ran.

        If the revise branch ran, ``ProposalReviseNode`` output is authoritative.
        Otherwise the ``ProposalWriterNode`` output is used.

        Both nodes store their output under the ``"result"`` key via
        ``update_node(node_name=..., result=...)``, consistent with the
        framework convention for agent nodes. The revise result is a
        ``ProposalReviseNode.OutputType``; we reconstruct an ``AutomationRoadmap``
        from its JSON-encoded fields.
        """
        revise_node_output = task_context.nodes.get("ProposalReviseNode")
        if revise_node_output is not None:
            revise_result = revise_node_output.get("result")
            if revise_result is not None:
                return self._roadmap_from_revise_output(revise_result)

        writer_output = task_context.get_node_output("ProposalWriterNode")
        roadmap_data = writer_output.get("result")

        if isinstance(roadmap_data, AutomationRoadmap):
            return roadmap_data
        return AutomationRoadmap.model_validate(roadmap_data)

    def process(self, task_context: TaskContext) -> TaskContext:
        """Embed and persist the final roadmap; update node output with storage metadata."""
        roadmap = self._read_final_roadmap(task_context)

        # Capture artifact_id from the event before committing. After the
        # session commits and closes, SQLAlchemy's default expire_on_commit
        # would expire ORM attributes, so reading doc.id on a detached instance
        # would either silently return None or raise DetachedInstanceError.
        artifact_id = task_context.event.artifact_id
        company_name = task_context.event.company_name

        embed_text = self._build_embed_text(roadmap)
        embedding = EmbeddingService().embed_text(embed_text)

        file_path = f"proposals/{artifact_id}/roadmap.json"
        doc = BrainDocument(
            id=artifact_id,
            file_path=file_path,
            doc_type="proposal",
            section="AutomationRoadmap",
            content=embed_text,
            embedding=embedding,
        )
        self._persist(doc)

        task_context.update_node(
            self.node_name,
            output={
                "artifact_id": str(artifact_id),
                "file_path": file_path,
                "company_name": company_name,
                "embedded": True,
                "doc_type": "proposal",
            },
        )
        return task_context
