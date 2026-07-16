"""Retrieval workspace-scoping acceptance tests (OR.C Task 3).

Proves the contract-§5 claim that ``RetrieveChunksNode`` retrieval is already
workspace-conformant with **no production change** — it relies on the
existing ``"brain"``-corpus ``filter_fields["project"] = "scalar"``
declaration, exactly as ``TestCrossRepoProjectScoping`` in
``test_retrieve_chunks_node.py`` proved for cross-repo sub-repo scoping. This
suite mirrors that pattern but shapes the fixture rows exactly like Task 2's
workspace-mode indexer output: ``file_path`` relative to the workspace root
(not a brain-family path) and ``project`` stamped with the workspace name
verbatim.

Cases covered:
(a) A query with ``filters={"project": "<workspace>"}`` on the ``"brain"``
    corpus returns only that workspace's chunks, driven end-to-end through
    ``RetrieveChunksNode.process()`` with the embedding seam mocked.
(b) Rows from workspace A never appear in a query scoped to workspace B,
    including two workspaces holding the same relative ``file_path``.
(c) A brain-scoped query (manifest-slug ``project`` filter, and an unfiltered
    query) is unaffected — behaves exactly as it does today.
(d) Stage 1b structural expansion is a harmless no-op for a workspace with no
    ``brain_edges`` rows — no error, no leakage.
(e) Workspace names pass through as filter values verbatim — no
    normalization (case, hyphens, etc. preserved).

Per CLAUDE.md standing rule 9, ``TaskContext`` is seeded via
``ctx.nodes["X"] = {"result": ...}`` where relevant (none needed here — this
node has no upstream dependency), and the real node-output contract
(``update_node`` -> ``{"result": ...}``) is asserted directly on ``process()``
output.
"""

import uuid
from unittest.mock import MagicMock, patch

from core.task import TaskContext
from workflows.document_qa_workflow_nodes.retrieve_chunks_node import (
    RetrieveChunksNode,
)


def _make_event(question: str = "q", corpus: str = "brain", filters: dict | None = None):
    """Return a minimal event-like object with the fields RetrieveChunksNode reads."""
    event = MagicMock()
    event.question = question
    event.corpus = corpus
    event.filters = filters
    event.include_archived = True  # skip the unrelated default-status filter
    event.expand_structural = True
    return event


def _make_ctx(question: str = "q", corpus: str = "brain", filters: dict | None = None) -> TaskContext:
    return TaskContext(event=_make_event(question, corpus, filters))


def _apply_binary_eq(expr, row) -> bool:
    """Evaluate a ``Column == literal`` SQLAlchemy BinaryExpression against a fixture row.

    Mirrors ``test_retrieve_chunks_node.py``'s helper of the same name: lets
    the fake query below apply the *actual* production filter predicate
    (built by ``_apply_metadata_filters``) to in-memory fixture rows, so the
    test exercises the real WHERE-clause contract, not a stand-in.
    """
    field = expr.left.key
    value = expr.right.value
    return getattr(row, field, None) == value


class _FakeSemanticQuery:
    """Minimal chainable stand-in for the SQLAlchemy query used in _semantic_search."""

    def __init__(self, rows_with_distance):
        self._rows = rows_with_distance

    def filter(self, *exprs):
        rows = self._rows
        for expr in exprs:
            rows = [(row, dist) for row, dist in rows if _apply_binary_eq(expr, row)]
        return _FakeSemanticQuery(rows)

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, n):
        return _FakeSemanticQuery(self._rows[:n])

    def all(self):
        return self._rows


def _make_workspace_row(
    project: str,
    file_path: str,
    content: str = "workspace content",
    doc_id: str | None = None,
):
    """Build a fixture row shaped exactly like Task 2's workspace-mode output:
    ``file_path`` relative to the workspace root (no brain-family prefix) and
    ``project`` stamped with the workspace name verbatim."""
    row = MagicMock()
    row.id = uuid.uuid4()
    row.content = content
    row.section = "## Overview"
    row.is_section_title = False
    row.file_path = file_path
    row.doc_id = doc_id or f"{project}:{file_path}"
    row.title = None
    row.project = project
    row.status = None
    return row


