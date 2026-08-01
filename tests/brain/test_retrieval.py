"""Tests for app/brain/retrieval.py — the recall read core (OR.N1 task 1, OR.K2 task 1).

Covers `find_exact_id` token recognition, `semantic_search` ordering (mocked
session + embedding service, no live DB/embedding call), workspace-filter
threading (OR.K2), and the parity guard: `recall(q, hybrid=True)` must return
the exact same list `hybrid_search` returns, proving there is one
implementation behind both callers.
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


def _fake_engine_chunk(**overrides) -> dict:
    """Build a `retrieval_engine.retrieve()`-shaped chunk (pre-normalization)."""
    base = {
        "id": "chunk-1",
        "doc_id": "D99",
        "file_path": "docs/decisions/D99-example.md",
        "title": "D99 — Parity Check",
        "section_title": "",
        "content": "Parity check content.",
        "source": "General",
        "score": 0.9,
        "via": "semantic",
    }
    base.update(overrides)
    return base


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


def test_semantic_search_forwards_filters():
    """A `filters` dict scopes the query via `_apply_metadata_filters` (OR.K2)."""
    fake_embedding_service = MagicMock()
    fake_embedding_service.embed_text.return_value = [0.1, 0.2, 0.3]

    fake_query = MagicMock()
    fake_query.filter.return_value = fake_query
    fake_query.order_by.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.all.return_value = []
    fake_session = MagicMock()
    fake_session.query.return_value = fake_query

    with patch("database.brain_document.BrainDocument") as fake_model:
        fake_model.embedding.cosine_distance.return_value.label.return_value = "distance"
        fake_model.project = MagicMock()
        semantic_search(
            "What is Bastion?",
            fake_session,
            fake_embedding_service,
            limit=2,
            filters={"project": "acme"},
        )

    fake_query.filter.assert_called_once()


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


def test_exact_id_lookup_forwards_filters():
    """A `filters` dict adds a metadata WHERE clause on top of the ILIKE match (OR.K2)."""
    fake_doc = _fake_doc()
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
        fake_model.project = MagicMock()
        results = exact_id_lookup("D20", fake_session, limit=5, filters={"project": "acme"})

    # filter() is called once for the ILIKE or_() clause, once for the project filter.
    assert fake_query.filter.call_count == 2
    assert results == [fake_doc]


# ---------------------------------------------------------------------------
# hybrid_search — delegates to the promoted retrieval_engine, normalizes shape
# ---------------------------------------------------------------------------


def test_hybrid_search_delegates_to_retrieval_engine_and_normalizes_shape():
    engine_chunk = _fake_engine_chunk()

    with patch("brain.retrieval_engine.retrieve", return_value=[engine_chunk]) as mock_retrieve:
        results = hybrid_search("What is decision D99 about?", limit=3)

    mock_retrieve.assert_called_once_with(
        "What is decision D99 about?",
        corpus="brain",
        k=3,
        filters=None,
        workspace_id=None,
        session=None,
        surface=None,
    )
    assert results == [
        {
            "doc_id": "D99",
            "file_path": "docs/decisions/D99-example.md",
            "title": "D99 — Parity Check",
            "section": "",
            "content": "Parity check content.",
            "score": 0.9,
            "via": "semantic",
        }
    ]


def test_hybrid_search_forwards_workspace_as_project_filter():
    with patch("brain.retrieval_engine.retrieve", return_value=[]) as mock_retrieve:
        hybrid_search("q", limit=5, workspace="acme")

    assert mock_retrieve.call_args.kwargs["filters"] == {"project": "acme"}


# ---------------------------------------------------------------------------
# recall() — parity guard + dispatch
# ---------------------------------------------------------------------------


def test_recall_hybrid_true_returns_identical_list_to_hybrid_search():
    engine_chunk = _fake_engine_chunk()

    with patch("brain.retrieval_engine.retrieve", return_value=[engine_chunk]):
        expected = hybrid_search("What is decision D20 about?", limit=3)

    with patch("brain.retrieval_engine.retrieve", return_value=[engine_chunk]):
        actual = recall("What is decision D20 about?", limit=3, hybrid=True)

    assert actual == expected


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
            "score": 1.0,
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
            "score": 1.0 - 0.42,
            "via": "semantic",
        }
    ]


def test_recall_workspace_threads_project_filter_on_exact_id_path():
    fake_doc = _fake_doc()
    fake_query = MagicMock()
    fake_query.filter.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.all.return_value = [fake_doc]
    fake_session = MagicMock()
    fake_session.query.return_value = fake_query

    with (
        patch("database.brain_document.BrainDocument") as fake_model,
        patch("sqlalchemy.or_"),
    ):
        fake_model.project = MagicMock()
        recall("D20", session=fake_session, workspace="acme")

    # One filter() call for the ILIKE or_() clause, one for the project filter.
    assert fake_query.filter.call_count == 2


def test_recall_workspace_threads_project_filter_on_semantic_path():
    fake_embedding_service = MagicMock()
    fake_embedding_service.embed_text.return_value = [0.1, 0.2, 0.3]
    fake_query = MagicMock()
    fake_query.filter.return_value = fake_query
    fake_query.order_by.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.all.return_value = []
    fake_session = MagicMock()
    fake_session.query.return_value = fake_query

    with patch("database.brain_document.BrainDocument") as fake_model:
        fake_model.embedding.cosine_distance.return_value.label.return_value = "distance"
        fake_model.project = MagicMock()
        recall(
            "What is the Bastion program?",
            session=fake_session,
            embedding_service=fake_embedding_service,
            workspace="acme",
        )

    fake_query.filter.assert_called_once()


def test_recall_workspace_threads_into_hybrid_path():
    with patch("brain.retrieval_engine.retrieve", return_value=[]) as mock_retrieve:
        recall("q", hybrid=True, workspace="acme")

    assert mock_retrieve.call_args.kwargs["filters"] == {"project": "acme"}
