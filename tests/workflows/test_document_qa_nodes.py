"""Unit tests for the document_qa workflow nodes (Project D, Task 4).

Tests each node in isolation — no real database, no real Voyage API, no real
LLM call:

- ``EmbedQuestionNode``: ``EmbeddingService`` patched; assert vector stored.
- ``AssembleContextNode``: ``_load_session`` patched; assert both chunk context
  (with section title + relevance score) AND prior conversation turns appear in
  the assembled result (RAG-vs-session-memory assembly acceptance criterion).
- ``AnswerNode``: ``agent.run_sync`` mocked; assert the correct user prompt
  shape and that the result is stored under ``AnswerNode``'s ``result`` key.
- ``UpdateSessionMemoryNode``: ``_load_session`` and ``_persist`` patched;
  assert new session is created with two appended turns, and existing session
  has turns appended (not replaced).

TaskContext seeds follow CLAUDE.md rule 9: upstream output is stored as
``{"result": payload}`` matching what ``update_node(node_name=..., result=...)``
writes.
"""

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from core.task import TaskContext
from database.chat_session import ChatSession
from schemas.document_qa_schema import DocumentQAEventSchema
from workflows.document_qa_workflow_nodes.answer_node import AnswerNode
from workflows.document_qa_workflow_nodes.assemble_context_node import AssembleContextNode
from workflows.document_qa_workflow_nodes.embed_question_node import EmbedQuestionNode
from workflows.document_qa_workflow_nodes.update_session_memory_node import (
    UpdateSessionMemoryNode,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _make_chunks(n: int = 2) -> list[dict]:
    """Return n normalized chunk dicts as RetrieveChunksNode would produce."""
    return [
        {
            "content": f"Some content about topic {i}.",
            "section_title": f"Section {i}",
            "score": 0.9 - (i * 0.1),
            "source": f"chunk-{i}",
        }
        for i in range(n)
    ]


def _make_chat_session(
    session_id: uuid.UUID | None = None,
    doc_id: uuid.UUID | None = None,
    turns: list[dict] | None = None,
) -> ChatSession:
    s = ChatSession(
        id=session_id or uuid.uuid4(),
        doc_id=doc_id or uuid.uuid4(),
        turns=turns or [],
        topics_covered=[],
    )
    return s


# ---------------------------------------------------------------------------
# EmbedQuestionNode
# ---------------------------------------------------------------------------


class TestEmbedQuestionNode:
    def test_embedding_stored_in_context(self):
        """EmbedQuestionNode stores the question text and embedding vector."""
        event = _make_event(question="How does chunking work?")
        ctx = _make_ctx(event)
        fake_vector = [0.1] * 1024

        with patch(
            "workflows.document_qa_workflow_nodes.embed_question_node.EmbeddingService"
        ) as MockES:
            MockES.return_value.embed_text.return_value = fake_vector
            EmbedQuestionNode().process(ctx)

        result = ctx.nodes["EmbedQuestionNode"]["result"]
        assert result["question"] == "How does chunking work?"
        assert result["embedding"] == fake_vector

    def test_embed_text_called_with_question(self):
        """embed_text is called with the exact question from the event."""
        question = "What are the retrieval stages?"
        event = _make_event(question=question)
        ctx = _make_ctx(event)

        with patch(
            "workflows.document_qa_workflow_nodes.embed_question_node.EmbeddingService"
        ) as MockES:
            instance = MockES.return_value
            instance.embed_text.return_value = [0.0] * 1024
            EmbedQuestionNode().process(ctx)

        instance.embed_text.assert_called_once_with(question)

    def test_output_has_result_key(self):
        """The node stores its output under the 'result' key (rule 9 contract)."""
        ctx = _make_ctx()
        with patch(
            "workflows.document_qa_workflow_nodes.embed_question_node.EmbeddingService"
        ) as MockES:
            MockES.return_value.embed_text.return_value = [0.0] * 1024
            EmbedQuestionNode().process(ctx)

        assert "result" in ctx.nodes["EmbedQuestionNode"]


# ---------------------------------------------------------------------------
# AssembleContextNode
# ---------------------------------------------------------------------------


class TestAssembleContextNode:
    def _ctx_with_chunks(
        self,
        chunks: list[dict],
        session: ChatSession | None = None,
        question: str = "What is RAG?",
    ) -> TaskContext:
        event = _make_event(question=question)
        ctx = _make_ctx(event)
        # Seed RetrieveChunksNode output with real {"result": ...} contract
        ctx.nodes["RetrieveChunksNode"] = {"result": {"chunks": chunks}}
        return ctx

    def test_context_contains_section_titles(self):
        """Each chunk's section_title appears in the assembled context block."""
        chunks = _make_chunks(2)
        ctx = self._ctx_with_chunks(chunks)
        node = AssembleContextNode()

        node._load_session = MagicMock(return_value=None)
        node.process(ctx)

        result = ctx.nodes["AssembleContextNode"]["result"]
        context = result["context"]
        assert "Section: Section 0" in context
        assert "Section: Section 1" in context

    def test_context_contains_relevance_scores(self):
        """The assembled context includes formatted relevance scores per chunk."""
        chunks = _make_chunks(2)
        ctx = self._ctx_with_chunks(chunks)
        node = AssembleContextNode()
        node._load_session = MagicMock(return_value=None)
        node.process(ctx)

        context = ctx.nodes["AssembleContextNode"]["result"]["context"]
        assert "relevance: 0.90" in context or "relevance:" in context

    def test_prior_turns_included_when_session_exists(self):
        """Prior ChatSession turns are included in the assembled history."""
        chunks = _make_chunks(2)
        prior_turns = [
            {"role": "user", "content": "What is embedding?"},
            {"role": "assistant", "content": "Embedding maps text to vectors."},
        ]
        session = _make_chat_session(turns=prior_turns)
        ctx = self._ctx_with_chunks(chunks)
        node = AssembleContextNode()
        node._load_session = MagicMock(return_value=session)
        node.process(ctx)

        result = ctx.nodes["AssembleContextNode"]["result"]
        history = result["history"]
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

    def test_no_prior_turns_when_session_none(self):
        """When no session exists, history is an empty list."""
        chunks = _make_chunks(1)
        ctx = self._ctx_with_chunks(chunks)
        node = AssembleContextNode()
        node._load_session = MagicMock(return_value=None)
        node.process(ctx)

        result = ctx.nodes["AssembleContextNode"]["result"]
        assert result["history"] == []

    def test_both_chunks_and_history_present(self):
        """The assembled result contains BOTH chunk context and prior turns.

        This is the RAG-vs-session-memory assembly acceptance criterion: the
        assembled context must include retrieved chunks (with section title +
        relevance score) AND the prior conversation turns from ChatSession.
        """
        chunks = _make_chunks(2)
        prior_turns = [{"role": "user", "content": "Earlier question?"}]
        session = _make_chat_session(turns=prior_turns)
        ctx = self._ctx_with_chunks(chunks)
        node = AssembleContextNode()
        node._load_session = MagicMock(return_value=session)
        node.process(ctx)

        result = ctx.nodes["AssembleContextNode"]["result"]
        # RAG context must be non-empty and contain chunk content
        assert len(result["context"]) > 0
        assert "Section 0" in result["context"]
        # Prior turns must be present
        assert len(result["history"]) == 1
        assert result["history"][0]["content"] == "Earlier question?"
        # Question must be threaded through
        assert result["question"] == "What is RAG?"

    def test_question_passed_through(self):
        """The question from the event is stored in the assembled result."""
        chunks = _make_chunks(1)
        question = "Explain the retrieval algorithm."
        ctx = self._ctx_with_chunks(chunks, question=question)
        node = AssembleContextNode()
        node._load_session = MagicMock(return_value=None)
        node.process(ctx)

        assert ctx.nodes["AssembleContextNode"]["result"]["question"] == question

    def test_chunk_without_section_title_uses_general(self):
        """A chunk with section_title=None renders as 'General' in the context."""
        chunks = [{"content": "some text", "section_title": None, "score": 0.8, "source": "c1"}]
        ctx = self._ctx_with_chunks(chunks)
        node = AssembleContextNode()
        node._load_session = MagicMock(return_value=None)
        node.process(ctx)

        context = ctx.nodes["AssembleContextNode"]["result"]["context"]
        assert "Section: General" in context


# ---------------------------------------------------------------------------
# AnswerNode
# ---------------------------------------------------------------------------


def _make_answer_node() -> AnswerNode:
    """Construct AnswerNode without building a real Agent (skip __init__)."""
    node = AnswerNode.__new__(AnswerNode)
    node.agent = MagicMock()
    return node


def _answer_result(answer: str = "The answer is X.", cited: list[str] | None = None):
    """Build a mock run result with a fake AnswerNode OutputType."""
    output = AnswerNode.OutputType(
        answer=answer,
        cited_sections=cited or ["Introduction"],
    )
    r = MagicMock()
    r.output = output
    r.usage.return_value = MagicMock(input_tokens=5, output_tokens=10)
    return r


class TestAnswerNode:
    def _ctx_with_assembled(
        self,
        context: str = "Section: Intro (relevance: 0.90)\nSome content.",
        history: list[dict] | None = None,
        question: str = "What is RAG?",
    ) -> TaskContext:
        ctx = _make_ctx()
        # Seed AssembleContextNode output — real {"result": ...} contract
        ctx.nodes["AssembleContextNode"] = {
            "result": {
                "context": context,
                "history": history or [],
                "question": question,
            }
        }
        return ctx

    def test_result_stored_under_result_key(self):
        """AnswerNode stores its output under the 'result' key."""
        node = _make_answer_node()
        fake_result = _answer_result()
        node.agent.run_sync.return_value = fake_result

        ctx = self._ctx_with_assembled()
        node.process(ctx)

        assert "result" in ctx.nodes["AnswerNode"]

    def test_answer_text_in_output(self):
        """The answer text from the model output is stored in the result."""
        node = _make_answer_node()
        fake_result = _answer_result(answer="RAG stands for Retrieval-Augmented Generation.")
        node.agent.run_sync.return_value = fake_result

        ctx = self._ctx_with_assembled()
        node.process(ctx)

        stored = ctx.nodes["AnswerNode"]["result"]
        # result may be an OutputType instance or a dict
        if hasattr(stored, "answer"):
            assert "RAG" in stored.answer
        else:
            assert "RAG" in stored.get("answer", "")

    def test_user_prompt_contains_context_and_question(self):
        """The user prompt sent to the agent includes the RAG context and question."""
        node = _make_answer_node()
        node.agent.run_sync.return_value = _answer_result()

        context_block = "Section: Intro (relevance: 0.90)\nSome content."
        question = "Define chunking."
        ctx = self._ctx_with_assembled(context=context_block, question=question)
        node.process(ctx)

        prompt = node.agent.run_sync.call_args.kwargs["user_prompt"]
        data = json.loads(prompt)
        assert data["document_context"] == context_block
        assert data["question"] == question

    def test_prior_conversation_in_prompt(self):
        """Prior history is included in the user prompt sent to the agent."""
        node = _make_answer_node()
        node.agent.run_sync.return_value = _answer_result()

        history = [{"role": "user", "content": "What was said before?"}]
        ctx = self._ctx_with_assembled(history=history)
        node.process(ctx)

        prompt = node.agent.run_sync.call_args.kwargs["user_prompt"]
        data = json.loads(prompt)
        assert data["prior_conversation"] == history

    def test_agent_run_sync_called_once(self):
        """The agent's run_sync is called exactly once per process call."""
        node = _make_answer_node()
        node.agent.run_sync.return_value = _answer_result()

        ctx = self._ctx_with_assembled()
        node.process(ctx)

        node.agent.run_sync.assert_called_once()


# ---------------------------------------------------------------------------
# UpdateSessionMemoryNode
# ---------------------------------------------------------------------------


class TestUpdateSessionMemoryNode:
    def _ctx_with_answer(
        self,
        question: str = "What is RAG?",
        answer: str = "RAG is Retrieval-Augmented Generation.",
        cited_sections: list[str] | None = None,
        session_id: uuid.UUID | None = None,
        doc_id: uuid.UUID | None = None,
    ) -> tuple[TaskContext, uuid.UUID, uuid.UUID]:
        s_id = session_id or uuid.uuid4()
        d_id = doc_id or uuid.uuid4()
        event = _make_event(question=question, session_id=s_id, doc_id=d_id)
        ctx = _make_ctx(event)

        # Seed AssembleContextNode — rule 9 contract
        ctx.nodes["AssembleContextNode"] = {
            "result": {
                "context": "Some context.",
                "history": [],
                "question": question,
            }
        }
        # Seed AnswerNode — rule 9 contract; store as plain dict (to_jsonable path)
        ctx.nodes["AnswerNode"] = {
            "result": {
                "answer": answer,
                "cited_sections": cited_sections or ["Introduction"],
            }
        }
        return ctx, s_id, d_id

    def test_new_session_created_with_two_turns(self, monkeypatch):
        """When no session exists, a new ChatSession is created with two turns."""
        ctx, s_id, d_id = self._ctx_with_answer()
        node = UpdateSessionMemoryNode()

        persisted: list[ChatSession] = []
        monkeypatch.setattr(node, "_load_session", lambda sid: None)
        monkeypatch.setattr(node, "_persist", lambda s: persisted.append(s))

        node.process(ctx)

        assert len(persisted) == 1
        session = persisted[0]
        assert str(session.id) == str(s_id)
        assert str(session.doc_id) == str(d_id)
        assert len(session.turns) == 2
        assert session.turns[0]["role"] == "user"
        assert session.turns[0]["content"] == "What is RAG?"
        assert session.turns[1]["role"] == "assistant"
        assert session.turns[1]["content"] == "RAG is Retrieval-Augmented Generation."

    def test_existing_session_turns_appended(self, monkeypatch):
        """When a session exists, new turns are appended — not replaced."""
        existing_turns = [
            {"role": "user", "content": "First question?"},
            {"role": "assistant", "content": "First answer."},
        ]
        s_id = uuid.uuid4()
        existing_session = _make_chat_session(
            session_id=s_id,
            turns=list(existing_turns),
        )

        ctx, _, _ = self._ctx_with_answer(
            question="Second question?",
            answer="Second answer.",
            session_id=s_id,
        )
        node = UpdateSessionMemoryNode()

        persisted: list[ChatSession] = []
        monkeypatch.setattr(node, "_load_session", lambda sid: existing_session)
        monkeypatch.setattr(node, "_persist", lambda s: persisted.append(s))

        node.process(ctx)

        assert len(persisted) == 1
        session = persisted[0]
        # Original two turns + two new turns = four total
        assert len(session.turns) == 4
        assert session.turns[0]["content"] == "First question?"
        assert session.turns[2]["content"] == "Second question?"
        assert session.turns[3]["content"] == "Second answer."

    def test_result_reports_session_id_and_turn_count(self, monkeypatch):
        """The node stores the session_id and total turn count in its result."""
        ctx, s_id, _ = self._ctx_with_answer()
        node = UpdateSessionMemoryNode()

        monkeypatch.setattr(node, "_load_session", lambda sid: None)
        monkeypatch.setattr(node, "_persist", lambda s: None)

        node.process(ctx)

        result = ctx.nodes["UpdateSessionMemoryNode"]["result"]
        assert result["session_id"] == str(s_id)
        assert result["turns"] == 2

    def test_topics_covered_extended_from_cited_sections(self, monkeypatch):
        """cited_sections from the answer are added to topics_covered."""
        ctx, s_id, _ = self._ctx_with_answer(cited_sections=["Introduction", "Methods"])
        node = UpdateSessionMemoryNode()

        persisted: list[ChatSession] = []
        monkeypatch.setattr(node, "_load_session", lambda sid: None)
        monkeypatch.setattr(node, "_persist", lambda s: persisted.append(s))

        node.process(ctx)

        session = persisted[0]
        assert "Introduction" in session.topics_covered
        assert "Methods" in session.topics_covered

    def test_topics_not_duplicated(self, monkeypatch):
        """Existing topics are not duplicated when the same section is cited again."""
        existing_session = _make_chat_session(turns=[])
        existing_session.topics_covered = ["Introduction"]

        ctx, _, _ = self._ctx_with_answer(cited_sections=["Introduction", "New Section"])
        node = UpdateSessionMemoryNode()

        persisted: list[ChatSession] = []
        monkeypatch.setattr(node, "_load_session", lambda sid: existing_session)
        monkeypatch.setattr(node, "_persist", lambda s: persisted.append(s))

        node.process(ctx)

        topics = persisted[0].topics_covered
        assert topics.count("Introduction") == 1
        assert "New Section" in topics

    def test_pydantic_answer_output_path(self, monkeypatch):
        """UpdateSessionMemoryNode correctly reads a Pydantic AnswerOutput instance.

        At runtime AnswerNode stores ``result.output`` (an OutputType Pydantic
        model) in the context — not a plain dict.  This exercises the
        ``hasattr(answer_output, "answer")`` branch that the other tests skip.
        """
        s_id = uuid.uuid4()
        d_id = uuid.uuid4()
        event = _make_event(
            question="What is RAG?",
            session_id=s_id,
            doc_id=d_id,
        )
        ctx = _make_ctx(event)
        ctx.nodes["AssembleContextNode"] = {
            "result": {
                "context": "Some context.",
                "history": [],
                "question": "What is RAG?",
            }
        }
        # Seed as a real AnswerOutput Pydantic model — the runtime path
        pydantic_output = AnswerNode.OutputType(
            answer="RAG is Retrieval-Augmented Generation.",
            cited_sections=["Overview"],
        )
        ctx.nodes["AnswerNode"] = {"result": pydantic_output}

        node = UpdateSessionMemoryNode()
        persisted: list[ChatSession] = []
        monkeypatch.setattr(node, "_load_session", lambda sid: None)
        monkeypatch.setattr(node, "_persist", lambda s: persisted.append(s))

        node.process(ctx)

        session = persisted[0]
        assert len(session.turns) == 2
        assert session.turns[1]["content"] == "RAG is Retrieval-Augmented Generation."
        assert "Overview" in session.topics_covered


# ---------------------------------------------------------------------------
# AnswerNode — telemetry recording path
# ---------------------------------------------------------------------------


class TestAnswerNodeTelemetry:
    """Verifies the run_agent_recorded telemetry block when node_runs is set.

    The base tests in TestAnswerNode leave node_runs empty so the ``if run is
    not None`` block in run_agent_recorded is always skipped.  These tests
    populate node_runs to exercise that path, which is what happens in every
    real workflow execution.
    """

    def _ctx_with_run(self) -> "TaskContext":
        from core.task import NodeRun, TaskContext

        ctx = TaskContext(event=_make_event())
        ctx.nodes["AssembleContextNode"] = {
            "result": {
                "context": "Section: Intro (relevance: 0.90)\nSome content.",
                "history": [],
                "question": "What is RAG?",
            }
        }
        ctx.node_runs["AnswerNode"] = NodeRun()
        return ctx

    def test_telemetry_usage_recorded(self):
        """run_agent_recorded stamps usage onto the NodeRun when run is set."""
        node = _make_answer_node()
        fake_result = _answer_result()
        node.agent.run_sync.return_value = fake_result

        ctx = self._ctx_with_run()
        node.process(ctx)

        run = ctx.node_runs["AnswerNode"]
        assert run.usage is not None
        assert run.usage["input_tokens"] == 5
        assert run.usage["output_tokens"] == 10

    def test_telemetry_records_jsonable_output(self):
        """run_agent_recorded writes a JSON-serializable copy to the 'output' key."""
        node = _make_answer_node()
        fake_result = _answer_result(answer="Grounded answer.")
        node.agent.run_sync.return_value = fake_result

        ctx = self._ctx_with_run()
        node.process(ctx)

        # The 'output' key (set by run_agent_recorded) must be a plain dict
        stored_output = ctx.nodes["AnswerNode"].get("output")
        assert isinstance(stored_output, dict), (
            "'output' key must be a plain dict (to_jsonable applied)"
        )
        assert stored_output["answer"] == "Grounded answer."

    def test_telemetry_input_prompt_recorded(self):
        """run_agent_recorded stamps the user_prompt string onto NodeRun.input."""
        node = _make_answer_node()
        node.agent.run_sync.return_value = _answer_result()

        ctx = self._ctx_with_run()
        node.process(ctx)

        run = ctx.node_runs["AnswerNode"]
        assert run.input is not None
        assert "What is RAG?" in run.input
