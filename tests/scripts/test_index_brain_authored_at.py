"""Unit tests for scripts/index_brain.py's authored_at persistence + backfill.

Block OR.M Task 5 correction 3: authored_at is the real authoring-freshness
signal (file mtime), persisted on every upsert — distinct from indexed_at,
which --rebuild resets to datetime.now() on every run. These tests cover:

- Every upsert persists authored_at = the file's mtime (BrainDocument
  constructor receives the value the indexer already computes for its
  incremental-skip check).
- --backfill-dates populates authored_at for existing rows via a bulk
  UPDATE, without calling the embedding service (no re-embed).
- --backfill-dates --dry-run reports intent without writing or committing.
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure scripts/ is importable (mirrors tests/test_index_brain.py).
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from index_brain import main  # noqa: E402

_TEST_BRAIN_TOML = """\
[vocab]
layer = ["brain", "engine", "factory", "console", "surface", "infra", "business", "content", "meta"]
status = ["active", "draft", "deprecated", "superseded", "archived"]

[crawl]
skip_dirs = ["target", "node_modules", ".git", ".claude", ".agent", "planning/archive", "venv", ".venv"]

[[repos]]
slug = "brain"
tier = "_root"
repo_path = "."
status_file = "planning/status.md"
cache_doc = "README.md"
heading = "Company Brain"
"""


@pytest.fixture(autouse=True)
def _auto_brain_toml(tmp_path):
    """Make every test's tmp_path a valid brain root (mirrors test_index_brain.py)."""
    (tmp_path / "brain.toml").write_text(_TEST_BRAIN_TOML, encoding="utf-8")


def _make_mock_session(mock_doc=None) -> MagicMock:
    """Build a chainable MagicMock SQLAlchemy session usable as a context manager."""
    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.filter_by.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.first.return_value = mock_doc
    mock_query.delete.return_value = 0
    mock_query.update.return_value = 1
    mock_session.query.return_value = mock_query
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    return mock_session


class TestAuthoredAtPersistedOnUpsert:
    """Every normal-indexing upsert persists authored_at = file mtime."""

    def test_authored_at_matches_file_mtime(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        doc_path = docs / "career.md"
        doc_path.write_text("# Career\n\nSome content.\n", encoding="utf-8")

        captured_docs: list = []

        def fake_db_session():
            mock_session = _make_mock_session(mock_doc=None)
            real_add = mock_session.add

            def capturing_add(obj):
                if hasattr(obj, "authored_at"):
                    captured_docs.append(obj)
                return real_add(obj)

            mock_session.add = capturing_add
            yield mock_session

        mock_embed = MagicMock()
        mock_embed.embed_batch.return_value = [[0.1] * 1024]

        with (
            patch("database.session.db_session", fake_db_session),
            patch("services.embedding_service.EmbeddingService", return_value=mock_embed),
        ):
            main(["--brain-path", str(tmp_path)])

        assert len(captured_docs) > 0
        expected_mtime = datetime.fromtimestamp(doc_path.stat().st_mtime)
        for doc in captured_docs:
            assert doc.authored_at == expected_mtime


class TestBackfillDates:
    """--backfill-dates populates authored_at for existing rows, no re-embed."""

    def test_backfill_updates_rows_without_reembedding(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "career.md").write_text("# Career\n\nSome content.\n", encoding="utf-8")

        mock_session = _make_mock_session()

        def fake_db_session():
            yield mock_session

        with (
            patch("database.session.db_session", fake_db_session),
            patch("services.embedding_service.EmbeddingService") as mock_embed_cls,
        ):
            main(["--brain-path", str(tmp_path), "--backfill-dates"])

        mock_session.query.return_value.update.assert_called_once()
        update_kwargs = mock_session.query.return_value.update.call_args[0][0]
        assert "authored_at" in update_kwargs
        mock_session.commit.assert_called_once()
        # No re-embed: the embedding service is never touched.
        mock_embed_cls.assert_not_called()

    def test_backfill_dry_run_writes_nothing(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "career.md").write_text("# Career\n\nSome content.\n", encoding="utf-8")

        mock_session = _make_mock_session()

        def fake_db_session():
            yield mock_session

        with (
            patch("database.session.db_session", fake_db_session),
            patch("services.embedding_service.EmbeddingService") as mock_embed_cls,
        ):
            main(["--brain-path", str(tmp_path), "--backfill-dates", "--dry-run"])

        mock_session.query.return_value.update.assert_not_called()
        mock_session.commit.assert_not_called()
        mock_embed_cls.assert_not_called()
