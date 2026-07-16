"""Unit tests for the workspace-mode CLI surface of scripts/index_brain.py.

Tests cover:
- _collect_workspace_files: contract §4 corpus walk conformance over the
  tests/fixtures/okf_workspace/ portability fixture
- empty-corpus fatal error naming the resolved root
- --root-requires---workspace usage error
- resolver-error -> SystemExit mapping (unknown workspace, no registry, malformed
  registry)
- project stamping + root-relative file_path on written rows
- workspace-scoped upsert / --rebuild / --prune-paths deletes (two workspaces
  sharing a relative path coexist)
- brain-mode default unchanged (no-flag invocation still resolves the walk-up
  brain root)
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure scripts/ is importable
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from index_brain import (  # noqa: E402
    _DEFAULT_BRAIN_PATH,
    _classify_doc_type,
    _collect_workspace_files,
    main,
)

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "okf_workspace"


def _write_registry(config_dir: Path, workspaces: dict[str, str], default: str | None = None) -> None:
    """Write a minimal ``[workspaces]`` registry TOML under ``config_dir/orchestrator/config.toml``."""
    orchestrator_dir = config_dir / "orchestrator"
    orchestrator_dir.mkdir(parents=True, exist_ok=True)
    lines = ["[workspaces]"]
    for name, path in workspaces.items():
        lines.append(f'{name} = "{path}"')
    if default is not None:
        lines.append(f'default_workspace = "{default}"')
    (orchestrator_dir / "config.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _make_mock_session() -> tuple[MagicMock, MagicMock]:
    """A chainable MagicMock (session, query) usable as a context manager."""
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.first.return_value = None
    mock_query.count.return_value = 0
    mock_query.delete.return_value = 0
    mock_session = MagicMock()
    mock_session.query.return_value = mock_query
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    return mock_session, mock_query


# ---------------------------------------------------------------------------
# _collect_workspace_files: contract §4 corpus walk conformance
# ---------------------------------------------------------------------------


class TestCollectWorkspaceFiles:
    """Walk conformance over the tests/fixtures/okf_workspace/ fixture."""

    def test_finds_md_and_mdx_files(self):
        files = _collect_workspace_files(FIXTURE_ROOT)
        names = {f.name for f in files}
        assert "with_frontmatter.md" in names
        assert "no_frontmatter.md" in names
        assert "mdx_doc.mdx" in names
        assert "nested_doc.md" in names

    def test_skips_hidden_files_and_dirs(self):
        files = _collect_workspace_files(FIXTURE_ROOT)
        names = {f.name for f in files}
        assert ".dotfile.md" not in names
        assert "inside_hidden.md" not in names

    def test_skips_target_dir(self):
        files = _collect_workspace_files(FIXTURE_ROOT)
        names = {f.name for f in files}
        assert "decoy.md" not in names

    def test_exact_count(self):
        """Exactly the 4 legitimate corpus members are discovered."""
        files = _collect_workspace_files(FIXTURE_ROOT)
        assert len(files) == 4

    def test_finds_nested_subdir_file(self):
        files = _collect_workspace_files(FIXTURE_ROOT)
        rels = {f.relative_to(FIXTURE_ROOT).as_posix() for f in files}
        assert "nested/sub/nested_doc.md" in rels

    def test_empty_dir_returns_empty_list(self, tmp_path):
        empty_dir = tmp_path / "empty_workspace"
        empty_dir.mkdir()
        assert _collect_workspace_files(empty_dir) == []


# ---------------------------------------------------------------------------
# main() usage errors
# ---------------------------------------------------------------------------


class TestUsageErrors:
    """--root without --workspace, and --brain-path combined with workspace flags."""

    def test_root_without_workspace_is_usage_error(self):
        with pytest.raises(SystemExit, match="--root requires --workspace"):
            main(["--root", "/tmp/somewhere"])

    def test_brain_path_with_workspace_is_usage_error(self, tmp_path):
        with pytest.raises(SystemExit, match="brain-mode-only"):
            main(["--brain-path", str(tmp_path), "--workspace", "some-name"])

    def test_brain_path_with_root_is_usage_error(self, tmp_path):
        with pytest.raises(SystemExit, match="brain-mode-only"):
            main(
                [
                    "--brain-path",
                    str(tmp_path),
                    "--workspace",
                    "some-name",
                    "--root",
                    str(tmp_path),
                ]
            )


# ---------------------------------------------------------------------------
# Resolver-error -> SystemExit mapping
# ---------------------------------------------------------------------------


class TestResolverErrorMapping:
    """Typed workspace_resolver errors surface as SystemExit with their message."""

    def test_unknown_workspace_name(self, tmp_path, monkeypatch):
        config_dir = tmp_path / "config"
        _write_registry(config_dir, {"other-workspace": str(tmp_path)})
        monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir))

        with pytest.raises(SystemExit, match="unknown workspace 'missing-workspace'"):
            main(["--workspace", "missing-workspace"])

    def test_no_registry_at_all(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "no-such-config"))

        with pytest.raises(SystemExit, match="no \\[workspaces\\] table"):
            main(["--workspace", "some-workspace"])

    def test_malformed_registry_file(self, tmp_path, monkeypatch):
        config_dir = tmp_path / "config"
        orchestrator_dir = config_dir / "orchestrator"
        orchestrator_dir.mkdir(parents=True)
        (orchestrator_dir / "config.toml").write_text("not valid toml [[[", encoding="utf-8")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir))

        with pytest.raises(SystemExit, match="config file is malformed"):
            main(["--workspace", "some-workspace"])


# ---------------------------------------------------------------------------
# Empty-corpus fatal error
# ---------------------------------------------------------------------------


class TestEmptyCorpus:
    def test_empty_workspace_root_is_fatal(self, tmp_path):
        empty_dir = tmp_path / "empty_workspace"
        empty_dir.mkdir()

        with pytest.raises(SystemExit, match="empty corpus"):
            main(["--workspace", "empty-one", "--root", str(empty_dir)])


# ---------------------------------------------------------------------------
# Dry-run over the fixture: project stamping + root-relative file_path
# ---------------------------------------------------------------------------


class TestWorkspaceDryRun:
    def test_dry_run_lists_root_relative_paths_and_project(self, caplog):
        import logging

        with caplog.at_level(logging.INFO, logger="index_brain"):
            main(
                [
                    "--workspace",
                    "my-workspace",
                    "--root",
                    str(FIXTURE_ROOT),
                    "--dry-run",
                ]
            )

        log_text = caplog.text
        assert "with_frontmatter.md" in log_text
        assert "(project=my-workspace)" in log_text
        assert "Total: 4 files" in log_text

    def test_doc_type_classification_on_root_relative_path(self):
        """Plain OKF corpus files fall back to 'content' via the path classifier."""
        assert _classify_doc_type("with_frontmatter.md") == "content"
        assert _classify_doc_type("nested/sub/nested_doc.md") == "content"


# ---------------------------------------------------------------------------
# Written-row shape: project override + root-relative file_path
# ---------------------------------------------------------------------------


class TestWorkspaceWrittenRows:
    """Mock DB/embedding seams as test_index_brain.py does; drive main() for real."""

    def test_project_stamped_and_file_path_root_relative(self, tmp_path):
        workspace_dir = tmp_path / "wsroot"
        workspace_dir.mkdir()
        (workspace_dir / "doc.md").write_text(
            "---\nproject: some-other-project\n---\n\n## Section\nBody text.",
            encoding="utf-8",
        )

        mock_session, mock_query = _make_mock_session()
        added_docs: list[MagicMock] = []
        mock_session.add.side_effect = added_docs.append

        def fake_db_session():
            yield mock_session

        mock_embed = MagicMock()
        mock_embed.embed_batch.return_value = [[0.1] * 4]

        with (
            patch("database.session.db_session", fake_db_session),
            patch("services.embedding_service.EmbeddingService", return_value=mock_embed),
        ):
            main(["--workspace", "my-ws", "--root", str(workspace_dir)])

        assert len(added_docs) == 1
        doc = added_docs[0]
        # project is stamped with the workspace name verbatim, overriding frontmatter.
        assert doc.project == "my-ws"
        # file_path is relative to the workspace root, not absolute.
        assert doc.file_path == "doc.md"


# ---------------------------------------------------------------------------
# Cross-workspace isolation: --rebuild / --prune-paths are project-scoped
# ---------------------------------------------------------------------------


class TestWorkspaceScopedDestructiveQueries:
    def test_rebuild_scopes_delete_to_project(self, tmp_path):
        workspace_dir = tmp_path / "wsroot"
        workspace_dir.mkdir()
        (workspace_dir / "doc.md").write_text("## Section\nBody.", encoding="utf-8")

        mock_session, mock_query = _make_mock_session()

        def fake_db_session():
            yield mock_session

        mock_embed = MagicMock()
        mock_embed.embed_batch.return_value = [[0.1] * 4]

        with (
            patch("database.session.db_session", fake_db_session),
            patch("services.embedding_service.EmbeddingService", return_value=mock_embed),
        ):
            main(["--workspace", "workspace-a", "--root", str(workspace_dir), "--rebuild"])

        # The --rebuild delete query must have been scoped by project == workspace-a
        # at some point in the filter chain. Compile with literal_binds so the bound
        # parameter value (not just the placeholder) appears in the rendered SQL.
        filter_calls = [call.args for call in mock_query.filter.call_args_list]
        rendered = [
            str(arg.compile(compile_kwargs={"literal_binds": True}))
            for call_args in filter_calls
            for arg in call_args
        ]
        assert any("workspace-a" in sql for sql in rendered)

    def test_prune_paths_scopes_delete_to_project(self, tmp_path):
        workspace_dir = tmp_path / "wsroot"
        workspace_dir.mkdir()

        mock_session, mock_query = _make_mock_session()

        def fake_db_session():
            yield mock_session

        with patch("database.session.db_session", fake_db_session):
            main(
                [
                    "--workspace",
                    "workspace-b",
                    "--root",
                    str(workspace_dir),
                    "--prune-paths",
                    "gone.md",
                ]
            )

        filter_calls = [call.args for call in mock_query.filter.call_args_list]
        rendered = [
            str(arg.compile(compile_kwargs={"literal_binds": True}))
            for call_args in filter_calls
            for arg in call_args
        ]
        assert any("workspace-b" in sql for sql in rendered)


# ---------------------------------------------------------------------------
# Brain-mode default is unchanged
# ---------------------------------------------------------------------------


class TestBrainModeDefaultUnchanged:
    def test_no_flags_resolves_walk_up_brain_root(self, caplog):
        """With neither --workspace nor --root, main() still resolves the real
        brain root via the brain.toml walk-up (identical to pre-task2 behavior)."""
        import logging

        with caplog.at_level(logging.INFO, logger="index_brain"):
            main(["--dry-run"])

        assert (_DEFAULT_BRAIN_PATH / "brain.toml").is_file()
        assert "Dry run" in caplog.text
