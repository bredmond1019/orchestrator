"""Tests for app/brain/reconcile.py — the deep corpus/index drift read core.

Seeds `brain_documents` / `content_chunks` / `brain_edges` against the
Docker-gated `pgvector_engine` fixture (`tests/database/conftest.py`) with a
real on-disk corpus root (`tmp_path`) so `deep_stale()`'s file-existence and
section-diff axes exercise real `Path`/`chunk_by_section` behavior, not
mocks. One test per axis seeds exactly the drift the ticket's acceptance
criteria name and asserts the exact rows reported; a healthy-corpus test
asserts `drift is False` across all five axes.
"""

import uuid
from datetime import datetime

from brain.reconcile import ReconcileReport, deep_stale
from database.brain_document import BrainDocument
from database.brain_edge import BrainEdge
from database.content_chunk import ContentChunk

_STAMP = "ollama:mxbai-embed-large"


class _FakeEmbeddingService:
    """Stub embedding service — fixed stamp, never calls a real backend."""

    stamp = _STAMP


def _make_doc(file_path: str, **overrides) -> BrainDocument:
    defaults = dict(
        file_path=file_path,
        doc_type="decision",
        section="",
        content="content",
        embedding_model=_STAMP,
        indexed_at=datetime(2026, 1, 1),
        authored_at=datetime(2026, 1, 1),
    )
    defaults.update(overrides)
    return BrainDocument(**defaults)


def _make_edge(source_doc_id: str, to_ref: str, **overrides) -> BrainEdge:
    defaults = dict(
        source_node_id=f"brain:{source_doc_id}",
        source_doc_id=source_doc_id,
        to_ref=to_ref,
        target_node_id=f"brain:{to_ref}" if to_ref else None,
        target_doc_id=to_ref,
    )
    defaults.update(overrides)
    return BrainEdge(**defaults)


def _make_chunk(doc_id, position: int, **overrides) -> ContentChunk:
    defaults = dict(
        doc_id=doc_id,
        position=position,
        content=f"chunk {position}",
        embedding_model=_STAMP,
    )
    defaults.update(overrides)
    return ContentChunk(**defaults)


class TestDeletedButEmbedded:
    """Axis 1: an indexed file_path whose file no longer exists on disk."""

    def test_names_the_missing_file(self, pgvector_session, tmp_path):
        (tmp_path / "still-here.md").write_text("## A\n\nbody\n", encoding="utf-8")
        pgvector_session.add_all(
            [
                _make_doc("still-here.md", doc_id="D1", section="## A"),
                _make_doc("gone.md", doc_id="D2"),
            ]
        )
        pgvector_session.flush()

        report = deep_stale(
            brain_path=str(tmp_path),
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )

        assert report.deleted_but_embedded == ["gone.md"]
        assert report.drift is True

    def test_ingested_and_client_slug_rows_are_exempt(self, pgvector_session, tmp_path):
        pgvector_session.add_all(
            [
                _make_doc("ingested/proposal/abc.md", doc_id="D1"),
                _make_doc("diagnostics/acme.md", doc_id="D2", client_slug="acme-2026"),
            ]
        )
        pgvector_session.flush()

        report = deep_stale(
            brain_path=str(tmp_path),
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )

        assert report.deleted_but_embedded == []


class TestSectionOrphans:
    """Axis 2: a DB (file_path, section) pair absent from the file's current sections."""

    def test_names_the_orphaned_section_pair(self, pgvector_session, tmp_path):
        (tmp_path / "doc.md").write_text(
            "## Current\n\nstill here\n", encoding="utf-8"
        )
        pgvector_session.add_all(
            [
                _make_doc("doc.md", doc_id="D1", section="## Current"),
                _make_doc("doc.md", doc_id="D1", section="## Renamed-Away"),
            ]
        )
        pgvector_session.flush()

        report = deep_stale(
            brain_path=str(tmp_path),
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )

        assert report.section_orphans == [("doc.md", "## Renamed-Away")]
        assert report.drift is True

    def test_no_orphan_when_sections_match(self, pgvector_session, tmp_path):
        (tmp_path / "doc.md").write_text(
            "## Current\n\nstill here\n", encoding="utf-8"
        )
        pgvector_session.add(_make_doc("doc.md", doc_id="D1", section="## Current"))
        pgvector_session.flush()

        report = deep_stale(
            brain_path=str(tmp_path),
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )

        assert report.section_orphans == []

    def test_deleted_file_is_not_double_reported(self, pgvector_session, tmp_path):
        pgvector_session.add(_make_doc("gone.md", doc_id="D1", section="## X"))
        pgvector_session.flush()

        report = deep_stale(
            brain_path=str(tmp_path),
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )

        assert report.deleted_but_embedded == ["gone.md"]
        assert report.section_orphans == []


