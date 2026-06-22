"""Tests for ProposalGeneratorWorkflow StorageNode.

Covers:
- Persistence path: _persist is called with a BrainDocument carrying the
  correct artifact_id, doc_type, file_path, and embedding.
- Embedding path: EmbeddingService.embed_text is called once with a non-empty
  string combining the situation summary and candidate names.
- Post-commit id regression guard: artifact_id is read from the event before
  the session commits, not from the ORM object, preventing DetachedInstanceError.
- Revise-branch precedence: when ProposalReviseNode output is present, it takes
  priority over ProposalWriterNode output.
- Pass-branch fallback: when ProposalReviseNode output is absent, ProposalWriterNode
  output is used.

Key contract (Task 7 integration):
  - ProposalWriterNode stores {"result": AutomationRoadmap} under "ProposalWriterNode"
  - ProposalReviseNode stores {"result": ProposalReviseNode.OutputType} under "ProposalReviseNode"
    (OutputType has candidates_json / top_profiles_json JSON strings)
"""

import json
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from core.task import TaskContext
from schemas.proposal_generator_schema import (
    AutomationRoadmap,
    ScoredCandidate,
    WorkflowProfile,
)
from workflows.proposal_generator_workflow_nodes.proposal_revise_node import (
    ProposalReviseNode,
)
from workflows.proposal_generator_workflow_nodes.storage_node import StorageNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candidate(name: str, f: float = 3.0, t: float = 4.0, b: float = 2.0) -> ScoredCandidate:
    """Build a ScoredCandidate with a consistent composite score."""
    composite = round((f * 0.35) + (t * 0.40) + (b * 0.25), 4)
    return ScoredCandidate(
        name=name,
        problem_statement="Problem statement",
        proposed_solution="Proposed solution",
        estimated_value="High value",
        build_complexity="Medium",
        frequency=f,
        time_cost=t,
        buildability=b,
        composite=composite,
    )


def _make_profile(name: str) -> WorkflowProfile:
    return WorkflowProfile(
        name=name,
        current_state="Manual today",
        proposed_solution="Automate it",
        stack=["Python", "FastAPI"],
        rough_scope_weeks=(4, 6),
        roi_hrs_per_week=5.0,
    )


def _make_roadmap(candidate_names: list[str] | None = None) -> AutomationRoadmap:
    """Build a minimal valid AutomationRoadmap for use in tests."""
    if candidate_names is None:
        candidate_names = ["Order tracking", "Invoice processing", "Customer onboarding"]

    # Build candidates sorted by composite desc (all identical scores here — stable).
    candidates = [_make_candidate(n) for n in candidate_names]
    top_profiles = [_make_profile(n) for n in candidate_names[:3]]

    return AutomationRoadmap(
        situation_summary="Client situation summary.",
        candidates=candidates,
        top_profiles=top_profiles,
        recommended_workflow=candidate_names[0],
        engagement_scope="First 6-week engagement.",
        price_range_brl=(15000, 25000),
    )


def _make_revise_output_type(
    candidate_names: list[str] | None = None,
) -> "ProposalReviseNode.OutputType":
    """Build a ProposalReviseNode.OutputType mirroring a corrected roadmap."""
    if candidate_names is None:
        candidate_names = ["Revise candidate X", "Revise candidate Y", "Revise candidate Z"]
    roadmap = _make_roadmap(candidate_names)
    return ProposalReviseNode.OutputType(
        situation_summary=roadmap.situation_summary,
        candidates_json=json.dumps([c.model_dump() for c in roadmap.candidates]),
        top_profiles_json=json.dumps([p.model_dump() for p in roadmap.top_profiles]),
        recommended_workflow=roadmap.recommended_workflow,
        engagement_scope=roadmap.engagement_scope,
        price_range_brl_min=roadmap.price_range_brl[0],
        price_range_brl_max=roadmap.price_range_brl[1],
        body_pt=None,
        body_en=None,
        revision_notes="Added company name mentions.",
    )


def _make_event(artifact_id: UUID | None = None) -> MagicMock:
    event = MagicMock()
    event.artifact_id = artifact_id or uuid4()
    event.company_name = "Acme Ltda"
    return event


