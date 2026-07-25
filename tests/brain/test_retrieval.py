"""Tests for app/brain/retrieval.py — the recall read core (OR.N1 task 1).

Covers `find_exact_id` token recognition, `semantic_search` ordering (mocked
session + embedding service, no live DB/embedding call), and the parity
guard: `recall(q, hybrid=True)` must return the exact same list `hybrid_search`
returns, proving there is one implementation behind both callers.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from brain.retrieval import (
    exact_id_lookup,
    find_exact_id,
    hybrid_search,
    recall,
    semantic_search,
)


def _fake_doc(**overrides) -> SimpleNamespace:
    base = {
        "doc_id": "D26-example",
        "file_path": "docs/decisions/D26-example.md",
        "title": "D26 — Example Decision",
        "section": "",
        "content": "Some chunk content.",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# find_exact_id
# ---------------------------------------------------------------------------


def test_find_exact_id_matches_letter_digit_code():
    assert find_exact_id("What is decision D20 about?") == "D20"


def test_find_exact_id_matches_dotted_code():
    assert find_exact_id("OR.V graph resolver cleanup") == "OR.V"


def test_find_exact_id_matches_multi_segment_dotted_code():
    assert find_exact_id("what does MV.3B.Q cover") == "MV.3B.Q"


def test_find_exact_id_returns_none_for_ordinary_query():
    assert find_exact_id("What is the Bastion program?") is None


# ---------------------------------------------------------------------------
# semantic_search
# ---------------------------------------------------------------------------


def test_semantic_search_embeds_query_and_returns_ordered_rows():
    fake_embedding_service = MagicMock()
    fake_embedding_service.embed_text.return_value = [0.1, 0.2, 0.3]

    fake_rows = [(_fake_doc(), 0.12), (_fake_doc(file_path="docs/other.md"), 0.45)]
    fake_query = MagicMock()
    fake_query.order_by.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.all.return_value = fake_rows
    fake_session = MagicMock()
    fake_session.query.return_value = fake_query

    with patch("database.brain_document.BrainDocument") as fake_model:
        fake_model.embedding.cosine_distance.return_value.label.return_value = "distance"
        results = semantic_search(
            "What is Bastion?", fake_session, fake_embedding_service, limit=2
        )

    fake_embedding_service.embed_text.assert_called_once_with("What is Bastion?")
    fake_query.limit.assert_called_once_with(2)
    assert results == fake_rows


# ---------------------------------------------------------------------------
# exact_id_lookup
# ---------------------------------------------------------------------------


def test_exact_id_lookup_queries_doc_id_and_file_path_ilike():
    fake_doc = _fake_doc(file_path="docs/decisions/D20-shared-data-contract.md")
    fake_query = MagicMock()
    fake_query.filter.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.all.return_value = [fake_doc]
    fake_session = MagicMock()
    fake_session.query.return_value = fake_query

    with (
        patch("database.brain_document.BrainDocument") as fake_model,
        patch("sqlalchemy.or_") as fake_or,
    ):
        fake_or.return_value = "fake-or-clause"
        results = exact_id_lookup("D20", fake_session, limit=5)

    fake_session.query.assert_called_once_with(fake_model)
    fake_query.limit.assert_called_once_with(5)
    assert results == [fake_doc]


# ---------------------------------------------------------------------------
# recall() — parity guard + dispatch
# ---------------------------------------------------------------------------


def test_recall_hybrid_true_returns_identical_list_to_hybrid_search():
    fake_node = MagicMock()
    fake_chunks = [{"file_path": "docs/decisions/D26-example.md", "score": 1.23}]
    fake_node.retrieve.return_value = fake_chunks

    with patch(
        "workflows.document_qa_workflow_nodes.retrieve_chunks_node.RetrieveChunksNode",
        return_value=fake_node,
    ):
        expected = hybrid_search("What is decision D20 about?", limit=3)

    with patch(
        "workflows.document_qa_workflow_nodes.retrieve_chunks_node.RetrieveChunksNode",
        return_value=fake_node,
    ):
        actual = recall("What is decision D20 about?", limit=3, hybrid=True)

    assert actual == expected == fake_chunks


def test_recall_exact_id_short_circuits_without_embedding_call():
    fake_doc = _fake_doc(file_path="docs/decisions/D20-shared-data-contract.md")
    fake_query = MagicMock()
    fake_query.filter.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.all.return_value = [fake_doc]
    fake_session = MagicMock()
    fake_session.query.return_value = fake_query
    fake_embedding_service = MagicMock()

    with (
        patch("database.brain_document.BrainDocument"),
        patch("sqlalchemy.or_"),
    ):
        results = recall(
            "What is decision D20 about?",
            session=fake_session,
            embedding_service=fake_embedding_service,
        )

    fake_embedding_service.embed_text.assert_not_called()
    assert results == [
        {
            "doc_id": "D26-example",
            "file_path": "docs/decisions/D20-shared-data-contract.md",
            "title": "D26 — Example Decision",
            "section": "",
            "content": "Some chunk content.",
            "score": 0.0,
            "via": "exact-id",
        }
    ]


def test_recall_non_id_query_uses_semantic_search():
    fake_embedding_service = MagicMock()
    fake_embedding_service.embed_text.return_value = [0.1, 0.2, 0.3]
    fake_doc = _fake_doc()
    fake_query = MagicMock()
    fake_query.order_by.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.all.return_value = [(fake_doc, 0.42)]
    fake_session = MagicMock()
    fake_session.query.return_value = fake_query

    with patch("database.brain_document.BrainDocument") as fake_model:
        fake_model.embedding.cosine_distance.return_value.label.return_value = "distance"
        results = recall(
            "What is the Bastion program?",
            session=fake_session,
            embedding_service=fake_embedding_service,
        )

    fake_embedding_service.embed_text.assert_called_once_with("What is the Bastion program?")
    assert results == [
        {
            "doc_id": "D26-example",
            "file_path": "docs/decisions/D26-example.md",
            "title": "D26 — Example Decision",
            "section": "",
            "content": "Some chunk content.",
            "score": 0.42,
            "via": "semantic",
        }
    ]
