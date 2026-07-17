"""Tests for the confidence-gated abstain path (block OR.L, Task 2).

Covers:
- ``GroundingRouterNode``: routes to ``AbstainNode`` below threshold or on
  zero chunks; falls through to ``AssembleContextNode`` at/above threshold;
  raises the framework's descriptive ``KeyError`` when ``RetrieveChunksNode``
  hasn't run.
- ``AbstainNode``: writes the unified abstain envelope, no LLM call.
- End-to-end (nodes driven directly, matching ``test_document_qa_e2e.py``'s
  style): below-threshold and zero-chunk events abstain without ever
  invoking the agent seam; at/above-threshold events proceed through the
  normal answer path (``abstained: false``); the session turn is persisted
  on both branches.
- ``UpdateSessionMemoryNode``: reads the envelope from whichever of
  ``AnswerNode``/``AbstainNode`` actually ran.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from core.task import TaskContext
from database.chat_session import ChatSession
from schemas.document_qa_schema import DocumentQAEventSchema
from workflows.document_qa_workflow_nodes.abstain_node import (
    ABSTAIN_MESSAGE,
    AbstainNode,
)
from workflows.document_qa_workflow_nodes.answer_node import AnswerNode
from workflows.document_qa_workflow_nodes.assemble_context_node import AssembleContextNode
from workflows.document_qa_workflow_nodes.embed_question_node import EmbedQuestionNode
from workflows.document_qa_workflow_nodes.grounding_router_node import (
    GroundingRouterNode,
)
from workflows.document_qa_workflow_nodes.retrieve_chunks_node import RetrieveChunksNode
from workflows.document_qa_workflow_nodes.update_session_memory_node import (
    UpdateSessionMemoryNode,
)


def _make_event(**overrides) -> DocumentQAEventSchema:
    defaults = {
        "doc_id": uuid.uuid4(),
        "question": "What is RAG?",
        "session_id": uuid.uuid4(),
        "corpus": "content",
    }
    defaults.update(overrides)
    return DocumentQAEventSchema(**defaults)


def _make_ctx(event: DocumentQAEventSchema | None = None) -> TaskContext:
    return TaskContext(event=event or _make_event())


def _seed_retrieve_result(ctx: TaskContext, chunks: list[dict]) -> None:
    """Seed RetrieveChunksNode output following CLAUDE.md rule 9."""
    confidence = RetrieveChunksNode._compute_retrieval_confidence(chunks)
    ctx.nodes["RetrieveChunksNode"] = {
        "result": {"chunks": chunks, "retrieval_confidence": confidence},
    }


def _strong_chunks() -> list[dict]:
    return [{"content": "Strong match content.", "section_title": "Overview", "score": 5.0}]


def _weak_chunks() -> list[dict]:
    return [{"content": "Weak match content.", "section_title": "Aside", "score": -5.0}]


# ---------------------------------------------------------------------------
# GroundingRouterNode
# ---------------------------------------------------------------------------


class TestGroundingRouterNode:
    def test_routes_to_abstain_below_threshold(self):
        # First seed to learn the strong-chunk confidence, then pick a
        # threshold strictly above it so the router is guaranteed to abstain.
        probe_ctx = _make_ctx()
        _seed_retrieve_result(probe_ctx, _strong_chunks())
        confidence = probe_ctx.nodes["RetrieveChunksNode"]["result"]["retrieval_confidence"]

        event = _make_event(confidence_threshold=min(confidence + 0.01, 1.0))
        ctx = _make_ctx(event)
        _seed_retrieve_result(ctx, _strong_chunks())

        router = GroundingRouterNode()
        next_node = router.route(ctx)
        assert isinstance(next_node, AbstainNode)

    def test_routes_to_abstain_on_zero_chunks(self):
        event = _make_event(confidence_threshold=0.0)
        ctx = _make_ctx(event)
        _seed_retrieve_result(ctx, [])

        router = GroundingRouterNode()
        next_node = router.route(ctx)
        assert isinstance(next_node, AbstainNode)

    def test_routes_to_assemble_context_at_or_above_threshold(self):
        event = _make_event(confidence_threshold=0.1)
        ctx = _make_ctx(event)
        _seed_retrieve_result(ctx, _strong_chunks())

        router = GroundingRouterNode()
        next_node = router.route(ctx)
        assert isinstance(next_node, AssembleContextNode)

    def test_process_records_next_node_name(self):
        event = _make_event(confidence_threshold=0.0)
        ctx = _make_ctx(event)
        _seed_retrieve_result(ctx, [])

        router = GroundingRouterNode()
        router.process(ctx)
        assert ctx.nodes["GroundingRouterNode"]["next_node"] == "AbstainNode"

    def test_raises_descriptively_when_retrieve_chunks_missing(self):
        """Router surfaces the framework's descriptive KeyError, not a raw one."""
        ctx = _make_ctx()
        router = GroundingRouterNode()
        with pytest.raises(KeyError, match="RetrieveChunksNode"):
            router.route(ctx)


# ---------------------------------------------------------------------------
# AbstainNode
# ---------------------------------------------------------------------------


