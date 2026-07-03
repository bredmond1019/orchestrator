"""End-to-end acceptance test for OR.G — neighbor retrieval + parity/explainability.

Seeds a small `mev emit-graph` v2 payload (already-resolved `target_node_id`/
`target_doc_id` edge fields), converts it into `BrainEdge` rows via the Task 2
loader (``scripts/load_brain_edges.py::build_edge_rows``), and drives
``RetrieveChunksNode.retrieve()`` (Task 3) against a mocked DB session
built from those rows plus stand-in ``BrainDocument``-shaped rows. This is the
block's headline acceptance test (see ``planning/or-g-graph-aware-rag/tasks.md``
"Acceptance Criteria"):

1. A query whose answer lives in a ``related:``-neighbor of the top semantic
   hit retrieves that neighbor with ``expand_structural=True``, flagged
   ``via="structural"`` — and that neighbor is absent from the
   ``expand_structural=False`` (semantic-only) result on the same fixture.
   This is the measurable-improvement + explainability assertion.
2. On a query with no useful neighbor (a dangling/unresolvable edge), the
   structural-on and structural-off top results are identical — no
   regression, no noise injection.

No live DB and no real ``mev`` binary: ``db_session`` is patched with a fake
session whose ``.query()`` calls are pre-scripted from the loader's resolved
edge rows, mirroring the mocking pattern in
``tests/workflows/test_retrieve_chunks_node.py::TestStructuralExpand``. Only
``_semantic_search`` and ``_keyword_search`` (and ``EmbeddingService``) are
mocked — ``_structural_expand`` runs for real against the fake session, so
the actual traversal logic (Task 3) is exercised end-to-end together with the
loader's resolution logic (Task 2).
"""

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Make scripts/ importable, mirroring tests/test_load_brain_edges.py.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from database.brain_edge import BrainEdge  # noqa: E402
from load_brain_edges import build_edge_rows  # noqa: E402
from workflows.document_qa_workflow_nodes.retrieve_chunks_node import (  # noqa: E402
    RetrieveChunksNode,
)

_EMBED_PATCH = "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
_DB_SESSION_PATCH = "workflows.document_qa_workflow_nodes.retrieve_chunks_node.db_session"