class TestOrphanedChunks:
    """Axis 3: a content_chunks doc_id group with no position==0 anchor row."""

    def test_names_every_chunk_in_a_rootless_group(self, pgvector_session):
        rootless_doc_id = uuid.uuid4()
        rooted_doc_id = uuid.uuid4()

        orphan_1 = _make_chunk(rootless_doc_id, position=1)
        orphan_2 = _make_chunk(rootless_doc_id, position=2)
        healthy_root = _make_chunk(rooted_doc_id, position=0)
        healthy_tail = _make_chunk(rooted_doc_id, position=1)

        pgvector_session.add_all([orphan_1, orphan_2, healthy_root, healthy_tail])
        pgvector_session.flush()

        report = deep_stale(
            brain_path="/nonexistent-brain-root",
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )

        assert sorted(report.orphaned_chunks) == sorted(
            [str(orphan_1.id), str(orphan_2.id)]
        )
        assert report.drift is True

    def test_rooted_group_is_not_orphaned(self, pgvector_session):
        doc_id = uuid.uuid4()
        pgvector_session.add_all(
            [_make_chunk(doc_id, position=0), _make_chunk(doc_id, position=1)]
        )
        pgvector_session.flush()

        report = deep_stale(
            brain_path="/nonexistent-brain-root",
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )

        assert report.orphaned_chunks == []


class TestDanglingEdges:
    """Axis 4: NULL-target edges, plus non-null targets resolving to no document."""

    def test_names_null_target_and_unresolved_target_edges(self, pgvector_session):
        pgvector_session.add_all(
            [
                _make_doc("ingested/proposal/d1.md", doc_id="D1"),
                # An authored `related:` ref mev could not resolve at all —
                # the loader keeps it with NULL target columns rather than
                # dropping it (`to_ref` itself is still NOT NULL).
                _make_edge("D1", "unresolvable-ref", target_node_id=None, target_doc_id=None),
                _make_edge("D1", "D-does-not-exist"),
                _make_edge("D1", "D1"),
            ]
        )
        pgvector_session.flush()

        report = deep_stale(
            brain_path="/nonexistent-brain-root",
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )

        to_refs = {edge["to_ref"] for edge in report.dangling_edges}
        assert to_refs == {"unresolvable-ref", "D-does-not-exist"}
        assert report.drift is True

    def test_resolved_edge_is_not_dangling(self, pgvector_session):
        pgvector_session.add_all(
            [
                _make_doc("ingested/proposal/d1.md", doc_id="D1"),
                _make_doc("ingested/proposal/d2.md", doc_id="D2"),
                _make_edge("D1", "D2"),
            ]
        )
        pgvector_session.flush()

        report = deep_stale(
            brain_path="/nonexistent-brain-root",
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )

        assert report.dangling_edges == []


class TestModelMismatch:
    """Axis 5: a row whose embedding_model stamp differs from the configured service."""

    def test_flags_mismatched_stamp(self, pgvector_session):
        pgvector_session.add(
            _make_doc(
                "ingested/proposal/d1.md", doc_id="D1", embedding_model="voyage:voyage-2"
            )
        )
        pgvector_session.flush()

        report = deep_stale(
            brain_path="/nonexistent-brain-root",
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )

        assert len(report.model_mismatch) == 1
        assert report.model_mismatch[0]["embedding_model"] == "voyage:voyage-2"
        assert report.model_mismatch[0]["file_path"] == "ingested/proposal/d1.md"
        assert report.drift is True

    def test_null_stamp_is_unstamped_not_drift(self, pgvector_session):
        pgvector_session.add(
            _make_doc("ingested/proposal/d1.md", doc_id="D1", embedding_model=None)
        )
        pgvector_session.flush()

        report = deep_stale(
            brain_path="/nonexistent-brain-root",
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )

        assert report.model_mismatch == []
        assert report.unstamped_count == 1
        assert report.drift is False

    def test_matching_stamp_is_not_flagged(self, pgvector_session):
        pgvector_session.add(
            _make_doc("ingested/proposal/d1.md", doc_id="D1", embedding_model=_STAMP)
        )
        pgvector_session.flush()

        report = deep_stale(
            brain_path="/nonexistent-brain-root",
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )

        assert report.model_mismatch == []
        assert report.unstamped_count == 0


