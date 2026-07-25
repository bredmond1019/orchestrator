"""Tests for app/brain/graph.py — the walk read core (OR.N1 task 2).

Seeds `brain_edges` + `brain_documents` against the Docker-gated
`pgvector_engine` fixture (`tests/brain/conftest.py`) and exercises the BFS
traversal: single-hop neighbor resolution, multi-hop expansion, visited-node
dedup (no cycle revisits), and the no-edges-returns-empty-levels contract.
"""

from brain.graph import walk
from database.brain_document import BrainDocument
from database.brain_edge import BrainEdge


def _make_doc(doc_id: str, **overrides) -> BrainDocument:
    defaults = dict(
        file_path=f"docs/decisions/{doc_id}-example.md",
        doc_type="decision",
        content=f"Content for {doc_id}.",
        title=f"{doc_id} — Example Decision",
        section="",
        doc_id=doc_id,
    )
    defaults.update(overrides)
    return BrainDocument(**defaults)


def _make_edge(source_doc_id: str, target_doc_id: str) -> BrainEdge:
    return BrainEdge(
        source_node_id=f"brain:{source_doc_id}",
        source_doc_id=source_doc_id,
        to_ref=target_doc_id,
        target_node_id=f"brain:{target_doc_id}",
        target_doc_id=target_doc_id,
    )


class TestWalkSingleHop:
    """`walk(doc_id, depth=1)` returns the root's resolved related: neighbors."""

    def test_depth_one_returns_direct_neighbors(self, pgvector_session):
        pgvector_session.add_all(
            [
                _make_doc("D36"),
                _make_doc("D41"),
                _make_doc("D24"),
                _make_edge("D36", "D41"),
                _make_edge("D36", "D24"),
            ]
        )
        pgvector_session.flush()

        result = walk("D36", depth=1, session=pgvector_session)

        assert result["root"] == "D36"
        assert result["depth"] == 1
        assert result["levels"] == [["D24", "D41"]]
        assert set(result["nodes"].keys()) == {"D24", "D41"}
        assert result["nodes"]["D41"]["file_path"] == "docs/decisions/D41-example.md"
        assert result["nodes"]["D41"]["title"] == "D41 — Example Decision"


class TestWalkMultiHop:
    """`depth=N` traverses N hops, adding each level's new neighbors."""

    def test_depth_two_adds_second_hop(self, pgvector_session):
        pgvector_session.add_all(
            [
                _make_doc("D36"),
                _make_doc("D41"),
                _make_doc("D50"),
                _make_edge("D36", "D41"),
                _make_edge("D41", "D50"),
            ]
        )
        pgvector_session.flush()

        result = walk("D36", depth=2, session=pgvector_session)

        assert result["levels"] == [["D41"], ["D50"]]
        assert set(result["nodes"].keys()) == {"D41", "D50"}

    def test_depth_exceeding_graph_stops_early(self, pgvector_session):
        pgvector_session.add_all(
            [
                _make_doc("D36"),
                _make_doc("D41"),
                _make_edge("D36", "D41"),
            ]
        )
        pgvector_session.flush()

        result = walk("D36", depth=5, session=pgvector_session)

        # Only one real hop exists; traversal must not error past that.
        assert result["levels"] == [["D41"]]


class TestWalkCycles:
    """Already-visited doc ids are never revisited, even in a cycle."""

    def test_cycle_does_not_revisit_root_or_prior_nodes(self, pgvector_session):
        pgvector_session.add_all(
            [
                _make_doc("D36"),
                _make_doc("D41"),
                _make_edge("D36", "D41"),
                _make_edge("D41", "D36"),  # cycle back to root
            ]
        )
        pgvector_session.flush()

        result = walk("D36", depth=3, session=pgvector_session)

        # Hop 1 -> D41; hop 2 would re-discover D36 (already visited) so it
        # contributes nothing new and traversal stops.
        assert result["levels"] == [["D41"]]


class TestWalkNoEdges:
    """A doc with no edges returns an empty-levels structure, not an error."""

    def test_no_edges_returns_empty_levels(self, pgvector_session):
        pgvector_session.add(_make_doc("D99"))
        pgvector_session.flush()

        result = walk("D99", depth=1, session=pgvector_session)

        assert result["root"] == "D99"
        assert result["levels"] == []
        assert result["nodes"] == {}

    def test_unknown_root_returns_empty_levels(self, pgvector_session):
        result = walk("DOES-NOT-EXIST", depth=1, session=pgvector_session)

        assert result["levels"] == []
        assert result["nodes"] == {}