def _brain_row(doc_id: str, content: str, title: str = "") -> SimpleNamespace:
    """Build a BrainDocument-shaped stand-in row (the fields _row_to_candidate reads)."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        content=content,
        section="Overview",
        is_section_title=False,
        file_path=f"docs/{doc_id}.md",
        doc_id=doc_id,
        title=title or doc_id.title(),
    )


def _fake_db_session_factory(edge_target_doc_ids: list, neighbor_rows: list):
    """Build a fake ``db_session`` generator whose single session's ``.query()``
    calls, in order, return: the brain_edges neighbor-id lookup, then the
    brain_documents neighbor row/distance fetch (mirrors
    ``TestStructuralExpand._make_session``)."""
    edge_query = MagicMock()
    edge_query.filter.return_value = edge_query
    edge_query.all.return_value = [
        MagicMock(target_doc_id=t) for t in edge_target_doc_ids
    ]

    neighbor_query = MagicMock()
    neighbor_query.filter.return_value = neighbor_query
    neighbor_query.all.return_value = neighbor_rows

    fake_session = MagicMock()
    fake_session.query.side_effect = [edge_query, neighbor_query]

    def _fake_db_session():
        yield fake_session

    return _fake_db_session


class TestBrainGraphRetrievalAcceptance:
    """OR.G headline acceptance: structural neighbor retrieval + parity."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def test_related_neighbor_is_retrieved_and_flagged_structural(self):
        """Fixture: a small emit-graph payload with an alpha -> beta related:
        edge. The top semantic hit is alpha; the query's actual answer lives
        in beta's content. With expand_structural=True, beta is retrieved and
        flagged via='structural'. With expand_structural=False (semantic-only
        path), beta never appears on the same fixture."""
        payload = {
            "version": "2",
            "root": "/path/to/brain",
            "nodes": [
                {
                    "id": "brain:alpha",
                    "scope": "brain",
                    "doc_id": "alpha",
                    "rel": "docs/alpha.md",
                },
                {
                    "id": "brain:beta",
                    "scope": "brain",
                    "doc_id": "beta",
                    "rel": "docs/beta.md",
                },
            ],
            "edges": [
                {
                    "from": "brain:alpha",
                    "to_ref": "beta",
                    "kind": "related",
                    "target_node_id": "brain:beta",
                    "target_doc_id": "beta",
                },
            ],
            "leaves": [],
        }

        # Task 2 loader reads mev's already-resolved target fields into BrainEdge-ready rows.
        edge_rows = build_edge_rows(payload)
        assert len(edge_rows) == 1
        edges = [BrainEdge(**row) for row in edge_rows]
        assert edges[0].target_doc_id == "beta"  # resolved target read through from mev

        alpha_candidate = {
            "id": uuid.uuid4(),
            "content": "Alpha covers the overview topic.",
            "section_title": "Overview",
            "is_section_title": False,
            "distance": 0.1,
            "file_path": "docs/alpha.md",
            "doc_id": "alpha",
            "title": "Alpha",
            "via": "semantic",
        }
        beta_row = _brain_row("beta", "Beta contains the specific answer the user asked for.")

        fake_db_session = _fake_db_session_factory(
            edge_target_doc_ids=[e.target_doc_id for e in edges],
            neighbor_rows=[(beta_row, 0.2)],
        )

        with patch(_EMBED_PATCH) as mock_embed, patch.object(
            self.node, "_semantic_search", return_value=[alpha_candidate]
        ), patch.object(self.node, "_keyword_search", return_value=set()), patch(
            _DB_SESSION_PATCH, fake_db_session
        ):
            mock_embed.return_value.embed_text.return_value = [0.1] * 1024
            structural_on = self.node.retrieve(
                "What is the specific answer?", corpus="brain", k=5, expand_structural=True
            )

        structural_on_by_doc_id = {r["doc_id"]: r for r in structural_on}
        assert "beta" in structural_on_by_doc_id
        assert structural_on_by_doc_id["beta"]["via"] == "structural"
        assert structural_on_by_doc_id["alpha"]["via"] == "semantic"

        # Semantic-only path on the SAME fixture: beta must be absent, and the
        # structural stage must never open the DB when the toggle is off.
        with patch(_EMBED_PATCH) as mock_embed, patch.object(
            self.node, "_semantic_search", return_value=[alpha_candidate]
        ), patch.object(self.node, "_keyword_search", return_value=set()), patch(
            _DB_SESSION_PATCH
        ) as mock_db_session:
            mock_embed.return_value.embed_text.return_value = [0.1] * 1024
            structural_off = self.node.retrieve(
                "What is the specific answer?", corpus="brain", k=5, expand_structural=False
            )

        structural_off_doc_ids = {r["doc_id"] for r in structural_off}
        assert "beta" not in structural_off_doc_ids
        assert structural_off_doc_ids == {"alpha"}
        mock_db_session.assert_not_called()

    def test_parity_when_no_useful_neighbor(self):
        """Fixture: alpha's only related: edge is dangling (mev couldn't
        resolve to_ref). The loader keeps the edge row but leaves
        target_doc_id NULL per the ingestion contract, so there is no
        traversable neighbor. structural-on and structural-off top results
        must be identical."""
        payload = {
            "version": "2",
            "root": "/path/to/brain",
            "nodes": [
                {
                    "id": "brain:alpha",
                    "scope": "brain",
                    "doc_id": "alpha",
                    "rel": "docs/alpha.md",
                },
            ],
            "edges": [
                {
                    "from": "brain:alpha",
                    "to_ref": "nonexistent-doc",
                    "kind": "related",
                    "target_node_id": None,
                    "target_doc_id": None,
                },
            ],
            "leaves": [],
        }

        edge_rows = build_edge_rows(payload)
        assert len(edge_rows) == 1
        edges = [BrainEdge(**row) for row in edge_rows]
        assert edges[0].target_doc_id is None  # dangling, never dropped

        alpha_candidate = {
            "id": uuid.uuid4(),
            "content": "Alpha is fully self-contained.",
            "section_title": "Overview",
            "is_section_title": False,
            "distance": 0.1,
            "file_path": "docs/alpha.md",
            "doc_id": "alpha",
            "title": "Alpha",
            "via": "semantic",
        }

        # The real SQL query filters target_doc_id.isnot(None), so a dangling
        # edge never surfaces a target id here — the edge lookup returns empty.
        resolved_targets = [e.target_doc_id for e in edges if e.target_doc_id is not None]
        assert resolved_targets == []

        def _run(expand: bool):
            fake_db_session = _fake_db_session_factory(
                edge_target_doc_ids=resolved_targets, neighbor_rows=[]
            )
            with patch(_EMBED_PATCH) as mock_embed, patch.object(
                self.node, "_semantic_search", return_value=[alpha_candidate]
            ), patch.object(self.node, "_keyword_search", return_value=set()), patch(
                _DB_SESSION_PATCH, fake_db_session
            ):
                mock_embed.return_value.embed_text.return_value = [0.1] * 1024
                return self.node.retrieve(
                    "Tell me about alpha", corpus="brain", k=5, expand_structural=expand
                )

        structural_on = _run(True)
        structural_off = _run(False)
        assert structural_on == structural_off
        assert [r["doc_id"] for r in structural_on] == ["alpha"]

    def test_content_corpus_regression_free(self):
        """The content corpus path is unaffected by the structural stage,
        regardless of the expand_structural toggle."""
        candidate = {
            "id": uuid.uuid4(),
            "content": "Some content chunk.",
            "section_title": "Intro",
            "is_section_title": False,
            "distance": 0.15,
        }
        with patch(_EMBED_PATCH) as mock_embed, patch.object(
            self.node, "_semantic_search", return_value=[candidate]
        ), patch.object(self.node, "_keyword_search", return_value=set()), patch(
            _DB_SESSION_PATCH
        ) as mock_db_session:
            mock_embed.return_value.embed_text.return_value = [0.1] * 1024
            result = self.node.retrieve(
                "some question", corpus="content", k=5, expand_structural=True
            )

        assert len(result) == 1
        assert result[0]["via"] == "semantic"
        mock_db_session.assert_not_called()