class TestIngestedLane:
    """Axis 6 (informational): count + authored_at age range of ingested/% rows."""

    def test_reports_count_and_age_range(self, pgvector_session):
        pgvector_session.add_all(
            [
                _make_doc(
                    "ingested/proposal/a.md",
                    doc_id=None,
                    authored_at=datetime(2026, 1, 1),
                ),
                _make_doc(
                    "ingested/proposal/b.md",
                    doc_id=None,
                    authored_at=datetime(2026, 6, 1),
                ),
            ]
        )
        pgvector_session.flush()

        report = deep_stale(
            brain_path="/nonexistent-brain-root",
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )

        assert report.ingested_count == 2
        assert report.ingested_min_authored_at == datetime(2026, 1, 1)
        assert report.ingested_max_authored_at == datetime(2026, 6, 1)
        # The ingested lane is informational — it never contributes to drift.
        assert report.drift is False

    def test_empty_lane_reports_zero_and_no_age(self, pgvector_session):
        pgvector_session.add(_make_doc("d1.md", doc_id="D1"))
        pgvector_session.flush()

        report = deep_stale(
            brain_path="/nonexistent-brain-root",
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )

        assert report.ingested_count == 0
        assert report.ingested_min_authored_at is None
        assert report.ingested_max_authored_at is None


class TestHealthyCorpus:
    """A fully-consistent corpus reports zero drift on all five axes."""

    def test_reports_no_drift(self, pgvector_session, tmp_path):
        (tmp_path / "doc.md").write_text("## Current\n\nbody\n", encoding="utf-8")
        doc_id_uuid = uuid.uuid4()
        pgvector_session.add_all(
            [
                _make_doc("doc.md", doc_id="D1", section="## Current"),
                _make_doc("ingested/proposal/d2.md", doc_id="D2"),
                _make_edge("D1", "D2"),
                _make_chunk(doc_id_uuid, position=0),
                _make_chunk(doc_id_uuid, position=1),
            ]
        )
        pgvector_session.flush()

        report = deep_stale(
            brain_path=str(tmp_path),
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )

        assert isinstance(report, ReconcileReport)
        assert report.deleted_but_embedded == []
        assert report.section_orphans == []
        assert report.orphaned_chunks == []
        assert report.dangling_edges == []
        assert report.model_mismatch == []
        assert report.drift is False


def _write_brain_toml(root, skip_dirs=()):
    skip_list = ", ".join(f'"{d}"' for d in skip_dirs)
    (root / "brain.toml").write_text(
        "[vocab]\n"
        'layer = ["brain"]\n'
        'status = ["active"]\n'
        "[crawl]\n"
        f"skip_dirs = [{skip_list}]\n",
        encoding="utf-8",
    )


