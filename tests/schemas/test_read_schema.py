"""Tests for app/schemas/read_schema.py (OR.Q2 task 1).

Covers:
- RecallResponse validates from a real `_normalize_doc_row`-shaped dict
- WalkResponse validates from `walk()`'s documented return shape, including
  the empty-edges case (`levels: []`, `nodes: {}`)
- PulseResponse validates from a real `PulseReport(...).to_dict()`, with
  both None and ISO-string timestamps
"""

from datetime import UTC, datetime

from brain.pulse import PulseReport
from schemas.read_schema import (
    PulseResponse,
    RecallResponse,
    RecallResult,
    WalkNode,
    WalkResponse,
)

# ---------------------------------------------------------------------------
# RecallResponse / RecallResult
# ---------------------------------------------------------------------------


def _normalize_doc_row_shape(doc_id="D20", distance=0.0, via="exact-id") -> dict:
    """Mirror app/brain/retrieval.py::_normalize_doc_row's exact return shape."""
    return {
        "doc_id": doc_id,
        "file_path": "docs/decisions/D20-shared-data-contract.md",
        "title": "D20 — Shared data contract",
        "section": None,
        "content": "Some chunk content.",
        "score": distance,
        "via": via,
    }


class TestRecallResult:
    def test_validates_from_normalized_doc_row(self):
        row = _normalize_doc_row_shape()
        result = RecallResult(**row)
        assert result.doc_id == "D20"
        assert result.file_path == row["file_path"]
        assert result.score == 0.0
        assert result.via == "exact-id"

    def test_none_doc_id_and_section_allowed(self):
        row = _normalize_doc_row_shape(doc_id=None)
        row["section"] = None
        result = RecallResult(**row)
        assert result.doc_id is None
        assert result.section is None


class TestRecallResponse:
    def test_validates_from_core_results_list(self):
        rows = [
            _normalize_doc_row_shape(doc_id="D20", distance=0.0, via="exact-id"),
            _normalize_doc_row_shape(doc_id="D21", distance=0.12, via="semantic"),
        ]
        response = RecallResponse(query="what is D20", count=len(rows), results=rows)
        assert response.query == "what is D20"
        assert response.count == 2
        assert len(response.results) == 2
        assert response.results[1].via == "semantic"

    def test_empty_results(self):
        response = RecallResponse(query="nothing matches", count=0, results=[])
        assert response.count == 0
        assert response.results == []


# ---------------------------------------------------------------------------
# WalkResponse / WalkNode
# ---------------------------------------------------------------------------


class TestWalkNode:
    def test_validates_from_walk_node_shape(self):
        node = WalkNode(doc_id="D21", file_path="docs/decisions/D21.md", title="D21 title")
        assert node.doc_id == "D21"

    def test_none_file_path_and_title_allowed(self):
        node = WalkNode(doc_id="D21", file_path=None, title=None)
        assert node.file_path is None
        assert node.title is None


class TestWalkResponse:
    def test_validates_from_walk_documented_return_shape(self):
        payload = {
            "root": "D20",
            "depth": 2,
            "levels": [["D21", "D22"], ["D23"]],
            "nodes": {
                "D21": {"doc_id": "D21", "file_path": "docs/D21.md", "title": "D21"},
                "D22": {"doc_id": "D22", "file_path": "docs/D22.md", "title": "D22"},
                "D23": {"doc_id": "D23", "file_path": None, "title": None},
            },
        }
        response = WalkResponse(**payload)
        assert response.root == "D20"
        assert response.depth == 2
        assert response.levels == [["D21", "D22"], ["D23"]]
        assert response.nodes["D23"].file_path is None

    def test_no_edges_returns_empty_levels_and_nodes(self):
        payload = {"root": "D99", "depth": 1, "levels": [], "nodes": {}}
        response = WalkResponse(**payload)
        assert response.levels == []
        assert response.nodes == {}


# ---------------------------------------------------------------------------
# PulseResponse
# ---------------------------------------------------------------------------


class TestPulseResponse:
    def test_validates_from_real_pulse_report_to_dict_with_none_timestamps(self):
        report = PulseReport(
            pgvector_reachable=True,
            embedding_reachable=True,
            embedding_error=None,
            brain_documents_count=1234,
            brain_edges_count=456,
            max_indexed_at=None,
            max_authored_at=None,
            edges_empty_but_related_exists=False,
            healthy=True,
            errors=[],
        )
        response = PulseResponse(**report.to_dict())
        assert response.healthy is True
        assert response.max_indexed_at is None
        assert response.max_authored_at is None
        assert response.errors == []

    def test_validates_from_real_pulse_report_to_dict_with_iso_timestamps(self):
        now = datetime(2026, 7, 27, 12, 0, 0, tzinfo=UTC)
        report = PulseReport(
            pgvector_reachable=False,
            embedding_reachable=False,
            embedding_error="embedding backend unreachable: connection refused",
            brain_documents_count=0,
            brain_edges_count=0,
            max_indexed_at=now,
            max_authored_at=now,
            edges_empty_but_related_exists=True,
            healthy=False,
            errors=["pgvector unreachable: connection refused"],
        )
        payload = report.to_dict()
        response = PulseResponse(**payload)
        assert response.healthy is False
        assert response.max_indexed_at == now.isoformat()
        assert response.max_authored_at == now.isoformat()
        assert response.embedding_error == "embedding backend unreachable: connection refused"
        assert response.edges_empty_but_related_exists is True
        assert response.errors == ["pgvector unreachable: connection refused"]