def _make_task_context(
    writer_roadmap: AutomationRoadmap | None = None,
    revise_output: "ProposalReviseNode.OutputType | None" = None,
    artifact_id: UUID | None = None,
) -> TaskContext:
    """Build a TaskContext pre-populated with the given node outputs.

    Uses the framework key contract:
      - ProposalWriterNode stores {"result": roadmap}
      - ProposalReviseNode stores {"result": OutputType}
    """
    event = _make_event(artifact_id)
    nodes = {}
    if writer_roadmap is not None:
        nodes["ProposalWriterNode"] = {"result": writer_roadmap}
    if revise_output is not None:
        nodes["ProposalReviseNode"] = {"result": revise_output}
    return TaskContext(event=event, nodes=nodes)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStorageNodePassBranch:
    """StorageNode reads from ProposalWriterNode when ProposalReviseNode did not run."""

    def test_persist_called_once_with_brain_document(self):
        """_persist is called exactly once with a BrainDocument."""
        roadmap = _make_roadmap()
        ctx = _make_task_context(writer_roadmap=roadmap)

        node = StorageNode()
        fake_embedding = [0.1] * 1024

        with (
            patch.object(node, "_persist") as mock_persist,
            patch(
                "workflows.proposal_generator_workflow_nodes.storage_node.EmbeddingService"
            ) as MockEmbeddingService,
        ):
            MockEmbeddingService.return_value.embed_text.return_value = fake_embedding
            node.process(ctx)

        mock_persist.assert_called_once()
        doc = mock_persist.call_args[0][0]
        assert doc.doc_type == "proposal"
        assert "proposals/" in doc.file_path
        assert str(ctx.event.artifact_id) in doc.file_path
        assert doc.embedding == fake_embedding

    def test_embedding_called_with_nonempty_text(self):
        """EmbeddingService.embed_text is called with a non-empty string."""
        roadmap = _make_roadmap()
        ctx = _make_task_context(writer_roadmap=roadmap)

        node = StorageNode()
        fake_embedding = [0.0] * 1024

        with (
            patch.object(node, "_persist"),
            patch(
                "workflows.proposal_generator_workflow_nodes.storage_node.EmbeddingService"
            ) as MockEmbeddingService,
        ):
            MockEmbeddingService.return_value.embed_text.return_value = fake_embedding
            node.process(ctx)

        call_args = MockEmbeddingService.return_value.embed_text.call_args
        embed_text = call_args[0][0]
        assert isinstance(embed_text, str)
        assert len(embed_text) > 0
        # Situation summary and candidate names must appear in the embed text.
        assert "Client situation summary" in embed_text
        assert "Order tracking" in embed_text

    def test_node_output_contains_artifact_id(self):
        """Node output stores artifact_id as a string (pre-commit capture guard)."""
        artifact_id = uuid4()
        roadmap = _make_roadmap()
        ctx = _make_task_context(writer_roadmap=roadmap, artifact_id=artifact_id)

        node = StorageNode()

        with (
            patch.object(node, "_persist"),
            patch(
                "workflows.proposal_generator_workflow_nodes.storage_node.EmbeddingService"
            ) as MockEmbeddingService,
        ):
            MockEmbeddingService.return_value.embed_text.return_value = [0.0] * 1024
            node.process(ctx)

        output = ctx.nodes["StorageNode"]["output"]
        assert output["artifact_id"] == str(artifact_id)
        assert output["embedded"] is True
        assert output["doc_type"] == "proposal"

    def test_artifact_id_from_event_not_orm(self):
        """Artifact id is captured from the event, not the ORM object.

        This is the regression guard against DetachedInstanceError:
        the id must be stored in the node output *before* the session
        commits — reading it from ``event.artifact_id`` (not ``doc.id``)
        ensures it survives expire_on_commit.
        """
        artifact_id = uuid4()
        roadmap = _make_roadmap()
        ctx = _make_task_context(writer_roadmap=roadmap, artifact_id=artifact_id)

        node = StorageNode()
        persisted_docs = []

        def capture_persist(doc):
            # Simulate expire_on_commit by clearing the ORM id after persist
            persisted_docs.append(doc)
            doc.id = None  # mimic expired attribute

        with (
            patch.object(node, "_persist", side_effect=capture_persist),
            patch(
                "workflows.proposal_generator_workflow_nodes.storage_node.EmbeddingService"
            ) as MockEmbeddingService,
        ):
            MockEmbeddingService.return_value.embed_text.return_value = [0.0] * 1024
            node.process(ctx)

        # Even though the ORM object's id was cleared, the output still holds the
        # correct artifact_id from the pre-commit event capture.
        output = ctx.nodes["StorageNode"]["output"]
        assert output["artifact_id"] == str(artifact_id)


