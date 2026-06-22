"""Unit tests for scripts/index_brain.py.

Tests cover:
- chunk_by_section: section-header splitting logic
- doc_type assignment via CORPUS mapping
- incremental skip logic (mocked DB)
- dry-run mode (no DB writes)
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure scripts/ is importable
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from index_brain import (  # noqa: E402
    CORPUS,
    _collect_files,
    _get_doc_type_for_path,
    chunk_by_section,
    main,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "brain_docs"


# ---------------------------------------------------------------------------
# chunk_by_section tests
# ---------------------------------------------------------------------------


class TestChunkBySection:
    """chunk_by_section correctly splits markdown on H2/H3 boundaries."""

    def test_no_headers_returns_single_chunk(self):
        content = "Just plain text with no headers."
        result = chunk_by_section(content)
        assert len(result) == 1
        section, body = result[0]
        assert section == ""
        assert "Just plain text" in body

    def test_h2_header_splits_into_sections(self):
        content = "## Overview\nSome overview text.\n\n## Details\nDetailed info."
        result = chunk_by_section(content)
        assert len(result) == 2
        assert result[0][0] == "## Overview"
        assert "Some overview text" in result[0][1]
        assert result[1][0] == "## Details"
        assert "Detailed info" in result[1][1]

    def test_h3_header_is_also_split(self):
        content = "## Section\nIntro.\n\n### Subsection\nSub content."
        result = chunk_by_section(content)
        assert len(result) == 2
        assert result[0][0] == "## Section"
        assert result[1][0] == "### Subsection"

    def test_preamble_before_first_header_is_captured(self):
        content = "Preamble text.\n\n## First Section\nContent."
        result = chunk_by_section(content)
        assert len(result) == 2
        # First item is the preamble with empty section
        assert result[0][0] == ""
        assert "Preamble text" in result[0][1]
        assert result[1][0] == "## First Section"

    def test_header_included_in_chunk_body(self):
        content = "## My Header\nBody content here."
        result = chunk_by_section(content)
        assert len(result) == 1
        section, body = result[0]
        assert section == "## My Header"
        assert "## My Header" in body
        assert "Body content here" in body

    def test_empty_body_after_header(self):
        content = "## Empty Section"
        result = chunk_by_section(content)
        assert len(result) == 1
        assert result[0][0] == "## Empty Section"

    def test_fixture_career_md(self):
        content = (FIXTURES_DIR / "career.md").read_text(encoding="utf-8")
        result = chunk_by_section(content)
        # Should have preamble + ## Experience + ## Goals + ### Short-term
        assert len(result) >= 3
        sections = [r[0] for r in result]
        assert "## Experience" in sections
        assert "## Goals" in sections
        assert "### Short-term" in sections

    def test_fixture_no_headers_md(self):
        content = (FIXTURES_DIR / "no_headers.md").read_text(encoding="utf-8")
        result = chunk_by_section(content)
        assert len(result) == 1
        assert result[0][0] == ""


# ---------------------------------------------------------------------------
# doc_type assignment tests
# ---------------------------------------------------------------------------


class TestDocTypeAssignment:
    """_get_doc_type_for_path assigns doc_types matching the CORPUS map."""

    def setup_method(self):
        self.brain_path = Path("/fake/brain")

    def test_career_file(self):
        assert (
            _get_doc_type_for_path("/fake/brain/docs/career.md", self.brain_path)
            == "career"
        )

    def test_brand_file(self):
        assert (
            _get_doc_type_for_path("/fake/brain/docs/brand.md", self.brain_path)
            == "brand"
        )

    def test_decision_in_decisions_dir(self):
        assert (
            _get_doc_type_for_path(
                "/fake/brain/docs/decisions/D1.md", self.brain_path
            )
            == "decision"
        )

    def test_project_file(self):
        assert (
            _get_doc_type_for_path(
                "/fake/brain/docs/projects/python-orchestration.md", self.brain_path
            )
            == "project"
        )

    def test_business_file(self):
        assert (
            _get_doc_type_for_path(
                "/fake/brain/docs/business/pipeline.md", self.brain_path
            )
            == "business"
        )

    def test_content_file(self):
        assert (
            _get_doc_type_for_path(
                "/fake/brain/docs/content/ideas.md", self.brain_path
            )
            == "content"
        )

    def test_diagnostic_file(self):
        assert (
            _get_doc_type_for_path(
                "/fake/brain/planning/the-diagnostic/plan.md", self.brain_path
            )
            == "diagnostic"
        )

    def test_memory_file(self):
        assert (
            _get_doc_type_for_path("/fake/brain/MEMORY.md", self.brain_path) == "memory"
        )

    def test_memory_dir_file(self):
        assert (
            _get_doc_type_for_path(
                "/fake/brain/memory/notes.md", self.brain_path
            )
            == "memory"
        )

    def test_unknown_path_falls_back_to_content(self):
        assert (
            _get_doc_type_for_path("/fake/brain/unknown/file.md", self.brain_path)
            == "content"
        )


# ---------------------------------------------------------------------------
# Incremental skip tests
# ---------------------------------------------------------------------------


class TestIncrementalSkip:
    """Files with indexed_at > file mtime are skipped during incremental runs.

    EmbeddingService and db_session are lazily imported inside main(), so they
    must be patched at their source module paths, not at 'index_brain.*'.
    """

    def _make_mock_session(self, mock_doc: MagicMock) -> MagicMock:
        """Build a MagicMock SQLAlchemy session that works as a context manager."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_doc
        mock_query.delete.return_value = 0
        mock_session.query.return_value = mock_query
        # SQLAlchemy Session.__enter__ returns self — MagicMock must do the same.
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        return mock_session

    def test_skip_when_indexed_at_is_newer_than_mtime(self, tmp_path):
        """A file indexed more recently than its mtime should be skipped."""
        docs = tmp_path / "docs"
        docs.mkdir()
        (tmp_path / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
        (docs / "career.md").write_text("## Section\nContent.", encoding="utf-8")

        # Mock: DB returns a recent indexed_at (future timestamp → file is already fresh)
        future_indexed = datetime.now() + timedelta(hours=1)
        mock_doc = MagicMock()
        mock_doc.indexed_at = future_indexed
        mock_session = self._make_mock_session(mock_doc)

        def fake_db_session():
            yield mock_session

        mock_embed = MagicMock()
        mock_embed.embed_batch.return_value = []

        with (
            patch("database.session.db_session", fake_db_session),
            patch("services.embedding_service.EmbeddingService", return_value=mock_embed),
        ):
            main(["--brain-path", str(tmp_path)])
            # embed_batch should not have been called — file was skipped
            mock_embed.embed_batch.assert_not_called()

    def test_no_skip_when_file_is_newer_than_indexed_at(self, tmp_path):
        """A file modified after its indexed_at should be re-indexed."""
        docs = tmp_path / "docs"
        docs.mkdir()
        (tmp_path / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
        (docs / "career.md").write_text("## Section\nContent.", encoding="utf-8")

        # Mock: DB returns an old indexed_at (past → file is newer, must re-index)
        old_indexed = datetime.now() - timedelta(hours=24)
        mock_doc = MagicMock()
        mock_doc.indexed_at = old_indexed
        mock_session = self._make_mock_session(mock_doc)

        def fake_db_session():
            yield mock_session

        mock_embed = MagicMock()
        mock_embed.embed_batch.return_value = [[0.1] * 1024]

        with (
            patch("database.session.db_session", fake_db_session),
            patch("services.embedding_service.EmbeddingService", return_value=mock_embed),
        ):
            main(["--brain-path", str(tmp_path)])
            # embed_batch should have been called — file was re-indexed
            mock_embed.embed_batch.assert_called()


# ---------------------------------------------------------------------------
# Dry-run tests
# ---------------------------------------------------------------------------


class TestDryRun:
    """--dry-run prints file list without writing to DB or calling embed API.

    In dry-run mode, main() returns before importing EmbeddingService or
    db_session, so we verify via output capture and lack of side effects rather
    than patching lazy imports.
    """

    def test_dry_run_no_db_calls(self, tmp_path, caplog):
        """Dry-run with a fixture brain dir logs files and does not hit DB.

        Uses caplog (log record capture) because the logger StreamHandler may
        be bound to sys.stdout before pytest patches it.
        """
        import logging

        docs = tmp_path / "docs"
        docs.mkdir()
        (tmp_path / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
        career = docs / "career.md"
        career.write_text("## Section\nContent.", encoding="utf-8")

        with (
            patch("services.embedding_service.EmbeddingService") as mock_embed_cls,
            patch("database.session.db_session") as mock_db,
            caplog.at_level(logging.INFO, logger="index_brain"),
        ):
            main(["--brain-path", str(tmp_path), "--dry-run"])
            mock_embed_cls.assert_not_called()
            mock_db.assert_not_called()

        log_text = caplog.text
        assert "Dry run" in log_text
        assert "career.md" in log_text

    def test_dry_run_reports_total_file_count(self, tmp_path, caplog):
        """Dry-run output must include a 'Total' file count message."""
        import logging

        docs = tmp_path / "docs"
        docs.mkdir()
        (tmp_path / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
        (docs / "brand.md").write_text("## Brand\nContent.", encoding="utf-8")

        with caplog.at_level(logging.INFO, logger="index_brain"):
            main(["--brain-path", str(tmp_path), "--dry-run"])

        assert "Total:" in caplog.text


# ---------------------------------------------------------------------------
# _collect_files tests
# ---------------------------------------------------------------------------


class TestCollectFiles:
    """_collect_files walks the corpus and returns (path, doc_type) pairs."""

    def test_collects_individual_file(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        career = docs / "career.md"
        career.write_text("# Career", encoding="utf-8")

        result = _collect_files(tmp_path)
        paths = [r[0] for r in result]
        assert career in paths

    def test_skips_underscore_files_in_dirs(self, tmp_path):
        decisions = tmp_path / "docs" / "decisions"
        decisions.mkdir(parents=True)
        (decisions / "_draft.md").write_text("draft", encoding="utf-8")
        (decisions / "D1.md").write_text("real", encoding="utf-8")

        result = _collect_files(tmp_path)
        names = [r[0].name for r in result]
        assert "_draft.md" not in names
        assert "D1.md" in names

    def test_missing_corpus_entry_is_skipped(self, tmp_path):
        # brain_path exists but has no docs/career.md
        docs = tmp_path / "docs"
        docs.mkdir()
        # No career.md created — should be silently skipped
        result = _collect_files(tmp_path)
        paths = [r[0] for r in result]
        for p in paths:
            assert "career.md" not in str(p)