class TestAbstainNode:
    def test_writes_unified_abstain_envelope(self):
        ctx = _make_ctx()
        _seed_retrieve_result(ctx, _weak_chunks())

        AbstainNode().process(ctx)

        result = ctx.nodes["AbstainNode"]["result"]
        assert result["answer"] == ABSTAIN_MESSAGE
        assert result["cited_sections"] == []
        assert result["verified_citations"] == []
        assert result["unverified_citations"] == []
        assert result["abstained"] is True
        assert result["corroborated"] is False
        assert result["escalate_to_human"] is True
        assert result["withheld_reason"] == "below_confidence_threshold"

    def test_context_confidence_matches_retrieval_signal(self):
        ctx = _make_ctx()
        _seed_retrieve_result(ctx, _weak_chunks())
        expected = ctx.nodes["RetrieveChunksNode"]["result"]["retrieval_confidence"]

        AbstainNode().process(ctx)

        assert ctx.nodes["AbstainNode"]["result"]["context_confidence"] == expected

    def test_zero_chunks_yields_zero_confidence(self):
        ctx = _make_ctx()
        _seed_retrieve_result(ctx, [])

        AbstainNode().process(ctx)

        assert ctx.nodes["AbstainNode"]["result"]["context_confidence"] == 0.0


# ---------------------------------------------------------------------------
# UpdateSessionMemoryNode — envelope-source dispatch
# ---------------------------------------------------------------------------


class TestUpdateSessionMemoryEnvelopeDispatch:
    def test_reads_from_abstain_node_when_present(self, monkeypatch):
        ctx = _make_ctx()
        _seed_retrieve_result(ctx, [])
        AbstainNode().process(ctx)

        node = UpdateSessionMemoryNode()
        persisted = []
        monkeypatch.setattr(node, "_load_session", lambda sid: None)
        monkeypatch.setattr(node, "_persist", lambda s: persisted.append(s))

        node.process(ctx)

        assert persisted[0].turns[1]["content"] == ABSTAIN_MESSAGE

    def test_reads_from_answer_node_when_present(self, monkeypatch):
        ctx = _make_ctx()
        ctx.nodes["AnswerNode"] = {
            "result": {"answer": "A grounded answer.", "cited_sections": ["Overview"]}
        }

        node = UpdateSessionMemoryNode()
        persisted = []
        monkeypatch.setattr(node, "_load_session", lambda sid: None)
        monkeypatch.setattr(node, "_persist", lambda s: persisted.append(s))

        node.process(ctx)

        assert persisted[0].turns[1]["content"] == "A grounded answer."

    def test_raises_descriptively_when_neither_branch_ran(self):
        ctx = _make_ctx()
        node = UpdateSessionMemoryNode()
        with pytest.raises(KeyError, match="AbstainNode"):
            node.process(ctx)


# ---------------------------------------------------------------------------
# End-to-end: full node sequence driven directly (mirrors test_document_qa_e2e.py)
# ---------------------------------------------------------------------------


class TestAbstainPathEndToEnd:
    def _run_up_to_router(self, event: DocumentQAEventSchema, chunks: list[dict]):
        ctx = _make_ctx(event)
        with patch(
            "workflows.document_qa_workflow_nodes.embed_question_node.EmbeddingService"
        ) as MockES:
            MockES.return_value.embed_text.return_value = [0.1] * 1024
            EmbedQuestionNode().process(ctx)
        _seed_retrieve_result(ctx, chunks)
        return ctx

    def test_below_threshold_abstains_without_agent_call(self, monkeypatch):
        event = _make_event(confidence_threshold=0.999999)
        ctx = self._run_up_to_router(event, _strong_chunks())

        router = GroundingRouterNode()
        next_node = router.route(ctx)
        assert isinstance(next_node, AbstainNode)
        next_node.process(ctx)

        # AnswerNode's agent seam must never be invoked on this branch.
        with patch(
            "workflows.document_qa_workflow_nodes.answer_node.AgentNode.run_agent_recorded"
        ) as mock_agent_call:
            node = UpdateSessionMemoryNode()
            persisted = []
            node._load_session = MagicMock(return_value=None)
            node._persist = lambda s: persisted.append(s)
            node.process(ctx)
            mock_agent_call.assert_not_called()

        assert ctx.nodes["AbstainNode"]["result"]["abstained"] is True
        assert persisted[0].turns[1]["content"] == ABSTAIN_MESSAGE

    def test_zero_chunks_abstains(self):
        event = _make_event(confidence_threshold=0.0)
        ctx = self._run_up_to_router(event, [])

        router = GroundingRouterNode()
        next_node = router.route(ctx)
        assert isinstance(next_node, AbstainNode)
        next_node.process(ctx)

        assert ctx.nodes["AbstainNode"]["result"]["abstained"] is True

    def test_at_or_above_threshold_takes_normal_path(self, monkeypatch):
        event = _make_event(confidence_threshold=0.1)
        ctx = self._run_up_to_router(event, _strong_chunks())

        router = GroundingRouterNode()
        next_node = router.route(ctx)
        assert isinstance(next_node, AssembleContextNode)

        next_node._load_session = MagicMock(return_value=None)
        next_node.process(ctx)

        answer_node = AnswerNode.__new__(AnswerNode)
        answer_node.agent = MagicMock()
        fake_output = AnswerNode.OutputType(
            answer="RAG is Retrieval-Augmented Generation.",
            cited_sections=["Overview"],
        )
        fake_run_result = MagicMock()
        fake_run_result.output = fake_output
        fake_run_result.usage.return_value = MagicMock(input_tokens=10, output_tokens=20)
        answer_node.agent.run_sync.return_value = fake_run_result
        answer_node.process(ctx)

        update_node = UpdateSessionMemoryNode()
        persisted = []
        update_node._load_session = MagicMock(return_value=None)
        update_node._persist = lambda s: persisted.append(s)
        update_node.process(ctx)

        assert "AbstainNode" not in ctx.nodes
        assert persisted[0].turns[1]["content"] == "RAG is Retrieval-Augmented Generation."
