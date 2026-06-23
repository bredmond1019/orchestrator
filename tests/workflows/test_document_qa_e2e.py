"""End-to-end smoke tests for DocumentQAWorkflow.

Runs the full five-node pipeline in sequence — EmbedQuestion → RetrieveChunks
→ AssembleContext → Answer → UpdateSessionMemory — with all external services
and DB calls mocked.

The goal is to verify cross-node key contracts end-to-end:
- RetrieveChunksNode reads nothing from EmbedQuestionNode (it re-embeds).
- AssembleContextNode reads {"result": {"chunks": ...}} from RetrieveChunksNode.
- AnswerNode reads {"result": {"context", "history", "question"}} from AssembleContextNode.
- UpdateSessionMemoryNode reads the Pydantic OutputType stored under
  ctx.nodes["AnswerNode"]["result"] — the live runtime path.

This exercises the actual runtime output types (Pydantic model from AnswerNode,
not the plain dict that unit tests seed) and catches cross-node contract drift.
"""

import uuid
from unittest.mock import MagicMock, patch

from core.task import TaskContext
from database.chat_session import ChatSession
from schemas.document_qa_schema import DocumentQAEventSchema
from workflows.document_qa_workflow_nodes.answer_node import AnswerNode
from workflows.document_qa_workflow_nodes.assemble_context_node import AssembleContextNode
from workflows.document_qa_workflow_nodes.embed_question_node import EmbedQuestionNode
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


def _fake_chunks(n: int = 2) -> list[dict]:
    return [
        {
            "content": f"RAG enables grounded answers. Chunk {i}.",
            "section_title": f"Section {i}",
            "score": 0.9 - i * 0.1,
            "source": f"Section {i}",
        }
        for i in range(n)
    ]


