"""Unit tests for scripts/index_brain.py.

Tests cover:
- chunk_by_section: section-header splitting logic
- doc_type assignment via the path classifier
- corpus derivation from brain.toml (root walk-up + docs/planning crawl)
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
    _DEFAULT_BRAIN_PATH,
    BrainConfig,
    _classify_doc_type,
    _collect_files,
    _find_brain_root,
    _get_doc_type_for_path,
    _is_header_only_chunk,
    build_context_prefix,
    chunk_by_section,
    main,
    normalize_metadata,
    parse_document,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "brain_docs"

# ---------------------------------------------------------------------------
# Shared test config / brain-root scaffolding
# ---------------------------------------------------------------------------
# The indexer reads its vocab + crawl rules + manifest from brain.toml (HQ
# Restructure Block I). Unit tests that call normalize_metadata / _collect_files
# directly pass this BrainConfig; tests that drive main() write a brain.toml into
# tmp_path so _resolve_brain_path treats it as a brain root and main() can load it.
TEST_CONFIG = BrainConfig(
    valid_layers=frozenset(
        [
            "brain",
            "engine",
            "factory",
            "console",
            "surface",
            "infra",
            "business",
            "content",
            "meta",
        ]
    ),
    valid_projects=frozenset(
        [
            "brain",
            "orchestrator",
            "mev",
            "bastion",
            "bastion-ui",
            "bella",
            "rag-engine-rs",
            "workflow-engine-rs",
            "claude-sdk-rs",
            "amistad",
            "price-scout",
            "learn-ai",
            "base-template",
        ]
    ),
    valid_statuses=frozenset(
        ["active", "draft", "deprecated", "superseded", "archived"]
    ),
    skip_dirs=("planning/archive", "node_modules", ".git"),
    repos=(),
)

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
    """Make every test's tmp_path a valid brain root.

    The indexer's _resolve_brain_path now requires brain.toml as the root marker,
    and main() loads vocab/crawl rules from it. Writing it for every test keeps
    main()-driven tests working without each one repeating the boilerplate; it is
    inert for tests that pass TEST_CONFIG directly (brain.toml is not a *.md file,
    so it never enters the corpus).
    """
    (tmp_path / "brain.toml").write_text(_TEST_BRAIN_TOML, encoding="utf-8")


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
    """_get_doc_type_for_path assigns doc_types via the path classifier."""

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
                "/fake/brain/docs/projects/orchestrator.md", self.brain_path
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
        # The Diagnostic offering now lives in docs/diagnostic (was the
        # nonexistent planning/the-diagnostic path).
        assert (
            _get_doc_type_for_path(
                "/fake/brain/docs/diagnostic/plan.md", self.brain_path
            )
            == "diagnostic"
        )

    def test_claude_md_file(self):
        # CLAUDE.md is newly in the corpus, typed "meta".
        assert (
            _get_doc_type_for_path("/fake/brain/CLAUDE.md", self.brain_path) == "meta"
        )

    def test_planning_dir_file_is_plan(self):
        # Any planning/** path classifies as "plan". (planning/archive is skipped
        # from the corpus entirely via brain.toml [crawl].skip_dirs, so archived
        # docs are no longer embedded; the classifier is doc_type-only metadata.)
        assert (
            _get_doc_type_for_path(
                "/fake/brain/planning/bastion-product/plan.md", self.brain_path
            )
            == "plan"
        )

    def test_tier_prefixed_cache_classifies_as_project(self):
        # A tiered cache path (core/docs/projects/...) classifies the same as its
        # HQ-relative equivalent — the leading tier component is stripped.
        assert (
            _get_doc_type_for_path(
                "/fake/brain/core/docs/projects/bastion.md", self.brain_path
            )
            == "project"
        )

    def test_memory_path_falls_back_to_content(self):
        # memory/ + MEMORY.md are no longer in the corpus (out-of-repo, drift);
        # any such path now resolves to the "content" fallback, not "memory".
        assert (
            _get_doc_type_for_path("/fake/brain/MEMORY.md", self.brain_path) == "content"
        )
        assert (
            _get_doc_type_for_path("/fake/brain/memory/notes.md", self.brain_path)
            == "content"
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


class TestLimit:
    """--limit N caps the corpus to the first N files (pre-rebuild subset check)."""

    def test_limit_caps_file_count(self, tmp_path, caplog):
        """--limit 1 reduces a multi-file corpus to a single file."""
        import logging

        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "career.md").write_text("## A\nContent.", encoding="utf-8")
        (docs / "brand.md").write_text("## B\nContent.", encoding="utf-8")
        (docs / "index.md").write_text("## C\nContent.", encoding="utf-8")

        with caplog.at_level(logging.INFO, logger="index_brain"):
            main(["--brain-path", str(tmp_path), "--dry-run", "--limit", "1"])

        assert "--limit 1: processing first 1 file(s) only" in caplog.text
        assert "Total: 1 files" in caplog.text


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

        result = _collect_files(tmp_path, TEST_CONFIG)
        paths = [r[0] for r in result]
        assert career in paths

    def test_skips_underscore_files_in_dirs(self, tmp_path):
        decisions = tmp_path / "docs" / "decisions"
        decisions.mkdir(parents=True)
        (decisions / "_draft.md").write_text("draft", encoding="utf-8")
        (decisions / "D1.md").write_text("real", encoding="utf-8")

        result = _collect_files(tmp_path, TEST_CONFIG)
        names = [r[0].name for r in result]
        assert "_draft.md" not in names
        assert "D1.md" in names

    def test_missing_corpus_entry_is_skipped(self, tmp_path):
        # brain_path exists but has no docs/career.md
        docs = tmp_path / "docs"
        docs.mkdir()
        # No career.md created — should be silently skipped
        result = _collect_files(tmp_path, TEST_CONFIG)
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
        result = normalize_metadata({}, self.file_path, self.brain_path, TEST_CONFIG)
        assert result["doc_id"] == "test-doc"

    def test_explicit_doc_id_is_preserved(self):
        result = normalize_metadata(
            {"doc_id": "my-custom-id"}, self.file_path, self.brain_path, TEST_CONFIG
        )
        assert result["doc_id"] == "my-custom-id"

    def test_bare_string_layer_is_coerced_to_list(self):
        result = normalize_metadata(
            {"layer": "brain"}, self.file_path, self.brain_path, TEST_CONFIG
        )
        assert result["layer"] == ["brain"]

    def test_list_layer_is_preserved(self):
        result = normalize_metadata(
            {"layer": ["brain", "engine"]}, self.file_path, self.brain_path, TEST_CONFIG
        )
        assert result["layer"] == ["brain", "engine"]

    def test_out_of_vocab_layer_warns_but_does_not_raise(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="index_brain"):
            result = normalize_metadata(
                {"layer": "unknown-layer"}, self.file_path, self.brain_path, TEST_CONFIG
            )
        assert result["layer"] == ["unknown-layer"]
        assert "Out-of-vocabulary" in caplog.text or "layer" in caplog.text.lower()

    def test_out_of_vocab_project_warns_but_does_not_raise(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="index_brain"):
            result = normalize_metadata(
                {"project": "nonexistent-project"}, self.file_path, self.brain_path, TEST_CONFIG
            )
        assert result["project"] == "nonexistent-project"
        assert "Out-of-vocabulary" in caplog.text

    def test_out_of_vocab_status_warns_but_does_not_raise(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="index_brain"):
            result = normalize_metadata(
                {"status": "pending"}, self.file_path, self.brain_path, TEST_CONFIG
            )
        assert result["status"] == "pending"
        assert "Out-of-vocabulary" in caplog.text

    def test_keywords_as_list_is_preserved(self):
        result = normalize_metadata(
            {"keywords": ["foo", "bar"]}, self.file_path, self.brain_path, TEST_CONFIG
        )
        assert result["keywords"] == ["foo", "bar"]

    def test_related_as_list_is_preserved(self):
        result = normalize_metadata(
            {"related": ["docs/a.md", "docs/b.md"]}, self.file_path, self.brain_path, TEST_CONFIG
        )
        assert result["related"] == ["docs/a.md", "docs/b.md"]

    def test_missing_optional_fields_are_none(self):
        result = normalize_metadata({}, self.file_path, self.brain_path, TEST_CONFIG)
        assert result["layer"] is None
        assert result["project"] is None
        assert result["status"] is None
        assert result["keywords"] is None
        assert result["related"] is None

    def test_bare_string_layer_fixture(self):
        content = (FIXTURES_DIR / "bare_string_layer.md").read_text(encoding="utf-8")
        meta, _ = parse_document(content)
        result = normalize_metadata(meta, self.file_path, self.brain_path, TEST_CONFIG)
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


# ---------------------------------------------------------------------------
# Default brain path (cwd-independence)
# ---------------------------------------------------------------------------


class TestIsHeaderOnlyChunk:
    """_is_header_only_chunk measures the header-STRIPPED body (the E4 blocker).

    Because chunk_by_section prepends the header to every chunk's text, a naive
    startswith('#') would flag every chunk. The flag must be False for chunks
    that carry a real body.
    """

    def test_header_with_no_body_is_true(self):
        assert _is_header_only_chunk("## Section", "## Section") is True

    def test_header_with_trivial_body_is_true(self):
        # Stripped body "Tiny." is < 40 chars → still a header-only chunk.
        assert _is_header_only_chunk("## Section", "## Section\nTiny.") is True

    def test_header_with_real_body_is_false(self):
        combined = (
            "## Section\nA real paragraph body that comfortably exceeds the "
            "forty-character threshold."
        )
        assert _is_header_only_chunk("## Section", combined) is False

    def test_guardrail_flag_is_a_mix_not_all_true(self):
        """Across a multi-section doc the flag must be a mix — the E4 guardrail.

        If header-stripping were wrong, every chunk would read as a header.
        """
        content = (
            "## Header Only\n\n"
            "## Has Body\nA long paragraph body that clearly exceeds the forty "
            "character threshold by a wide margin."
        )
        chunks = chunk_by_section(content)
        flags = [_is_header_only_chunk(h, t) for h, t in chunks]
        assert any(flags) and not all(flags)


class TestVocabCaseNormalization:
    """normalize_metadata lowercases layer/project/status before checking + storing.

    The real warning source was capitalization (status: Draft/Active), not a
    vocabulary gap. Lowercasing fixes the whole class of bug.
    """

    def setup_method(self):
        self.brain_path = Path("/fake/brain")
        self.file_path = Path("/fake/brain/docs/test.md")

    def test_project_brain_does_not_warn(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="index_brain"):
            result = normalize_metadata(
                {"project": "brain"}, self.file_path, self.brain_path, TEST_CONFIG
            )
        assert result["project"] == "brain"
        assert "Out-of-vocabulary" not in caplog.text

    def test_layer_surface_singular_does_not_warn(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="index_brain"):
            result = normalize_metadata(
                {"layer": ["surface"]}, self.file_path, self.brain_path, TEST_CONFIG
            )
        assert result["layer"] == ["surface"]
        assert "Out-of-vocabulary" not in caplog.text

    def test_capitalized_status_is_normalized_and_does_not_warn(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="index_brain"):
            draft = normalize_metadata(
                {"status": "Draft"}, self.file_path, self.brain_path, TEST_CONFIG
            )
            active = normalize_metadata(
                {"status": "Active"}, self.file_path, self.brain_path, TEST_CONFIG
            )
        assert draft["status"] == "draft"
        assert active["status"] == "active"
        assert "Out-of-vocabulary" not in caplog.text

    def test_mixed_case_layer_is_normalized(self):
        result = normalize_metadata(
            {"layer": ["Brain", "Engine"]}, self.file_path, self.brain_path, TEST_CONFIG
        )
        assert result["layer"] == ["brain", "engine"]

    def test_superseded_status_is_valid(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="index_brain"):
            result = normalize_metadata(
                {"status": "superseded"}, self.file_path, self.brain_path, TEST_CONFIG
            )
        assert result["status"] == "superseded"
        assert "Out-of-vocabulary" not in caplog.text

    def test_genuinely_bogus_layer_still_warns(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="index_brain"):
            result = normalize_metadata(
                {"layer": ["bogus"]}, self.file_path, self.brain_path, TEST_CONFIG
            )
        assert result["layer"] == ["bogus"]
        assert "Out-of-vocabulary" in caplog.text


class TestCorpusDerivation:
    """_collect_files crawls docs/ + planning/ and honours skip + ephemeral rules."""

    def test_includes_docs_planning_and_root_files(self, tmp_path):
        (tmp_path / "docs" / "diagnostic").mkdir(parents=True)
        (tmp_path / "docs" / "diagnostic" / "plan.md").write_text("# x", encoding="utf-8")
        (tmp_path / "docs" / "okf-frontmatter.md").write_text("# o", encoding="utf-8")
        (tmp_path / "planning").mkdir()
        (tmp_path / "planning" / "status.md").write_text("# s", encoding="utf-8")
        (tmp_path / "CLAUDE.md").write_text("# c", encoding="utf-8")

        rels = {
            p.relative_to(tmp_path).as_posix() for p, _ in _collect_files(tmp_path, TEST_CONFIG)
        }
        assert "docs/diagnostic/plan.md" in rels
        assert "docs/okf-frontmatter.md" in rels
        assert "planning/status.md" in rels
        assert "CLAUDE.md" in rels

    def test_excludes_ephemeral_archive_and_out_of_corpus(self, tmp_path):
        (tmp_path / "planning" / "archive").mkdir(parents=True)
        (tmp_path / "planning" / "archive" / "old.md").write_text("# o", encoding="utf-8")
        (tmp_path / "planning" / "handoff.md").write_text("# h", encoding="utf-8")
        (tmp_path / "MEMORY.md").write_text("# m", encoding="utf-8")
        (tmp_path / "log.md").write_text("# l", encoding="utf-8")

        rels = {
            p.relative_to(tmp_path).as_posix() for p, _ in _collect_files(tmp_path, TEST_CONFIG)
        }
        assert "planning/archive/old.md" not in rels  # [crawl].skip_dirs
        assert "planning/handoff.md" not in rels  # ephemeral
        assert "MEMORY.md" not in rels  # out of repo (not README/CLAUDE)
        assert "log.md" not in rels  # not a crawled root file

    def test_sub_brain_tier_docs_are_collected(self, tmp_path):
        # A tier sub-brain (core/) with its own docs/projects cache is crawled;
        # doc_type classification strips the leading tier component.
        (tmp_path / "core" / "docs" / "projects").mkdir(parents=True)
        (tmp_path / "core" / "docs" / "projects" / "bastion.md").write_text(
            "# b", encoding="utf-8"
        )
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "career.md").write_text("# c", encoding="utf-8")

        by_rel = {
            p.relative_to(tmp_path).as_posix(): dt
            for p, dt in _collect_files(tmp_path, TEST_CONFIG)
        }
        assert by_rel.get("core/docs/projects/bastion.md") == "project"
        assert by_rel.get("docs/career.md") == "career"

    def test_classify_doc_type_relative_rules(self):
        assert _classify_doc_type("docs/decisions/D1.md") == "decision"
        assert _classify_doc_type("docs/projects/x.md") == "project"
        assert _classify_doc_type("docs/brand.md") == "brand"
        assert _classify_doc_type("planning/hq-restructure/plan.md") == "plan"
        assert _classify_doc_type("docs/index.md") == "meta"
        assert _classify_doc_type("README.md") == "meta"
        assert _classify_doc_type("unknown/thing.md") == "content"


class TestNewColumnPopulation:
    """The indexer populates is_section_title/title/description, never content_tsv."""

    def _make_mock_session(self) -> MagicMock:
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None
        mock_query.delete.return_value = 0
        mock_session.query.return_value = mock_query
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        return mock_session

    def test_columns_populated_from_frontmatter_and_body(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        doc = (
            "---\n"
            "title: My Title\n"
            "description: A one-line description.\n"
            "type: ProjectContext\n"
            "---\n\n"
            "## Header Only\n\n"
            "## Has Body\n"
            "A long paragraph body that comfortably exceeds the forty character "
            "threshold for a real section.\n"
        )
        # docs/brand.md is a CORPUS-matched single-file entry.
        (docs / "brand.md").write_text(doc, encoding="utf-8")

        captured: list = []

        def fake_db_session():
            mock_session = self._make_mock_session()

            def capturing_add(obj):
                captured.append(obj)

            mock_session.add = capturing_add
            yield mock_session

        mock_embed = MagicMock()
        mock_embed.embed_batch.return_value = [[0.1] * 1024, [0.2] * 1024]

        with (
            patch("database.session.db_session", fake_db_session),
            patch(
                "services.embedding_service.EmbeddingService",
                return_value=mock_embed,
            ),
        ):
            main(["--brain-path", str(tmp_path)])

        assert len(captured) == 2
        # title + description come from frontmatter on every chunk of the doc.
        assert all(d.title == "My Title" for d in captured)
        assert all(d.description == "A one-line description." for d in captured)
        # is_section_title is a mix (header-only True, body False) — the guardrail.
        flags = [d.is_section_title for d in captured]
        assert any(flags) and not all(flags)
        # content_tsv is a generated column — the indexer must never set it.
        assert all(getattr(d, "content_tsv", None) is None for d in captured)

    def test_missing_title_stores_none(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        # No frontmatter title/description.
        (docs / "career.md").write_text(
            "## Section\nA paragraph body with enough length to be a real chunk here.",
            encoding="utf-8",
        )

        captured: list = []

        def fake_db_session():
            mock_session = self._make_mock_session()

            def capturing_add(obj):
                captured.append(obj)

            mock_session.add = capturing_add
            yield mock_session

        mock_embed = MagicMock()
        mock_embed.embed_batch.return_value = [[0.1] * 1024]

        with (
            patch("database.session.db_session", fake_db_session),
            patch(
                "services.embedding_service.EmbeddingService",
                return_value=mock_embed,
            ),
        ):
            main(["--brain-path", str(tmp_path)])

        assert len(captured) == 1
        assert captured[0].title is None
        assert captured[0].description is None


class TestDefaultBrainPath:
    """The default --brain-path is resolved by walking up to brain.toml, not cwd."""

    def test_default_is_absolute(self):
        """A script-derived default must be absolute so any cwd resolves it."""
        assert _DEFAULT_BRAIN_PATH.is_absolute()

    def test_default_resolves_to_brain_root_when_inside_brain(self):
        """When the orchestrator lives inside the brain repo (the normal case),
        the walk-up resolves the real brain.toml as the default root."""
        root = _find_brain_root(Path(__file__))
        if root is not None:  # standalone clones without the brain skip this
            assert (root / "brain.toml").is_file()
            assert _DEFAULT_BRAIN_PATH == root


# ---------------------------------------------------------------------------
# --prune-paths tests
# ---------------------------------------------------------------------------


class TestPrunePaths:
    """--prune-paths deletes rows for deleted/renamed-away files and exits early.

    db_session is lazily imported inside _prune_paths, so it is patched at its
    source module path. _resolve_brain_path requires a docs/ dir, so each test
    builds a minimal brain layout under tmp_path.
    """

    def _make_mock_session(self) -> tuple[MagicMock, MagicMock]:
        """A chainable MagicMock (session, query) usable as a context manager."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.delete.return_value = 0
        mock_session = MagicMock()
        mock_session.query.return_value = mock_query
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        return mock_session, mock_query

    def test_dry_run_does_not_delete_or_commit(self, tmp_path):
        """--prune-paths with --dry-run reports intent but writes nothing."""
        (tmp_path / "docs").mkdir()
        mock_session, mock_query = self._make_mock_session()

        def fake_db_session():
            yield mock_session

        with (
            patch("database.session.db_session", fake_db_session),
            patch("services.embedding_service.EmbeddingService") as mock_embed_cls,
        ):
            main(
                [
                    "--brain-path",
                    str(tmp_path),
                    "--prune-paths",
                    "docs/gone.md",
                    "--dry-run",
                ]
            )

        mock_query.delete.assert_not_called()
        mock_session.commit.assert_not_called()
        mock_query.count.assert_called()
        # Prune exits before any embedding work.
        mock_embed_cls.assert_not_called()

    def test_real_prune_deletes_and_commits(self, tmp_path):
        """--prune-paths (no dry-run) deletes prunable rows and commits."""
        (tmp_path / "docs").mkdir()
        mock_session, mock_query = self._make_mock_session()

        def fake_db_session():
            yield mock_session

        with (
            patch("database.session.db_session", fake_db_session),
            patch("services.embedding_service.EmbeddingService") as mock_embed_cls,
        ):
            main(["--brain-path", str(tmp_path), "--prune-paths", "docs/gone.md"])

        mock_query.delete.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_embed_cls.assert_not_called()

    def test_absolute_in_brain_path_is_relativised(self, tmp_path, caplog):
        """An absolute path under the brain root is logged as a brain-relative path."""
        import logging

        (tmp_path / "docs").mkdir()
        mock_session, _ = self._make_mock_session()

        def fake_db_session():
            yield mock_session

        abs_path = str(tmp_path / "docs" / "career.md")
        with (
            patch("database.session.db_session", fake_db_session),
            caplog.at_level(logging.INFO, logger="index_brain"),
        ):
            main(["--brain-path", str(tmp_path), "--prune-paths", abs_path])

        # The absolute path collapses to the stored relative form.
        assert "docs/career.md" in caplog.text
        assert abs_path not in caplog.text