class TestIngestCeiling:
    """Axis 7 (informational): the filesystem -> DB gap none of the other axes see."""

    def test_uncovered_file_has_no_db_rows(self, pgvector_session, tmp_path):
        _write_brain_toml(tmp_path)
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "never-indexed.md").write_text(
            "## A\n\nbody\n", encoding="utf-8"
        )
        pgvector_session.flush()

        report = deep_stale(
            brain_path=str(tmp_path),
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )

        assert "docs/never-indexed.md" in report.uncovered_files
        # Axis 7 is informational — it never contributes to drift.
        assert report.drift is False

    def test_malformed_frontmatter_is_unparseable_not_raising(
        self, pgvector_session, tmp_path
    ):
        _write_brain_toml(tmp_path)
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "broken.md").write_text(
            "---\nlayer: [brain\n---\nbody\n", encoding="utf-8"
        )
        pgvector_session.flush()

        # Must not raise — this is the fix for the bare parse_document call
        # in _section_orphans that used to make deep_stale itself blow up.
        report = deep_stale(
            brain_path=str(tmp_path),
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )

        assert "docs/broken.md" in report.unparseable_files
        assert "docs/broken.md" not in report.uncovered_files
        assert report.drift is False

    def test_excluded_count_breaks_down_by_reason(self, pgvector_session, tmp_path):
        _write_brain_toml(tmp_path, skip_dirs=["archive"])
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "_draft.md").write_text("body\n", encoding="utf-8")
        (tmp_path / "docs" / "handoff.md").write_text("body\n", encoding="utf-8")
        archive_dir = tmp_path / "docs" / "archive"
        archive_dir.mkdir()
        (archive_dir / "old.md").write_text("body\n", encoding="utf-8")
        pgvector_session.flush()

        report = deep_stale(
            brain_path=str(tmp_path),
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )

        assert report.excluded_count["leading_underscore"] == 1
        assert report.excluded_count["ephemeral_filename"] == 1
        assert report.excluded_count["skip_dir"] == 1

    def test_enumeration_is_imported_from_index_brain_not_reimplemented(
        self, pgvector_session, tmp_path, monkeypatch
    ):
        _write_brain_toml(tmp_path)
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "real.md").write_text("body\n", encoding="utf-8")

        import index_brain

        fake_file = tmp_path / "docs" / "fake-from-monkeypatch.md"
        fake_file.write_text("body\n", encoding="utf-8")

        def _fake_collect_files(brain_path, config, errors=None, parse_failed_paths=None):
            return [(fake_file, "content", None)]

        monkeypatch.setattr(index_brain, "_collect_files", _fake_collect_files)
        pgvector_session.flush()

        report = deep_stale(
            brain_path=str(tmp_path),
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )

        # Only the monkeypatched file is reflected — proves the axis calls
        # through index_brain._collect_files rather than walking the
        # filesystem itself.
        assert report.uncovered_files == ["docs/fake-from-monkeypatch.md"]
        assert "docs/real.md" not in report.uncovered_files

    def test_no_brain_toml_degrades_to_empty_axis(self, pgvector_session, tmp_path):
        # No brain.toml written — every other axis test in this file relies
        # on this not raising.
        (tmp_path / "doc.md").write_text("## A\n\nbody\n", encoding="utf-8")
        pgvector_session.flush()

        report = deep_stale(
            brain_path=str(tmp_path),
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )

        assert report.uncovered_files == []
        assert report.unparseable_files == []
        assert report.excluded_count == {}

    def test_healthy_corpus_drift_axes_unaffected_by_axis7(self, pgvector_session, tmp_path):
        """Existing drift semantics (bool of axes 1-5) are unchanged by axis 7."""
        _write_brain_toml(tmp_path)
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "doc.md").write_text("## Current\n\nbody\n", encoding="utf-8")
        pgvector_session.add(_make_doc("docs/doc.md", doc_id="D1", section="## Current"))
        pgvector_session.flush()

        report = deep_stale(
            brain_path=str(tmp_path),
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )

        assert report.drift is False
        assert report.deleted_but_embedded == []
        assert report.section_orphans == []


class TestReconcileReportSerialization:
    """`to_dict()` produces a JSON-serializable payload."""

    def test_to_dict_serializes_datetimes_and_tuples(self, pgvector_session, tmp_path):
        pgvector_session.add(
            _make_doc(
                "ingested/proposal/a.md",
                doc_id=None,
                authored_at=datetime(2026, 1, 1),
            )
        )
        pgvector_session.flush()

        report = deep_stale(
            brain_path=str(tmp_path),
            session=pgvector_session,
            embedding_service=_FakeEmbeddingService(),
        )
        payload = report.to_dict()

        assert isinstance(payload["ingested_min_authored_at"], str)
        assert isinstance(payload["ingested_max_authored_at"], str)
        assert isinstance(payload["section_orphans"], list)