def _run_semantic_search_scoped(node: RetrieveChunksNode, project_filter: str, rows) -> list[dict]:
    """Drive the real ``_semantic_search`` (and real ``_apply_metadata_filters``)
    over ``rows`` scoped by ``filters={"project": project_filter}``."""
    fake_query = _FakeSemanticQuery([(row, 0.1) for row in rows])
    fake_session = MagicMock()
    fake_session.query.return_value = fake_query

    def _fake_db_session():
        yield fake_session

    with patch(
        "workflows.document_qa_workflow_nodes.retrieve_chunks_node.db_session",
        _fake_db_session,
    ):
        return RetrieveChunksNode._semantic_search(
            node,
            [0.1] * 1024,
            "brain",
            limit=20,
            filters={"project": project_filter},
            include_archived=True,
        )


class TestWorkspaceScopingEndToEnd:
    """(a) process() end-to-end: a workspace-scoped query returns only that
    workspace's chunks — driving the real _semantic_search/_apply_metadata_filters
    path, not a pre-filtered mock."""

    def setup_method(self):
        self.node = RetrieveChunksNode()
        self.workspace_a_row = _make_workspace_row(
            "learn-ai-notes", "guides/setup.md", content="workspace A setup guide"
        )
        self.workspace_b_row = _make_workspace_row(
            "second-brain", "guides/setup.md", content="workspace B setup guide"
        )
        self.all_rows = [self.workspace_a_row, self.workspace_b_row]

    def _process_scoped(self, project_filter: str) -> list[dict]:
        ctx = _make_ctx(corpus="brain", filters={"project": project_filter})

        def _fake_semantic_search(_vector, _corpus, limit, filters=None, include_archived=False):
            return _run_semantic_search_scoped(self.node, filters["project"], self.all_rows)

        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as mock_emb, patch.object(
            self.node, "_semantic_search", side_effect=_fake_semantic_search
        ), patch.object(
            self.node, "_keyword_search", return_value={}
        ), patch.object(
            self.node, "_keyword_expand", return_value=[]
        ), patch.object(
            self.node, "_structural_expand", return_value=[]
        ):
            mock_emb.return_value.embed_text.return_value = [0.1] * 1024
            result_ctx = self.node.process(ctx)

        # CLAUDE.md standing rule 9: process() stores output as {"result": ...}
        return result_ctx.nodes[self.node.node_name]["result"]["chunks"]

    def test_workspace_scoped_query_returns_only_that_workspaces_chunks(self):
        """filters={"project": "learn-ai-notes"} returns only that workspace's chunk."""
        chunks = self._process_scoped("learn-ai-notes")
        assert len(chunks) == 1
        assert chunks[0]["content"] == "workspace A setup guide"
        assert chunks[0]["file_path"] == "guides/setup.md"

    def test_symmetric_workspace_scoped_query_does_not_leak(self):
        """filters={"project": "second-brain"} returns only that workspace's
        chunk — no leakage from the other workspace, even though both share
        the same relative file_path ("guides/setup.md")."""
        chunks = self._process_scoped("second-brain")
        assert len(chunks) == 1
        assert chunks[0]["content"] == "workspace B setup guide"


class TestWorkspaceIsolationAcrossSameRelativePath:
    """(b) Two workspaces sharing an identical relative file_path never
    cross-contaminate — the project filter is what disambiguates them, not
    file_path uniqueness."""

    def setup_method(self):
        self.node = RetrieveChunksNode()
        self.row_a = _make_workspace_row("ws-alpha", "README.md", content="alpha readme")
        self.row_b = _make_workspace_row("ws-beta", "README.md", content="beta readme")
        self.rows = [self.row_a, self.row_b]

    def test_project_a_scoped_query_excludes_project_b_same_path_row(self):
        results = _run_semantic_search_scoped(self.node, "ws-alpha", self.rows)
        assert len(results) == 1
        assert results[0]["content"] == "alpha readme"

    def test_project_b_scoped_query_excludes_project_a_same_path_row(self):
        results = _run_semantic_search_scoped(self.node, "ws-beta", self.rows)
        assert len(results) == 1
        assert results[0]["content"] == "beta readme"


