"""Unit tests for scripts/load_brain_edges.py.

Tests cover:
- validate_payload: required-key shape checks
- build_node_maps / resolve_ref: bare vs already-scoped to_ref resolution
- build_edge_rows: bare ref resolves to canonical id, already-scoped ref
  passes through, unresolvable ref yields a dangling row, unresolvable
  source is skipped
- load_edges: idempotent — a second load of an unchanged payload produces
  no duplicate rows (mocked session/repository seam, no live DB)
- main(): reads --input file and stdin, delegates to load_edges
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure scripts/ and app/ are importable, mirroring scripts/index_brain.py
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
APP_DIR = Path(__file__).resolve().parent.parent / "app"
for path in (SCRIPTS_DIR, APP_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from load_brain_edges import (  # noqa: E402
    build_edge_rows,
    build_node_maps,
    load_edges,
    main,
    resolve_ref,
    validate_payload,
)

# ---------------------------------------------------------------------------
# Fixture payload — mirrors the mev emit-graph "Output shape" example
# (../mev/docs/cli.md), extended with a dangling-ref edge and a second scope
# for bare-doc_id collision coverage.
# ---------------------------------------------------------------------------


def _payload(**overrides) -> dict:
    base = {
        "version": "1",
        "root": "/path/to/brain",
        "nodes": [
            {"id": "brain:alpha", "scope": "brain", "doc_id": "alpha", "rel": "docs/alpha.md"},
            {"id": "brain:beta", "scope": "brain", "doc_id": "beta", "rel": "docs/beta.md"},
        ],
        "edges": [
            {"from": "brain:alpha", "to_ref": "beta", "kind": "related"},
        ],
        "leaves": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# validate_payload
# ---------------------------------------------------------------------------


def test_validate_payload_accepts_well_formed_payload():
    validate_payload(_payload())  # must not raise


@pytest.mark.parametrize("missing_key", ["version", "nodes", "edges"])
def test_validate_payload_raises_on_missing_key(missing_key):
    payload = _payload()
    del payload[missing_key]
    with pytest.raises(ValueError, match=missing_key):
        validate_payload(payload)


def test_validate_payload_raises_when_nodes_not_a_list():
    payload = _payload(nodes={"id": "brain:alpha"})
    with pytest.raises(ValueError, match="nodes"):
        validate_payload(payload)


def test_validate_payload_raises_when_edges_not_a_list():
    payload = _payload(edges={"from": "brain:alpha"})
    with pytest.raises(ValueError, match="edges"):
        validate_payload(payload)


# ---------------------------------------------------------------------------
# build_node_maps / resolve_ref
# ---------------------------------------------------------------------------


def test_build_node_maps_keys_by_canonical_id_and_bare_doc_id():
    id_map, doc_id_map = build_node_maps(_payload()["nodes"])
    assert id_map["brain:alpha"]["doc_id"] == "alpha"
    assert doc_id_map["beta"]["id"] == "brain:beta"


def test_resolve_ref_bare_matches_by_doc_id():
    id_map, doc_id_map = build_node_maps(_payload()["nodes"])
    resolved = resolve_ref("beta", id_map, doc_id_map)
    assert resolved is not None
    assert resolved["id"] == "brain:beta"


def test_resolve_ref_scoped_matches_by_canonical_id():
    id_map, doc_id_map = build_node_maps(_payload()["nodes"])
    resolved = resolve_ref("brain:beta", id_map, doc_id_map)
    assert resolved is not None
    assert resolved["doc_id"] == "beta"


def test_resolve_ref_unresolvable_returns_none():
    id_map, doc_id_map = build_node_maps(_payload()["nodes"])
    assert resolve_ref("nonexistent", id_map, doc_id_map) is None
    assert resolve_ref("other-scope:nonexistent", id_map, doc_id_map) is None


# ---------------------------------------------------------------------------
# build_edge_rows
# ---------------------------------------------------------------------------


def test_build_edge_rows_bare_ref_resolves_to_canonical_target_id():
    rows = build_edge_rows(_payload())
    assert len(rows) == 1
    row = rows[0]
    assert row["source_node_id"] == "brain:alpha"
    assert row["source_doc_id"] == "alpha"
    assert row["to_ref"] == "beta"
    assert row["target_node_id"] == "brain:beta"
    assert row["target_doc_id"] == "beta"
    assert row["kind"] == "related"
    assert row["scope"] == "brain"


def test_build_edge_rows_already_scoped_ref_passes_through():
    payload = _payload(
        edges=[{"from": "brain:alpha", "to_ref": "brain:beta", "kind": "related"}]
    )
    rows = build_edge_rows(payload)
    assert rows[0]["to_ref"] == "brain:beta"
    assert rows[0]["target_node_id"] == "brain:beta"
    assert rows[0]["target_doc_id"] == "beta"


def test_build_edge_rows_unresolvable_ref_is_dangling_not_dropped():
    payload = _payload(
        edges=[{"from": "brain:alpha", "to_ref": "ghost", "kind": "related"}]
    )
    rows = build_edge_rows(payload)
    assert len(rows) == 1
    row = rows[0]
    assert row["to_ref"] == "ghost"
    assert row["target_node_id"] is None
    assert row["target_doc_id"] is None


def test_build_edge_rows_unresolvable_source_is_skipped():
    payload = _payload(
        edges=[{"from": "brain:nonexistent", "to_ref": "beta", "kind": "related"}]
    )
    rows = build_edge_rows(payload)
    assert rows == []


# ---------------------------------------------------------------------------
# load_edges — mocked session/repository seam, no live DB
# ---------------------------------------------------------------------------


class _FakeQuery:
    """Minimal stand-in for session.query(BrainEdge) supporting .delete()."""

    def __init__(self, store: list):
        self._store = store

    def delete(self, synchronize_session=False):  # noqa: ARG002 - mirrors real signature
        deleted = len(self._store)
        self._store.clear()
        return deleted


class _FakeSession:
    """Minimal stand-in for a SQLAlchemy Session — tracks add()/commit() calls."""

    def __init__(self):
        self.store: list = []
        self.commit_count = 0

    def query(self, _model):
        return _FakeQuery(self.store)

    def add(self, obj):
        self.store.append(obj)

    def commit(self):
        self.commit_count += 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def test_load_edges_loads_resolved_rows_into_session():
    session = _FakeSession()
    count = load_edges(_payload(), session)
    assert count == 1
    assert len(session.store) == 1
    assert session.store[0].source_node_id == "brain:alpha"
    assert session.store[0].target_node_id == "brain:beta"
    assert session.commit_count == 1


def test_load_edges_is_idempotent_second_load_adds_no_new_rows():
    session = _FakeSession()
    payload = _payload()

    first_count = load_edges(payload, session)
    assert len(session.store) == first_count

    second_count = load_edges(payload, session)
    assert second_count == first_count
    assert len(session.store) == first_count  # no duplicates accumulated
    assert session.commit_count == 2


def test_load_edges_raises_on_malformed_payload():
    session = _FakeSession()
    with pytest.raises(ValueError):
        load_edges({"version": "1"}, session)


# ---------------------------------------------------------------------------
# main() — CLI entry point
# ---------------------------------------------------------------------------


def test_main_reads_input_file_and_loads_edges(tmp_path):
    payload_file = tmp_path / "graph.json"
    payload_file.write_text(json.dumps(_payload()), encoding="utf-8")

    fake_session = _FakeSession()

    def _fake_db_session():
        yield fake_session

    with patch("database.session.db_session", side_effect=_fake_db_session):
        main(["--input", str(payload_file)])

    assert len(fake_session.store) == 1
    assert fake_session.store[0].target_node_id == "brain:beta"


def test_main_reads_payload_from_stdin(monkeypatch):
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(json.dumps(_payload())))

    fake_session = _FakeSession()

    def _fake_db_session():
        yield fake_session

    with patch("database.session.db_session", side_effect=_fake_db_session):
        main([])

    assert len(fake_session.store) == 1
