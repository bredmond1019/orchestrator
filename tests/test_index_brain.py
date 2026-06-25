"""Unit tests for scripts/index_brain.py.

Tests cover:
- chunk_by_section: section-header splitting logic
- doc_type assignment via CORPUS mapping
- incremental skip logic (mocked DB)
- dry-run mode (no DB writes)
- parse_document: frontmatter parsing and stripping
- normalize_metadata: field normalization and vocabulary validation
- build_context_prefix: semantic prefix construction
- integration: embed-text prefix vs stored content separation
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
    build_context_prefix,
    chunk_by_section,
    main,
    normalize_metadata,
    parse_document,
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


# ---------------------------------------------------------------------------
# parse_document tests
# ---------------------------------------------------------------------------


class TestParseDocument:
    """parse_document strips YAML frontmatter and returns (metadata, body)."""

    def test_no_frontmatter_returns_empty_meta_and_full_text(self):
        text = "Just plain text with no frontmatter."
        meta, body = parse_document(text)
        assert meta == {}
        assert "Just plain text" in body

    def test_parses_frontmatter_fields(self):
        text = "---\ntitle: Test Doc\ntype: Strategy\n---\n\n## Section\nContent."
        meta, body = parse_document(text)
        assert meta.get("title") == "Test Doc"
        assert meta.get("type") == "Strategy"

    def test_body_has_no_yaml_delimiters(self):
        text = "---\ntitle: My Doc\n---\n\n## Body\nContent here."
        meta, body = parse_document(text)
        assert "---" not in body
        assert "title: My Doc" not in body

    def test_body_contains_markdown_content(self):
        text = "---\ntitle: Doc\n---\n\n## Section\nActual content."
        _, body = parse_document(text)
        assert "## Section" in body
        assert "Actual content" in body

    def test_rich_frontmatter_fixture(self):
        content = (FIXTURES_DIR / "rich_frontmatter.md").read_text(encoding="utf-8")
        meta, body = parse_document(content)
        assert meta.get("type") == "ProjectContext"
        assert meta.get("title") == "Rich Frontmatter Example"
        assert isinstance(meta.get("layer"), list)
        assert "engine" in meta["layer"]
        assert "---" not in body
        assert "keywords:" not in body

    def test_no_headers_fixture_no_frontmatter(self):
        content = (FIXTURES_DIR / "no_headers.md").read_text(encoding="utf-8")
        meta, body = parse_document(content)
        assert meta == {}
        assert len(body) > 0


# ---------------------------------------------------------------------------
# normalize_metadata tests
# ---------------------------------------------------------------------------


class TestNormalizeMetadata:
    """normalize_metadata produces the six typed OKF filterable fields."""

    def setup_method(self):
        self.brain_path = Path("/fake/brain")
        self.file_path = Path("/fake/brain/docs/test-doc.md")

    def test_empty_meta_derives_doc_id_from_filename(self):
        result = normalize_metadata({}, self.file_path, self.brain_path)
        assert result["doc_id"] == "test-doc"

    def test_explicit_doc_id_is_preserved(self):
        result = normalize_metadata(
            {"doc_id": "my-custom-id"}, self.file_path, self.brain_path
        )
        assert result["doc_id"] == "my-custom-id"

    def test_bare_string_layer_is_coerced_to_list(self):
        result = normalize_metadata(
            {"layer": "brain"}, self.file_path, self.brain_path
        )
        assert result["layer"] == ["brain"]

    def test_list_layer_is_preserved(self):
        result = normalize_metadata(
            {"layer": ["brain", "engine"]}, self.file_path, self.brain_path
        )
        assert result["layer"] == ["brain", "engine"]

    def test_out_of_vocab_layer_warns_but_does_not_raise(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="index_brain"):
            result = normalize_metadata(
                {"layer": "unknown-layer"}, self.file_path, self.brain_path
            )
        assert result["layer"] == ["unknown-layer"]
        assert "Out-of-vocabulary" in caplog.text or "layer" in caplog.text.lower()

    def test_out_of_vocab_project_warns_but_does_not_raise(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="index_brain"):
            result = normalize_metadata(
                {"project": "nonexistent-project"}, self.file_path, self.brain_path
            )
        assert result["project"] == "nonexistent-project"
        assert "Out-of-vocabulary" in caplog.text

    def test_out_of_vocab_status_warns_but_does_not_raise(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="index_brain"):
            result = normalize_metadata(
                {"status": "pending"}, self.file_path, self.brain_path
            )
        assert result["status"] == "pending"
        assert "Out-of-vocabulary" in caplog.text

    def test_keywords_as_list_is_preserved(self):
        result = normalize_metadata(
            {"keywords": ["foo", "bar"]}, self.file_path, self.brain_path
        )
        assert result["keywords"] == ["foo", "bar"]

    def test_related_as_list_is_preserved(self):
        result = normalize_metadata(
            {"related": ["docs/a.md", "docs/b.md"]}, self.file_path, self.brain_path
        )
        assert result["related"] == ["docs/a.md", "docs/b.md"]

    def test_missing_optional_fields_are_none(self):
        result = normalize_metadata({}, self.file_path, self.brain_path)
        assert result["layer"] is None
        assert result["project"] is None
        assert result["status"] is None
        assert result["keywords"] is None
        assert result["related"] is None

    def test_bare_string_layer_fixture(self):
        content = (FIXTURES_DIR / "bare_string_layer.md").read_text(encoding="utf-8")
        meta, _ = parse_document(content)
        result = normalize_metadata(meta, self.file_path, self.brain_path)
        assert isinstance(result["layer"], list)
        assert result["layer"] == ["brain"]


# ---------------------------------------------------------------------------
# build_context_prefix tests
# ---------------------------------------------------------------------------


class TestBuildContextPrefix:
    """build_context_prefix produces a semantic-only embed prefix."""

    def test_empty_meta_returns_empty_string(self):
        assert build_context_prefix({}) == ""

    def test_includes_type(self):
        prefix = build_context_prefix({"type": "Strategy"})
        assert "type: Strategy" in prefix

    def test_includes_title(self):
        prefix = build_context_prefix({"title": "My Doc"})
        assert "title: My Doc" in prefix

    def test_includes_description(self):
        prefix = build_context_prefix({"description": "A short summary."})
        assert "description: A short summary." in prefix

    def test_includes_layer(self):
        prefix = build_context_prefix({"layer": ["brain", "engine"]})
        assert "layer:" in prefix
        assert "brain" in prefix
        assert "engine" in prefix

    def test_includes_project(self):
        prefix = build_context_prefix({"project": "bastion"})
        assert "project: bastion" in prefix

    def test_includes_keywords(self):
        prefix = build_context_prefix({"keywords": ["foo", "bar"]})
        assert "keywords:" in prefix
        assert "foo" in prefix

    def test_excludes_status(self):
        prefix = build_context_prefix({"title": "X", "status": "active"})
        assert "status" not in prefix

    def test_excludes_doc_id(self):
        prefix = build_context_prefix({"title": "X", "doc_id": "my-id"})
        assert "doc_id" not in prefix
        assert "my-id" not in prefix

    def test_excludes_related(self):
        prefix = build_context_prefix({"title": "X", "related": ["docs/a.md"]})
        assert "related" not in prefix
        assert "docs/a.md" not in prefix

    def test_prefix_ends_with_double_newline(self):
        prefix = build_context_prefix({"title": "X"})
        assert prefix.endswith("\n\n")

    def test_bare_string_layer_in_prefix(self):
        prefix = build_context_prefix({"layer": "brain"})
        assert "layer:" in prefix
        assert "brain" in prefix


# ---------------------------------------------------------------------------
# Integration: embed-text prefix vs stored content separation
# ---------------------------------------------------------------------------


class TestFrontmatterIntegration:
    """Integration tests: no frontmatter leaks into stored content; embed text gets prefix."""

    def _make_mock_session(self, mock_doc: MagicMock = None) -> MagicMock:
        """Build a MagicMock SQLAlchemy session that works as a context manager."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.filter_by.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_doc
        mock_query.delete.return_value = 0
        mock_session.query.return_value = mock_query
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        return mock_session

    def test_rich_frontmatter_no_yaml_in_stored_content(self, tmp_path):
        """Stored content must contain no YAML fence or frontmatter field lines.

        Places the rich-frontmatter fixture at docs/brand.md so it matches the
        CORPUS "docs/brand.md" entry.
        """
        docs = tmp_path / "docs"
        docs.mkdir()
        fixture_src = FIXTURES_DIR / "rich_frontmatter.md"
        # Use docs/brand.md — a CORPUS-matched path
        (docs / "brand.md").write_text(
            fixture_src.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (tmp_path / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")

        captured_contents: list[str] = []

        def fake_db_session():
            mock_session = self._make_mock_session(mock_doc=None)
            # Capture BrainDocument content when session.add() is called
            real_add = mock_session.add

            def capturing_add(obj):
                if hasattr(obj, "content"):
                    captured_contents.append(obj.content)
                return real_add(obj)

            mock_session.add = capturing_add
            yield mock_session

        mock_embed = MagicMock()
        mock_embed.embed_batch.return_value = [[0.1] * 1024, [0.2] * 1024]

        with (
            patch("database.session.db_session", fake_db_session),
            patch("services.embedding_service.EmbeddingService", return_value=mock_embed),
        ):
            main(["--brain-path", str(tmp_path)])

        assert len(captured_contents) > 0
        for content in captured_contents:
            assert "---" not in content
            assert "keywords:" not in content
            assert "doc_id:" not in content

    def test_embed_text_starts_with_prefix(self, tmp_path):
        """The text handed to embed_batch must start with the context prefix.

        Places the rich-frontmatter fixture at docs/brand.md so it matches the
        CORPUS "docs/brand.md" entry and the embed texts include the semantic prefix.
        """
        docs = tmp_path / "docs"
        docs.mkdir()
        fixture_src = FIXTURES_DIR / "rich_frontmatter.md"
        # Use docs/brand.md — a CORPUS-matched path
        (docs / "brand.md").write_text(
            fixture_src.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (tmp_path / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")

        def fake_db_session():
            yield self._make_mock_session(mock_doc=None)

        mock_embed = MagicMock()
        mock_embed.embed_batch.return_value = [[0.1] * 1024, [0.2] * 1024]

        with (
            patch("database.session.db_session", fake_db_session),
            patch("services.embedding_service.EmbeddingService", return_value=mock_embed),
        ):
            main(["--brain-path", str(tmp_path)])

        assert mock_embed.embed_batch.called
        # Collect all embed texts across all embed_batch calls
        all_embed_texts: list[str] = []
        for call in mock_embed.embed_batch.call_args_list:
            all_embed_texts.extend(call[0][0])
        # At least one embed text must start with the semantic prefix from the
        # rich frontmatter fixture (MEMORY.md has no frontmatter so no prefix)
        prefixed = [
            t for t in all_embed_texts
            if t.startswith("type:") or t.startswith("title:")
        ]
        assert len(prefixed) > 0, (
            f"Expected at least one embed text with semantic prefix, "
            f"got: {all_embed_texts[:3]}"
        )

    def test_no_frontmatter_doc_still_indexes(self, tmp_path):
        """A doc without frontmatter fields still indexes with defaults.

        Uses docs/career.md — a CORPUS-matched single-file entry.
        """
        docs = tmp_path / "docs"
        docs.mkdir()
        fixture_src = FIXTURES_DIR / "no_headers.md"
        (docs / "career.md").write_text(
            fixture_src.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (tmp_path / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")

        def fake_db_session():
            yield self._make_mock_session(mock_doc=None)

        mock_embed = MagicMock()
        mock_embed.embed_batch.return_value = [[0.1] * 1024]

        with (
            patch("database.session.db_session", fake_db_session),
            patch("services.embedding_service.EmbeddingService", return_value=mock_embed),
        ):
            main(["--brain-path", str(tmp_path)])

        assert mock_embed.embed_batch.called
