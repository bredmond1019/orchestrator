"""Tests for deterministic citation verification (block OR.L, Task 3).

Covers:
- ``support_score``: pure-function overlap scoring (supported vs unrelated
  text, empty-answer edge case).
- ``VerifyCitationsNode``: a fabricated (non-retrieved) section title lands
  in ``unverified_citations``; an all-citations-fail answer is withheld
  (``abstained: true``, ``withheld_reason`` set); a genuinely supported
  citation is verified and the envelope reports ``abstained: false``;
  ``corroborated`` is true iff verified citations span >= 2 distinct
  ``file_path``s; ``high_stakes`` + single-source corroboration sets
  ``escalate_to_human`` while still returning the answer; zero citations
  over a non-empty context is withheld too.
- Both the pydantic ``OutputType`` shape and the plain-dict shape (standing
  rule 9 seeding) are accepted from ``AnswerNode``.
"""

import uuid

import pytest

from core.task import TaskContext
from schemas.document_qa_schema import DocumentQAEventSchema
from workflows.document_qa_workflow_nodes.answer_node import AnswerNode
from workflows.document_qa_workflow_nodes.verify_citations_node import (
    SUPPORT_THRESHOLD,
    WITHHELD_MESSAGE,
    VerifyCitationsNode,
    split_sentences,
    support_score,
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


def _seed_retrieve(ctx: TaskContext, chunks: list[dict], confidence: float = 0.9) -> None:
    ctx.nodes["RetrieveChunksNode"] = {
        "result": {"chunks": chunks, "retrieval_confidence": confidence},
    }


def _seed_answer(ctx: TaskContext, answer: str, cited_sections: list[str]) -> None:
    """Seed AnswerNode output following CLAUDE.md standing rule 9."""
    ctx.nodes["AnswerNode"] = {
        "result": {"answer": answer, "cited_sections": cited_sections},
    }


_OVERVIEW_CHUNK = {
    "content": "Retrieval augmented generation combines retrieval with generation.",
    "section_title": "Overview",
    "score": 5.0,
    "file_path": "docs/rag.md",
}
_DETAILS_CHUNK = {
    "content": "The retriever fetches relevant passages before the generator answers.",
    "section_title": "Details",
    "score": 4.0,
    "file_path": "docs/architecture.md",
}


# ---------------------------------------------------------------------------
# support_score / split_sentences — pure-function cases
# ---------------------------------------------------------------------------


class TestSupportScore:
    def test_supported_text_scores_above_threshold(self):
        answer_sentences = split_sentences(
            "Retrieval augmented generation combines retrieval with generation."
        )
        score = support_score(answer_sentences, _OVERVIEW_CHUNK["content"])
        assert score >= SUPPORT_THRESHOLD

    def test_unrelated_text_scores_low(self):
        answer_sentences = split_sentences("Bananas are a great source of potassium.")
        score = support_score(answer_sentences, _OVERVIEW_CHUNK["content"])
        assert score < SUPPORT_THRESHOLD

    def test_empty_answer_yields_zero(self):
        assert support_score([], _OVERVIEW_CHUNK["content"]) == 0.0
        assert support_score([""], _OVERVIEW_CHUNK["content"]) == 0.0

    def test_split_sentences_handles_multiple_sentences(self):
        sentences = split_sentences("First sentence. Second sentence! Third?")
        assert sentences == ["First sentence.", "Second sentence!", "Third?"]

    def test_split_sentences_empty_text(self):
        assert split_sentences("") == []
        assert split_sentences("   ") == []


# ---------------------------------------------------------------------------
# VerifyCitationsNode
# ---------------------------------------------------------------------------


class TestVerifyCitationsNode:
    def test_fabricated_section_lands_in_unverified(self):
        ctx = _make_ctx()
        _seed_retrieve(ctx, [_OVERVIEW_CHUNK])
        _seed_answer(
            ctx,
            "RAG combines retrieval with generation.",
            ["Nonexistent Section"],
        )

        VerifyCitationsNode().process(ctx)

        result = ctx.nodes["VerifyCitationsNode"]["result"]
        titles = [c["section_title"] for c in result["unverified_citations"]]
        assert "Nonexistent Section" in titles
        assert not any(
            c["reason"] == "not_found"
            for c in result["unverified_citations"]
            if c["section_title"] != "Nonexistent Section"
        )

    def test_all_citations_failing_withholds(self):
        ctx = _make_ctx()
        _seed_retrieve(ctx, [_OVERVIEW_CHUNK])
        _seed_answer(ctx, "Something entirely unsupported.", ["Nonexistent Section"])

        VerifyCitationsNode().process(ctx)

        result = ctx.nodes["VerifyCitationsNode"]["result"]
        assert result["abstained"] is True
        assert result["withheld_reason"] == "citations_unverified"
        assert result["answer"] == WITHHELD_MESSAGE
        assert result["verified_citations"] == []
        assert result["cited_sections"] == []

    def test_zero_citations_over_non_empty_context_withholds(self):
        ctx = _make_ctx()
        _seed_retrieve(ctx, [_OVERVIEW_CHUNK])
        _seed_answer(ctx, "An answer with no citations at all.", [])

        VerifyCitationsNode().process(ctx)

        result = ctx.nodes["VerifyCitationsNode"]["result"]
        assert result["abstained"] is True
        assert result["withheld_reason"] == "citations_unverified"

    def test_genuine_supported_citation_is_verified(self):
        ctx = _make_ctx()
        _seed_retrieve(ctx, [_OVERVIEW_CHUNK])
        _seed_answer(
            ctx,
            "Retrieval augmented generation combines retrieval with generation.",
            ["Overview"],
        )

        VerifyCitationsNode().process(ctx)

        result = ctx.nodes["VerifyCitationsNode"]["result"]
        assert result["abstained"] is False
        assert result["withheld_reason"] is None
        verified_titles = [c["section_title"] for c in result["verified_citations"]]
        assert "Overview" in verified_titles
        assert result["answer"] == (
            "Retrieval augmented generation combines retrieval with generation."
        )
        assert result["cited_sections"] == ["Overview"]

    def test_corroborated_true_with_two_distinct_files(self):
        ctx = _make_ctx()
        _seed_retrieve(ctx, [_OVERVIEW_CHUNK, _DETAILS_CHUNK])
        _seed_answer(
            ctx,
            "Retrieval augmented generation combines retrieval with generation. "
            "The retriever fetches relevant passages before the generator answers.",
            ["Overview", "Details"],
        )

        VerifyCitationsNode().process(ctx)

        result = ctx.nodes["VerifyCitationsNode"]["result"]
        assert len(result["verified_citations"]) == 2
        assert result["corroborated"] is True
        assert result["escalate_to_human"] is False

    def test_corroborated_false_with_single_file(self):
        ctx = _make_ctx()
        _seed_retrieve(ctx, [_OVERVIEW_CHUNK])
        _seed_answer(
            ctx,
            "Retrieval augmented generation combines retrieval with generation.",
            ["Overview"],
        )

        VerifyCitationsNode().process(ctx)

        result = ctx.nodes["VerifyCitationsNode"]["result"]
        assert result["corroborated"] is False

    def test_high_stakes_uncorroborated_escalates_but_still_returns_answer(self):
        event = _make_event(high_stakes=True)
        ctx = _make_ctx(event)
        _seed_retrieve(ctx, [_OVERVIEW_CHUNK])
        _seed_answer(
            ctx,
            "Retrieval augmented generation combines retrieval with generation.",
            ["Overview"],
        )

        VerifyCitationsNode().process(ctx)

        result = ctx.nodes["VerifyCitationsNode"]["result"]
        assert result["corroborated"] is False
        assert result["escalate_to_human"] is True
        assert result["abstained"] is False
        assert result["answer"] == (
            "Retrieval augmented generation combines retrieval with generation."
        )

    def test_high_stakes_corroborated_does_not_escalate(self):
        event = _make_event(high_stakes=True)
        ctx = _make_ctx(event)
        _seed_retrieve(ctx, [_OVERVIEW_CHUNK, _DETAILS_CHUNK])
        _seed_answer(
            ctx,
            "Retrieval augmented generation combines retrieval with generation. "
            "The retriever fetches relevant passages before the generator answers.",
            ["Overview", "Details"],
        )

        VerifyCitationsNode().process(ctx)

        result = ctx.nodes["VerifyCitationsNode"]["result"]
        assert result["corroborated"] is True
        assert result["escalate_to_human"] is False

    def test_context_confidence_carried_from_retrieval_signal(self):
        ctx = _make_ctx()
        _seed_retrieve(ctx, [_OVERVIEW_CHUNK], confidence=0.77)
        _seed_answer(
            ctx,
            "Retrieval augmented generation combines retrieval with generation.",
            ["Overview"],
        )

        VerifyCitationsNode().process(ctx)

        assert ctx.nodes["VerifyCitationsNode"]["result"]["context_confidence"] == 0.77

    def test_normalized_title_match_ignores_case_and_heading_marker(self):
        ctx = _make_ctx()
        _seed_retrieve(ctx, [_OVERVIEW_CHUNK])
        _seed_answer(
            ctx,
            "Retrieval augmented generation combines retrieval with generation.",
            ["## overview"],
        )

        VerifyCitationsNode().process(ctx)

        result = ctx.nodes["VerifyCitationsNode"]["result"]
        assert len(result["verified_citations"]) == 1

    def test_accepts_pydantic_output_type_from_answer_node(self):
        ctx = _make_ctx()
        _seed_retrieve(ctx, [_OVERVIEW_CHUNK])
        ctx.nodes["AnswerNode"] = {
            "result": AnswerNode.OutputType(
                answer="Retrieval augmented generation combines retrieval with generation.",
                cited_sections=["Overview"],
            )
        }

        VerifyCitationsNode().process(ctx)

        result = ctx.nodes["VerifyCitationsNode"]["result"]
        assert result["abstained"] is False
        assert len(result["verified_citations"]) == 1

    def test_raises_descriptively_when_answer_node_missing(self):
        ctx = _make_ctx()
        _seed_retrieve(ctx, [_OVERVIEW_CHUNK])
        with pytest.raises(KeyError, match="AnswerNode"):
            VerifyCitationsNode().process(ctx)
