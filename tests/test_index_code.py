"""Unit tests for scripts/index_code.py.

Covers OR.P task 5: file discovery (`_eligible_files` — extension filter,
size ceiling, skip-dir pruning), the per-repo indexer (`_index_repo` —
incremental skip, re-embed on touch, deleted-file pruning), and the CLI's
repo-selection wiring (`main`/`_select_repos`).

No live database and no live embedding backend: `database.session.db_session`
is replaced with a scripted `MagicMock` session (mirroring `tests/test_index_brain.py`'s
pattern), and the embedding service is a stub whose `embed_batch` returns one
fixed-width vector per input text.

Fixture source files are the same ones `tests/brain/test_code_chunking.py` pins
(`tests/brain/fixtures/code/sample.py` / `sample.rs`) — copied into a tmp
directory that stands in for a repo's working tree, so a chunk-boundary
change to those fixtures cannot silently desync the two test files (both
read the fixtures fresh via `chunk_source`, never a hardcoded chunk count).
"""

import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure scripts/ and app/ are importable, matching index_code.py's own setup.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import index_code  # noqa: E402
from brain.code_chunking import chunk_source  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "brain" / "fixtures" / "code"


def _make_repo(tmp_path: Path, *files: str) -> Path:
    """Copy the named fixtures (from tests/brain/fixtures/code/) into a fresh repo dir."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    for name in files:
        shutil.copy(FIXTURES / name, repo_root / name)
    return repo_root


def _expected_chunk_count(*files: str) -> int:
    total = 0
    for name in files:
        text = (FIXTURES / name).read_text(encoding="utf-8")
        total += len(chunk_source(text, file_path=name))
    return total


def _make_session() -> MagicMock:
    """A MagicMock Session covering both query shapes _index_repo issues.

    `query(CodeChunk).filter(...).order_by(...).first()` — the per-file
    incremental skip-check (its return value is driven per-test via
    `.first.side_effect`, one entry per file in `_eligible_files`'s sorted
    order). `query(CodeChunk.file_path).filter(...).distinct().all()` — the
    end-of-run prune read.
    """
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    filtered = session.query.return_value.filter.return_value
    filtered.order_by.return_value.first.return_value = None
    filtered.distinct.return_value.all.return_value = []
    filtered.delete.return_value = 0
    return session


def _fake_db_session_factory(session: MagicMock):
    def fake_db_session():
        yield session

    return fake_db_session


def _fake_embedding_service(dim: int = 1024) -> MagicMock:
    svc = MagicMock()
    svc.stamp = "ollama:mxbai-embed-large"
    svc.embed_batch.side_effect = lambda texts: [[0.1] * dim for _ in texts]
    return svc


# ---------------------------------------------------------------------------
# _eligible_files
# ---------------------------------------------------------------------------


class TestEligibleFiles:
    def test_filters_by_extension_and_finds_source_files(self, tmp_path):
        repo_root = _make_repo(tmp_path, "sample.py", "sample.rs", "sample.txt")
        found = {p.name for p in index_code._eligible_files(repo_root)}
        assert found == {"sample.py", "sample.rs"}
        assert "sample.txt" not in found  # not a recognised source extension

    def test_skips_vendored_directories(self, tmp_path):
        repo_root = _make_repo(tmp_path, "sample.py")
        vendored = repo_root / "node_modules" / "pkg"
        vendored.mkdir(parents=True)
        (vendored / "index.js").write_text("module.exports = {};\n", encoding="utf-8")
        found = {p.name for p in index_code._eligible_files(repo_root)}
        assert found == {"sample.py"}

    def test_skips_files_over_the_size_ceiling(self, tmp_path):
        repo_root = _make_repo(tmp_path, "sample.py")
        huge = repo_root / "huge.py"
        huge.write_text("x = 1\n" * (index_code._MAX_FILE_BYTES // 4), encoding="utf-8")
        assert huge.stat().st_size > index_code._MAX_FILE_BYTES
        found = {p.name for p in index_code._eligible_files(repo_root)}
        assert "huge.py" not in found
        assert "sample.py" in found


# ---------------------------------------------------------------------------
# _index_repo
# ---------------------------------------------------------------------------


class TestIndexRepoFirstRun:
    def test_first_run_embeds_every_file_and_writes_a_row_per_chunk(self, tmp_path):
        repo_root = _make_repo(tmp_path, "sample.py", "sample.rs")
        expected_chunks = _expected_chunk_count("sample.py", "sample.rs")

        session = _make_session()  # first() -> None: nothing pre-existing, nothing skipped
        embed_svc = _fake_embedding_service()

        with patch("index_code.db_session", _fake_db_session_factory(session)):
            stats = index_code._index_repo(
                "orchestrator", repo_root, embed_svc, rebuild=False, dry_run=False
            )

        assert stats["files"] == 2
        assert stats["chunks"] == expected_chunks
        assert stats["embeddings"] == expected_chunks
        assert stats["skipped"] == 0
        assert session.add.call_count == expected_chunks
        assert embed_svc.embed_batch.call_count == 2  # once per file

    def test_dry_run_reports_counts_without_embedding_or_writing(self, tmp_path):
        repo_root = _make_repo(tmp_path, "sample.py", "sample.rs")
        expected_chunks = _expected_chunk_count("sample.py", "sample.rs")

        session = _make_session()
        embed_svc = _fake_embedding_service()

        with patch("index_code.db_session", _fake_db_session_factory(session)):
            stats = index_code._index_repo(
                "orchestrator", repo_root, embed_svc, rebuild=False, dry_run=True
            )

        assert stats["files"] == 2
        assert stats["chunks"] == expected_chunks
        assert stats["embeddings"] == 0
        embed_svc.embed_batch.assert_not_called()
        session.add.assert_not_called()


class TestIndexRepoIncremental:
    def test_second_run_unchanged_skips_every_file(self, tmp_path):
        repo_root = _make_repo(tmp_path, "sample.py", "sample.rs")

        far_future = datetime.now() + timedelta(days=365)
        session = _make_session()
        existing_row = MagicMock(indexed_at=far_future)
        session.query.return_value.filter.return_value.order_by.return_value.first.side_effect = [
            existing_row,
            existing_row,
        ]
        embed_svc = _fake_embedding_service()

        with patch("index_code.db_session", _fake_db_session_factory(session)):
            stats = index_code._index_repo(
                "orchestrator", repo_root, embed_svc, rebuild=False, dry_run=False
            )

        assert stats["files"] == 0
        assert stats["skipped"] == 2
        embed_svc.embed_batch.assert_not_called()
        session.add.assert_not_called()

    def test_touching_one_file_reembeds_only_that_file(self, tmp_path):
        repo_root = _make_repo(tmp_path, "sample.py", "sample.rs")
        expected_py_chunks = _expected_chunk_count("sample.py")

        far_future = datetime.now() + timedelta(days=365)
        far_past = datetime.now() - timedelta(days=365)
        session = _make_session()
        # _eligible_files sorts by path: "sample.py" precedes "sample.rs", so the
        # skip-check calls arrive in that order.
        session.query.return_value.filter.return_value.order_by.return_value.first.side_effect = [
            MagicMock(indexed_at=far_past),  # sample.py: stale row -> re-embed
            MagicMock(indexed_at=far_future),  # sample.rs: fresh row -> skip
        ]
        embed_svc = _fake_embedding_service()

        with patch("index_code.db_session", _fake_db_session_factory(session)):
            stats = index_code._index_repo(
                "orchestrator", repo_root, embed_svc, rebuild=False, dry_run=False
            )

        assert stats["files"] == 1
        assert stats["skipped"] == 1
        assert stats["chunks"] == expected_py_chunks
        embed_svc.embed_batch.assert_called_once()
        (embedded_texts,), _kwargs = embed_svc.embed_batch.call_args
        assert len(embedded_texts) == expected_py_chunks

    def test_rebuild_bypasses_the_skip_check(self, tmp_path):
        repo_root = _make_repo(tmp_path, "sample.py")
        expected_chunks = _expected_chunk_count("sample.py")

        far_future = datetime.now() + timedelta(days=365)
        session = _make_session()
        session.query.return_value.filter.return_value.order_by.return_value.first.return_value = MagicMock(
            indexed_at=far_future
        )
        embed_svc = _fake_embedding_service()

        with patch("index_code.db_session", _fake_db_session_factory(session)):
            stats = index_code._index_repo(
                "orchestrator", repo_root, embed_svc, rebuild=True, dry_run=False
            )

        assert stats["files"] == 1
        assert stats["skipped"] == 0
        assert stats["chunks"] == expected_chunks
        embed_svc.embed_batch.assert_called_once()


class TestIndexRepoPruning:
    def test_deleted_file_rows_are_pruned(self, tmp_path):
        repo_root = _make_repo(tmp_path, "sample.py")

        session = _make_session()
        # The DB still holds rows for "gone.py", which no longer exists on disk.
        session.query.return_value.filter.return_value.distinct.return_value.all.return_value = [
            ("sample.py",),
            ("gone.py",),
        ]
        embed_svc = _fake_embedding_service()

        with patch("index_code.db_session", _fake_db_session_factory(session)):
            stats = index_code._index_repo(
                "orchestrator", repo_root, embed_svc, rebuild=False, dry_run=False
            )

        assert stats["pruned_files"] == 1

    def test_dry_run_never_prunes(self, tmp_path):
        repo_root = _make_repo(tmp_path, "sample.py")

        session = _make_session()
        session.query.return_value.filter.return_value.distinct.return_value.all.return_value = [
            ("sample.py",),
            ("gone.py",),
        ]
        embed_svc = _fake_embedding_service()

        with patch("index_code.db_session", _fake_db_session_factory(session)):
            stats = index_code._index_repo(
                "orchestrator", repo_root, embed_svc, rebuild=False, dry_run=True
            )

        assert stats["pruned_files"] == 0


# ---------------------------------------------------------------------------
# CLI wiring: _select_repos / main
# ---------------------------------------------------------------------------


class TestSelectRepos:
    def test_selects_named_repo_only(self):
        config = index_code.BrainConfig(
            valid_layers=frozenset(),
            valid_projects=frozenset(),
            valid_statuses=frozenset(),
            skip_dirs=(),
            repos=(
                {"slug": "orchestrator", "repo_path": "core/orchestrator"},
                {"slug": "engine-rs", "repo_path": "core/engine-rs"},
            ),
        )
        selected = index_code._select_repos(config, "engine-rs")
        assert [r["slug"] for r in selected] == ["engine-rs"]

    def test_defaults_to_every_repo_with_a_repo_path(self):
        config = index_code.BrainConfig(
            valid_layers=frozenset(),
            valid_projects=frozenset(),
            valid_statuses=frozenset(),
            skip_dirs=(),
            repos=(
                {"slug": "orchestrator", "repo_path": "core/orchestrator"},
                {"slug": "brain", "repo_path": None},
                {"slug": "engine-rs", "repo_path": "core/engine-rs"},
            ),
        )
        selected = index_code._select_repos(config, None)
        assert {r["slug"] for r in selected} == {"orchestrator", "engine-rs"}

    def test_unknown_slug_raises_system_exit(self):
        config = index_code.BrainConfig(
            valid_layers=frozenset(),
            valid_projects=frozenset(),
            valid_statuses=frozenset(),
            skip_dirs=(),
            repos=({"slug": "orchestrator", "repo_path": "core/orchestrator"},),
        )
        with pytest.raises(SystemExit):
            index_code._select_repos(config, "no-such-repo")


class TestMain:
    def test_dry_run_skips_embedding_service_construction_and_respects_repo_filter(
        self, tmp_path
    ):
        brain_path = tmp_path
        (brain_path / "core" / "orchestrator").mkdir(parents=True)
        (brain_path / "core" / "other").mkdir(parents=True)

        config = index_code.BrainConfig(
            valid_layers=frozenset(),
            valid_projects=frozenset(),
            valid_statuses=frozenset(),
            skip_dirs=(),
            repos=(
                {"slug": "orchestrator", "repo_path": "core/orchestrator"},
                {"slug": "other", "repo_path": "core/other"},
            ),
        )

        with (
            patch("index_code._find_brain_root", return_value=brain_path),
            patch("index_code._load_brain_config", return_value=config),
            patch(
                "index_code._index_repo",
                return_value={
                    "files": 0,
                    "chunks": 0,
                    "embeddings": 0,
                    "skipped": 0,
                    "pruned_files": 0,
                },
            ) as mock_index_repo,
        ):
            exit_code = index_code.main(["--repo", "orchestrator", "--dry-run"])

        assert exit_code == 0
        mock_index_repo.assert_called_once()
        call_args, call_kwargs = mock_index_repo.call_args
        assert call_args[0] == "orchestrator"
        assert call_args[1] == (brain_path / "core" / "orchestrator").resolve()
        assert call_kwargs["dry_run"] is True
        assert call_kwargs["rebuild"] is False
        # dry-run: main() must never instantiate EmbeddingService (no server needed).
        assert call_args[2] is None

    def test_missing_brain_root_raises_system_exit(self):
        with patch("index_code._find_brain_root", return_value=None):
            with pytest.raises(SystemExit):
                index_code.main(["--dry-run"])