class TestStorageNodeReviseBranch:
    """StorageNode reads from ProposalReviseNode when both writer and revise ran."""

    def test_revise_output_takes_priority_over_writer(self):
        """When ProposalReviseNode ran, its roadmap is used, not ProposalWriterNode's."""
        writer_roadmap = _make_roadmap(["Writer A", "Writer B", "Writer C"])
        revise_output = _make_revise_output_type(
            ["Revise candidate X", "Revise candidate Y", "Revise candidate Z"]
        )
        ctx = _make_task_context(
            writer_roadmap=writer_roadmap,
            revise_output=revise_output,
        )

        node = StorageNode()

        with (
            patch.object(node, "_persist"),
            patch(
                "workflows.proposal_generator_workflow_nodes.storage_node.EmbeddingService"
            ) as MockEmbeddingService,
        ):
            MockEmbeddingService.return_value.embed_text.return_value = [0.0] * 1024
            node.process(ctx)

        embed_text = MockEmbeddingService.return_value.embed_text.call_args[0][0]
        assert "Revise candidate X" in embed_text
        assert "Writer A" not in embed_text

    def test_revise_only_context(self):
        """StorageNode works when only ProposalReviseNode output is present."""
        revise_output = _make_revise_output_type()
        ctx = _make_task_context(revise_output=revise_output)

        node = StorageNode()

        with (
            patch.object(node, "_persist"),
            patch(
                "workflows.proposal_generator_workflow_nodes.storage_node.EmbeddingService"
            ) as MockEmbeddingService,
        ):
            MockEmbeddingService.return_value.embed_text.return_value = [0.0] * 1024
            node.process(ctx)

        output = ctx.nodes["StorageNode"]["output"]
        assert output["embedded"] is True

    def test_revise_reconstructs_valid_roadmap(self):
        """StorageNode correctly reconstructs AutomationRoadmap from revise OutputType."""
        candidate_names = ["Revise A", "Revise B", "Revise C"]
        revise_output = _make_revise_output_type(candidate_names)
        ctx = _make_task_context(revise_output=revise_output)

        node = StorageNode()

        with (
            patch.object(node, "_persist"),
            patch(
                "workflows.proposal_generator_workflow_nodes.storage_node.EmbeddingService"
            ) as MockEmbeddingService,
        ):
            MockEmbeddingService.return_value.embed_text.return_value = [0.0] * 1024
            # Should not raise — roadmap is valid
            node.process(ctx)

        # All candidate names appear in the embedded text
        embed_text = MockEmbeddingService.return_value.embed_text.call_args[0][0]
        for name in candidate_names:
            assert name in embed_text


class TestStorageNodeDocumentStructure:
    """Verify the BrainDocument passed to _persist has the expected structure."""

    def test_brain_document_has_correct_fields(self):
        """BrainDocument is created with artifact_id as id, correct doc_type and section."""
        artifact_id = uuid4()
        roadmap = _make_roadmap()
        ctx = _make_task_context(writer_roadmap=roadmap, artifact_id=artifact_id)

        node = StorageNode()
        captured_docs = []

        with (
            patch.object(node, "_persist", side_effect=lambda d: captured_docs.append(d)),
            patch(
                "workflows.proposal_generator_workflow_nodes.storage_node.EmbeddingService"
            ) as MockEmbeddingService,
        ):
            MockEmbeddingService.return_value.embed_text.return_value = [0.1] * 1024
            node.process(ctx)

        assert len(captured_docs) == 1
        doc = captured_docs[0]
        assert doc.id == artifact_id
        assert doc.doc_type == "proposal"
        assert doc.section == "AutomationRoadmap"
        assert doc.file_path == f"proposals/{artifact_id}/roadmap.json"
        assert len(doc.content) > 0

    def test_roadmap_as_pydantic_model_accepted_directly(self):
        """StorageNode accepts AutomationRoadmap Pydantic model stored as result."""
        roadmap = _make_roadmap()
        ctx = _make_task_context(writer_roadmap=roadmap)

        node = StorageNode()

        with (
            patch.object(node, "_persist"),
            patch(
                "workflows.proposal_generator_workflow_nodes.storage_node.EmbeddingService"
            ) as MockEmbeddingService,
        ):
            MockEmbeddingService.return_value.embed_text.return_value = [0.0] * 1024
            # Should not raise — AutomationRoadmap is handled directly
            node.process(ctx)

    def test_roadmap_as_dict_is_validated(self):
        """StorageNode accepts a roadmap stored as a plain dict in node output."""
        roadmap = _make_roadmap()
        ctx = _make_task_context()
        ctx.nodes["ProposalWriterNode"] = {"result": roadmap.model_dump()}

        node = StorageNode()

        with (
            patch.object(node, "_persist"),
            patch(
                "workflows.proposal_generator_workflow_nodes.storage_node.EmbeddingService"
            ) as MockEmbeddingService,
        ):
            MockEmbeddingService.return_value.embed_text.return_value = [0.0] * 1024
            # Should not raise — AutomationRoadmap.model_validate handles dict input
            node.process(ctx)
