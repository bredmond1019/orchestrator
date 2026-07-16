"""Tests for scripts/ingest_repo_log.py — dogfood ingest of log.md into memory.

Block OR.M Task 6. Covers:

- ``parse_log_entries`` handles both log.md heading conventions: a
  ``## [run: DATE]``/``## DATE`` grouping header with nested ``### title``
  entries, and an older ``## DATE (title)`` combined heading with no nested
  entries.
- ``main`` writes one episode per parsed entry via ``EpisodeWriteService``,
  reusing (not duplicating) the ``orchestrator`` peer across runs.
- ``--dry-run`` writes nothing (no DB import, no embedding call).
- ``--limit`` truncates the entries actually ingested.
"""

import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure scripts/ is importable (mirrors tests/scripts/test_index_brain_authored_at.py).
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ingest_repo_log import main, parse_log_entries  # noqa: E402

_SAMPLE_LOG = """\
---
type: Log
title: Development Log
description: Chronological log of work completed.
---

# log — Orchestration Repo

## [run: 2026-07-16]

### First entry title
Some body text for the first entry.
More body.

```
abc1234 feat: something
```

---

### Second entry title
Body of the second entry.

---

## 2026-06-22 (older-style combined heading)
Body text living directly under the combined heading.

---

## 2026-06-20
### Nested under a bare-date grouping header
Body under the bare-date grouping.
"""


class TestParseLogEntries:
    def test_run_marker_groups_nested_h3_entries(self):
        entries = parse_log_entries(_SAMPLE_LOG)
        titled = [e for e in entries if e["title"] == "First entry title"]
        assert len(titled) == 1
        entry = titled[0]
        assert entry["date"] == "2026-07-16"
        assert "Some body text for the first entry." in entry["body"]
        # The trailing code fence + horizontal rule are not stripped from the
        # body content itself (only a trailing bare "---" rule is trimmed).
        assert "abc1234" in entry["body"]

    def test_second_h3_under_same_grouping_header_shares_date(self):
        entries = parse_log_entries(_SAMPLE_LOG)
        entry = next(e for e in entries if e["title"] == "Second entry title")
        assert entry["date"] == "2026-07-16"
        assert "Body of the second entry." in entry["body"]

    def test_combined_h2_date_and_title_is_one_entry(self):
        entries = parse_log_entries(_SAMPLE_LOG)
        entry = next(e for e in entries if e["title"] == "older-style combined heading")
        assert entry["date"] == "2026-06-22"
        assert "Body text living directly under the combined heading." in entry["body"]

    def test_bare_date_grouping_header_is_not_itself_an_entry(self):
        entries = parse_log_entries(_SAMPLE_LOG)
        titles = [e["title"] for e in entries]
        assert "2026-06-20" not in titles

    def test_h3_under_bare_date_header_inherits_date(self):
        entries = parse_log_entries(_SAMPLE_LOG)
        entry = next(e for e in entries if e["title"] == "Nested under a bare-date grouping header")
        assert entry["date"] == "2026-06-20"

    def test_entry_count_matches_expected(self):
        entries = parse_log_entries(_SAMPLE_LOG)
        assert len(entries) == 4

    def test_empty_content_returns_no_entries(self):
        assert parse_log_entries("") == []


@pytest.fixture
def sample_log_file(tmp_path):
    log_path = tmp_path / "log.md"
    log_path.write_text(_SAMPLE_LOG, encoding="utf-8")
    return log_path


class TestMainDryRun:
    def test_dry_run_writes_nothing(self, sample_log_file, caplog):
        # If --dry-run imported the DB/embedding stack it would raise on a
        # test env with no configured provider; asserting no exception plus
        # the logged summary is the behavioural proof nothing was written.
        with caplog.at_level("INFO"):
            main(["--log-path", str(sample_log_file), "--dry-run"])
        assert "Dry run" in caplog.text
        assert "4 entries" in caplog.text

    def test_dry_run_respects_limit(self, sample_log_file, caplog):
        with caplog.at_level("INFO"):
            main(["--log-path", str(sample_log_file), "--dry-run", "--limit", "2"])
        assert "2 entries" in caplog.text


class TestMainIngest:
    @pytest.fixture
    def patched_service(self, monkeypatch):
        """Patch EpisodeWriteService.write so no real DB/embedding is touched.

        ``main()`` imports ``EpisodeWriteService`` lazily inside the function
        body (D32), so the class must be patched where it is defined
        (``memory.episode_write_service``), not on the ``ingest_repo_log``
        module (which never binds a module-level name for it).
        """
        write_mock = MagicMock(return_value=None)
        monkeypatch.setattr(
            "memory.episode_write_service.EpisodeWriteService.write", write_mock
        )
        return write_mock

    def test_ingests_one_episode_per_entry(self, sample_log_file, patched_service):
        main(["--log-path", str(sample_log_file)])
        assert patched_service.call_count == 4
        first_call_kwargs = patched_service.call_args_list[0].kwargs
        assert first_call_kwargs["workspace_id"] == "orchestrator"
        assert first_call_kwargs["peer_id"] == "orchestrator"
        assert "log-entry" in first_call_kwargs["tags"]

    def test_limit_truncates_ingested_entries(self, sample_log_file, patched_service):
        main(["--log-path", str(sample_log_file), "--limit", "1"])
        assert patched_service.call_count == 1

    def test_missing_log_path_raises_system_exit(self, tmp_path):
        with pytest.raises(SystemExit):
            main(["--log-path", str(tmp_path / "does-not-exist.md")])


class TestMainRebuildAndPeerReuse:
    """Integration-shaped test proving one peer is created and reused."""

    def test_peer_created_once_and_reused_across_two_runs(self, sample_log_file, monkeypatch):
        from database.agent_episode import AgentEpisode
        from database.peer import Peer
        from database.session import Base
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine, tables=[Peer.__table__, AgentEpisode.__table__])
        factory = sessionmaker(bind=engine)

        from memory.episode_write_service import EpisodeWriteService

        @contextmanager
        def _session_scope(self):
            session = factory()
            try:
                yield session
            finally:
                session.close()

        monkeypatch.setattr(EpisodeWriteService, "_session_scope", _session_scope)
        monkeypatch.setattr(EpisodeWriteService, "_embed", lambda self, text: [0.01] * 1024)

        main(["--log-path", str(sample_log_file)])
        main(["--log-path", str(sample_log_file)])

        with factory() as session:
            assert session.query(Peer).filter_by(peer_id="orchestrator").count() == 1
            # 4 entries ingested twice = 8 episodes; no dedup on episodes,
            # only the owning peer is a stable, reused row.
            assert session.query(AgentEpisode).filter_by(peer_id="orchestrator").count() == 8