class TestDocumentQAPipelineE2E:
    """Full pipeline: all five nodes run in sequence on the same TaskContext."""

    def _run_pipeline(
        self,
        event: DocumentQAEventSchema | None = None,
        prior_turns: list[dict] | None = None,
    ):
        """Run the QA pipeline end-to-end and return (ctx, session_id, persisted)."""
        event = event or _make_event()
        ctx = TaskContext(event=event)
        persisted: list[ChatSession] = []

        # Node 1 — EmbedQuestionNode
        with patch(
            "workflows.document_qa_workflow_nodes.embed_question_node.EmbeddingService"
        ) as MockES:
            MockES.return_value.embed_text.return_value = [0.1] * 1024
            EmbedQuestionNode().process(ctx)

        # Node 2 — RetrieveChunksNode (_semantic_search / _keyword_search mocked)
        node2 = RetrieveChunksNode()
        fake_retrieved = _fake_chunks(2)
        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as MockES:
            MockES.return_value.embed_text.return_value = [0.1] * 1024
            node2._semantic_search = MagicMock(
                return_value=[
                    {
                        "id": uuid.uuid4(),
                        "content": c["content"],
                        "section_title": c["section_title"],
                        "is_section_title": False,
                        "distance": 0.1 + i * 0.05,
                    }
                    for i, c in enumerate(fake_retrieved)
                ]
            )
            node2._keyword_search = MagicMock(return_value=set())
            node2.process(ctx)

        # Node 3 — AssembleContextNode (_load_session mocked)
        node3 = AssembleContextNode()
        if prior_turns:
            prior_session = ChatSession(
                id=event.session_id,
                doc_id=event.doc_id,
                turns=prior_turns,
                topics_covered=[],
            )
            node3._load_session = MagicMock(return_value=prior_session)
        else:
            node3._load_session = MagicMock(return_value=None)
        node3.process(ctx)

        # Node 4 — AnswerNode (agent mocked; uses run_agent_recorded internally)
        node4 = AnswerNode.__new__(AnswerNode)
        node4.agent = MagicMock()
        fake_output = AnswerNode.OutputType(
            answer="RAG is Retrieval-Augmented Generation.",
            cited_sections=["Section 0"],
        )
        fake_run_result = MagicMock()
        fake_run_result.output = fake_output
        fake_run_result.usage.return_value = MagicMock(input_tokens=10, output_tokens=20)
        node4.agent.run_sync.return_value = fake_run_result
        node4.process(ctx)

        # Node 5 — UpdateSessionMemoryNode (_load_session / _persist mocked)
        node5 = UpdateSessionMemoryNode()
        node5._load_session = MagicMock(return_value=None)
        node5._persist = MagicMock(side_effect=lambda s: persisted.append(s))
        node5.process(ctx)

        return ctx, event.session_id, persisted

    def test_session_persisted_with_two_turns(self):
        """A fresh session ends with exactly two turns (user + assistant)."""
        _, _, persisted = self._run_pipeline()
        assert len(persisted) == 1
        assert len(persisted[0].turns) == 2

    def test_answer_text_in_persisted_session(self):
        """The answer from AnswerNode appears in the persisted session turns."""
        _, _, persisted = self._run_pipeline()
        turns = persisted[0].turns
        assistant_turn = next(t for t in turns if t["role"] == "assistant")
        assert "RAG" in assistant_turn["content"]

    def test_user_question_in_persisted_session(self):
        """The user question appears as the first turn in the persisted session."""
        event = _make_event(question="How does chunking work?")
        _, _, persisted = self._run_pipeline(event=event)
        assert persisted[0].turns[0]["role"] == "user"
        assert "chunking" in persisted[0].turns[0]["content"].lower()

    def test_cited_sections_in_topics_covered(self):
        """Sections cited by AnswerNode are propagated to topics_covered."""
        _, _, persisted = self._run_pipeline()
        assert "Section 0" in persisted[0].topics_covered

    def test_rag_context_present_in_answer_node_prompt(self):
        """AnswerNode receives a user prompt that includes retrieved chunk content."""
        ctx, _, _ = self._run_pipeline()
        assembled = ctx.nodes["AssembleContextNode"]["result"]
        assert "RAG enables grounded answers" in assembled["context"]

    def test_retrieve_output_key_contract(self):
        """RetrieveChunksNode writes {"result": {"chunks": [...]}} as AssembleContext reads it."""
        ctx, _, _ = self._run_pipeline()
        chunks = ctx.nodes["RetrieveChunksNode"]["result"]["chunks"]
        assert isinstance(chunks, list)
        assert len(chunks) > 0

    def test_answer_node_output_is_pydantic_model(self):
        """AnswerNode stores its OutputType Pydantic model under the 'result' key.

        This is the runtime path that UpdateSessionMemoryNode must handle via
        its hasattr dual-dispatch — confirmed here end-to-end.
        """
        ctx, _, _ = self._run_pipeline()
        answer_result = ctx.nodes["AnswerNode"]["result"]
        assert hasattr(answer_result, "answer"), (
            "AnswerNode must store the OutputType Pydantic model under 'result', "
            "not a plain dict — UpdateSessionMemoryNode reads it via attribute access"
        )
        assert answer_result.answer == "RAG is Retrieval-Augmented Generation."

    def test_prior_session_turns_appear_in_context(self):
        """Prior ChatSession turns are included in the assembled context history."""
        prior = [
            {"role": "user", "content": "What is embedding?"},
            {"role": "assistant", "content": "Embedding maps text to vectors."},
        ]
        ctx, _, _ = self._run_pipeline(prior_turns=prior)
        history = ctx.nodes["AssembleContextNode"]["result"]["history"]
        assert len(history) == 2
        assert history[0]["content"] == "What is embedding?"

    def test_session_id_consistent_through_pipeline(self):
        """The session_id from the event is preserved in the persisted ChatSession."""
        event = _make_event()
        _, session_id, persisted = self._run_pipeline(event=event)
        assert str(persisted[0].id) == str(session_id)