class TestBrainScopedQueryUnaffected:
    """(c) A brain-scoped query (manifest-slug project filter, and an
    unfiltered query) behaves exactly as it does today — unaffected by the
    existence of workspace-mode rows in the same table."""

    def setup_method(self):
        self.node = RetrieveChunksNode()
        self.brain_row = _make_workspace_row(
            "orchestrator", "docs/api-reference.md", content="brain manifest-slug content"
        )
        self.workspace_row = _make_workspace_row(
            "learn-ai-notes", "docs/api-reference.md", content="workspace content"
        )
        self.rows = [self.brain_row, self.workspace_row]

    def test_manifest_slug_scoped_query_excludes_workspace_row(self):
        """A brain-family manifest slug (e.g. "orchestrator") scopes out a
        workspace-mode row sharing the same relative path."""
        results = _run_semantic_search_scoped(self.node, "orchestrator", self.rows)
        assert len(results) == 1
        assert results[0]["content"] == "brain manifest-slug content"

    def test_unfiltered_query_returns_all_rows_unchanged(self):
        """No filters at all: today's unscoped behavior is unchanged — every
        row in the candidate set is returned regardless of project."""
        fake_query = _FakeSemanticQuery([(row, 0.1) for row in self.rows])
        fake_session = MagicMock()
        fake_session.query.return_value = fake_query

        def _fake_db_session():
            yield fake_session

        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.db_session",
            _fake_db_session,
        ):
            results = RetrieveChunksNode._semantic_search(
                self.node,
                [0.1] * 1024,
                "brain",
                limit=20,
                filters=None,
                include_archived=True,
            )
        assert {r["content"] for r in results} == {
            "brain manifest-slug content",
            "workspace content",
        }


class TestStructuralExpansionNoOpForWorkspace:
    """(d) Stage 1b structural expansion is a harmless no-op for a workspace
    with no brain_edges rows — no error, no leakage of unrelated rows."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def test_no_edges_returns_empty_without_error(self):
        """A workspace-mode candidate (doc_id present, no brain_edges rows
        referencing it) produces an empty structural-expansion result."""
        seed = _make_workspace_row("learn-ai-notes", "guides/setup.md")
        candidate = {
            "id": seed.id,
            "content": seed.content,
            "section_title": seed.section,
            "is_section_title": False,
            "distance": 0.1,
            "file_path": seed.file_path,
            "doc_id": seed.doc_id,
            "title": None,
            "via": "semantic",
        }

        edge_query = MagicMock()
        edge_query.filter.return_value = edge_query
        edge_query.all.return_value = []  # no brain_edges rows at all

        fake_session = MagicMock()
        fake_session.query.return_value = edge_query

        def _fake_db_session():
            yield fake_session

        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.db_session",
            _fake_db_session,
        ):
            result = self.node._structural_expand([candidate], "brain", [0.1] * 1024)

        assert result == []

    def test_retrieve_unaffected_when_structural_expand_is_a_noop(self):
        """retrieve() end-to-end: with _structural_expand returning [] (the
        no-edges case), the fused result is identical to the Stage-1
        semantic-only candidate set — no extra, no leaked rows."""
        row = _make_workspace_row("learn-ai-notes", "guides/setup.md", content="setup content")

        def _fake_semantic_search(_vector, _corpus, limit, filters=None, include_archived=False):
            return _run_semantic_search_scoped(self.node, "learn-ai-notes", [row])

        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as mock_emb, patch.object(
            self.node, "_semantic_search", side_effect=_fake_semantic_search
        ), patch.object(
            self.node, "_keyword_search", return_value={}
        ), patch.object(
            self.node, "_keyword_expand", return_value=[]
        ), patch.object(
            self.node, "_structural_expand", return_value=[]
        ):
            mock_emb.return_value.embed_text.return_value = [0.1] * 1024
            results = self.node.retrieve(
                "q", corpus="brain", filters={"project": "learn-ai-notes"}, include_archived=True
            )

        assert len(results) == 1
        assert results[0]["content"] == "setup content"


class TestWorkspaceNamesPassThroughVerbatim:
    """(e) Workspace names are used verbatim as the filter value — no
    normalization (case, hyphens, underscores) is applied anywhere in the
    retrieval path."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def test_mixed_case_and_hyphenated_name_matched_exactly(self):
        """A workspace name is matched by exact string equality — no
        lower()/normalize() is applied to either the filter value or the
        stored project column."""
        exact_row = _make_workspace_row("My-Weird_Workspace", "notes.md", content="exact match")
        near_miss_row = _make_workspace_row(
            "my-weird_workspace", "notes.md", content="near-miss, different case"
        )
        rows = [exact_row, near_miss_row]

        results = _run_semantic_search_scoped(self.node, "My-Weird_Workspace", rows)

        assert len(results) == 1
        assert results[0]["content"] == "exact match"

    def test_no_registry_slug_normalization_leaks_across_names(self):
        """Two distinctly-cased names never collapse into the same scope."""
        results_lower = _run_semantic_search_scoped(
            self.node,
            "my-weird_workspace",
            [
                _make_workspace_row("My-Weird_Workspace", "notes.md", content="upper variant"),
                _make_workspace_row("my-weird_workspace", "notes.md", content="lower variant"),
            ],
        )
        assert len(results_lower) == 1
        assert results_lower[0]["content"] == "lower variant"
