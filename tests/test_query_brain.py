"""Unit tests for scripts/query_brain.py.

Tests cover:
- semantic_search: embeds the query via the injected embedding service and
  delegates ordering/limit to the injected session (mocked query chain, no
  live DB or embedding call)
- format_result: header/title/section rendering, optional content snippet
  with truncation ellipsis
- main(): wires embedding service + db_session together end-to-end and
  prints a "no results" message on an empty corpus (mocked seams)
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Ensure scripts/ and app/ are importable, mirroring scripts/test_load_brain_edges.py
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
APP_DIR = Path(__file__).resolve().parent.parent / "app"
for path in (SCRIPTS_DIR, APP_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from query_brain import (  # noqa: E402
    exact_id_lookup,
    find_exact_id,
    format_result,
    main,
    semantic_search,
)


def _fake_doc(**overrides) -> SimpleNamespace:
    base = {
        "file_path": "docs/decisions/D26-example.md",
        "title": "D26 — Example Decision",
        "section": "",
        "content": "Some chunk content.",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


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
        results = semantic_search("What is Bastion?", fake_session, fake_embedding_service, limit=2)

    fake_embedding_service.embed_text.assert_called_once_with("What is Bastion?")
    fake_query.limit.assert_called_once_with(2)
    assert results == fake_rows


# ---------------------------------------------------------------------------
# find_exact_id / exact_id_lookup
# ---------------------------------------------------------------------------


def test_find_exact_id_matches_letter_digit_code():
    assert find_exact_id("What is decision D20 about?") == "D20"


def test_find_exact_id_matches_dotted_code():
    assert find_exact_id("OR.V graph resolver cleanup") == "OR.V"


def test_find_exact_id_matches_multi_segment_dotted_code():
    assert find_exact_id("what does MV.3B.Q cover") == "MV.3B.Q"


def test_find_exact_id_returns_none_for_ordinary_query():
    assert find_exact_id("What is the Bastion program?") is None


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
# format_result
# ---------------------------------------------------------------------------


def test_format_result_without_content():
    doc = _fake_doc(section="Overview")
    rendered = format_result(1, doc, 0.1234, show_content=False, content_chars=200)

    assert "[1] distance=0.1234" in rendered
    assert doc.file_path in rendered
    assert "section: Overview" in rendered
    assert "content:" not in rendered


def test_format_result_with_content_truncates_and_marks_ellipsis():
    doc = _fake_doc(content="x" * 300)
    rendered = format_result(1, doc, 0.5, show_content=True, content_chars=10)

    assert "content: " + "x" * 10 + "…" in rendered


def test_format_result_no_title_falls_back_to_none_marker():
    doc = _fake_doc(title=None)
    rendered = format_result(1, doc, 0.5, show_content=False, content_chars=10)

    assert "title: (none)" in rendered


# ---------------------------------------------------------------------------
# main() — CLI entry point
# ---------------------------------------------------------------------------


def test_main_prints_no_results_message_on_empty_corpus(capsys):
    fake_session = MagicMock()
    fake_query = MagicMock()
    fake_query.order_by.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.all.return_value = []
    fake_session.query.return_value = fake_query

    def _fake_db_session():
        yield fake_session

    with (
        patch("database.session.db_session", side_effect=_fake_db_session),
        patch("services.embedding_service.EmbeddingService") as fake_service_cls,
    ):
        fake_service_cls.return_value.embed_text.return_value = [0.1, 0.2]
        main(["some question"])

    captured = capsys.readouterr()
    assert "No results" in captured.out


def test_main_prints_formatted_results(capsys):
    doc = _fake_doc()
    fake_session = MagicMock()
    fake_query = MagicMock()
    fake_query.order_by.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.all.return_value = [(doc, 0.05)]
    fake_session.query.return_value = fake_query

    def _fake_db_session():
        yield fake_session

    with (
        patch("database.session.db_session", side_effect=_fake_db_session),
        patch("services.embedding_service.EmbeddingService") as fake_service_cls,
    ):
        fake_service_cls.return_value.embed_text.return_value = [0.1, 0.2]
        main(["some question", "--limit", "1"])

    captured = capsys.readouterr()
    assert doc.file_path in captured.out
    fake_query.limit.assert_called_once_with(1)


def test_main_id_query_short_circuits_without_embedding_call(capsys):
    doc = _fake_doc(file_path="docs/decisions/D20-shared-data-contract.md")
    fake_query = MagicMock()
    fake_query.filter.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.all.return_value = [doc]
    fake_session = MagicMock()
    fake_session.query.return_value = fake_query

    def _fake_db_session():
        yield fake_session

    with (
        patch("database.session.db_session", side_effect=_fake_db_session),
        patch("services.embedding_service.EmbeddingService") as fake_service_cls,
    ):
        main(["What is decision D20 about?"])

    fake_service_cls.assert_not_called()
    captured = capsys.readouterr()
    assert doc.file_path in captured.out


def test_main_non_id_query_still_uses_semantic_search(capsys):
    doc = _fake_doc()
    fake_query = MagicMock()
    fake_query.order_by.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.all.return_value = [(doc, 0.05)]
    fake_session = MagicMock()
    fake_session.query.return_value = fake_query

    def _fake_db_session():
        yield fake_session

    with (
        patch("database.session.db_session", side_effect=_fake_db_session),
        patch("services.embedding_service.EmbeddingService") as fake_service_cls,
    ):
        fake_service_cls.return_value.embed_text.return_value = [0.1, 0.2]
        main(["What is the Bastion program?"])

    fake_service_cls.return_value.embed_text.assert_called_once_with("What is the Bastion program?")
    captured = capsys.readouterr()
    assert doc.file_path in captured.out
