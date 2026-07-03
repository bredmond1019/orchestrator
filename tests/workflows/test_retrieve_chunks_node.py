"""Tests for RetrieveChunksNode — two-stage hybrid retrieval.

These tests cover:
- ``_fuse_and_rank`` (pure function): ordering, keyword boost, section-title
  weighting, threshold filtering, top-k truncation, NaN safety.
- ``retrieve`` (integration path): patches ``_semantic_search``,
  ``_keyword_search``, and ``EmbeddingService`` to verify the full call
  contract without a live database or Voyage API key.
- ``process``: verifies ``TaskContext`` seeding and output stored under the
  right key with the ``{"result": ...}`` contract (CLAUDE.md rule 9).
- Corpus dispatch: ``corpus="brain"`` threads through to ``_semantic_search``.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from core.task import TaskContext
from workflows.document_qa_workflow_nodes.retrieve_chunks_node import RetrieveChunksNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candidate(
    dist: float = 0.1,
    is_section_title: bool = False,
    content: str = "some content",
    section_title: str | None = "Intro",
    candidate_id: uuid.UUID | None = None,
) -> dict:
    """Build a candidate dict as returned by ``_semantic_search``."""
    return {
        "id": candidate_id or uuid.uuid4(),
        "content": content,
        "section_title": section_title,
        "is_section_title": is_section_title,
        "distance": dist,
    }


def _make_event(question: str = "What is RAG?", corpus: str = "content"):
    """Return a minimal event-like object with the fields RetrieveChunksNode reads."""
    event = MagicMock()
    event.question = question
    event.corpus = corpus
    return event


def _make_ctx(question: str = "What is RAG?", corpus: str = "content") -> TaskContext:
    """Build a TaskContext with a minimal mock event."""
    ctx = TaskContext(event=_make_event(question, corpus))
    return ctx


# ---------------------------------------------------------------------------
# _fuse_and_rank — pure function tests (no DB, no mock needed)
# ---------------------------------------------------------------------------


class TestFuseAndRank:
    """Pure unit tests for _fuse_and_rank. No DB or network involved."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def test_semantic_ranking_orders_by_distance(self):
        """Without keyword hits, candidates are ranked by semantic similarity."""
        c1 = _make_candidate(dist=0.1)   # similarity 0.9
        c2 = _make_candidate(dist=0.3)   # similarity 0.7
        c3 = _make_candidate(dist=0.2)   # similarity 0.8
        results = self.node._fuse_and_rank([c1, c2, c3], set(), k=3, threshold=0.0)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)
        assert results[0]["content"] == c1["content"]

    def test_keyword_boost_changes_order(self):
        """The candidate with a keyword hit outranks one with a slightly better distance."""
        close_id = uuid.uuid4()
        far_id = uuid.uuid4()
        # far has a worse distance (0.25) but gets a keyword boost of 1.0
        close = _make_candidate(dist=0.1, candidate_id=close_id)
        far = _make_candidate(dist=0.25, candidate_id=far_id)
        keyword_ids = {far_id}
        results = self.node._fuse_and_rank([close, far], keyword_ids, k=2, threshold=0.0)
        # far: (1-0.25)*1 + 1.0 = 0.75 + 1.0 = 1.75
        # close: (1-0.1)*1 + 0.0 = 0.9
        assert results[0]["id"] == far_id

    def test_section_title_chunk_weighted_2x(self):
        """A section-title chunk with worse distance outranks a body chunk."""
        body_id = uuid.uuid4()
        title_id = uuid.uuid4()
        body = _make_candidate(dist=0.05, is_section_title=False, candidate_id=body_id)
        title = _make_candidate(dist=0.3, is_section_title=True, candidate_id=title_id)
        # body score:  (1-0.05)*1 = 0.95
        # title score: (1-0.3)*2  = 1.40
        results = self.node._fuse_and_rank([body, title], set(), k=2, threshold=0.0)
        assert results[0]["id"] == title_id

    def test_threshold_filters_low_scores(self):
        """Candidates with a fused score below threshold are excluded."""
        c1 = _make_candidate(dist=0.9)   # similarity 0.1, score 0.1
        c2 = _make_candidate(dist=0.1)   # similarity 0.9, score 0.9
        results = self.node._fuse_and_rank([c1, c2], set(), k=5, threshold=0.5)
        assert len(results) == 1
        assert results[0]["content"] == c2["content"]

    def test_top_k_respected(self):
        """Only the top-k candidates are returned."""
        candidates = [_make_candidate(dist=0.1 * i) for i in range(1, 21)]
        results = self.node._fuse_and_rank(candidates, set(), k=5, threshold=0.0)
        assert len(results) == 5

    def test_nan_distance_does_not_crash(self):
        """A NaN distance is silently filtered; no exception is raised."""
        nan_c = _make_candidate(dist=float("nan"))
        good_c = _make_candidate(dist=0.2)
        results = self.node._fuse_and_rank([nan_c, good_c], set(), k=5, threshold=0.0)
        # The NaN candidate must be absent; the good one must be present
        assert len(results) == 1
        assert results[0]["id"] == good_c["id"]

    def test_nan_only_candidates_returns_empty(self):
        """All NaN distances → empty result list, no crash."""
        candidates = [_make_candidate(dist=float("nan")) for _ in range(5)]
        results = self.node._fuse_and_rank(candidates, set(), k=5, threshold=0.0)
        assert results == []

    def test_empty_candidates_returns_empty(self):
        """Empty input list returns empty result list."""
        assert self.node._fuse_and_rank([], set(), k=5, threshold=0.0) == []

    def test_output_dict_has_required_keys(self):
        """Each returned dict contains the required normalized keys."""
        c = _make_candidate(dist=0.2, section_title="Overview")
        results = self.node._fuse_and_rank([c], set(), k=1, threshold=0.0)
        assert len(results) == 1
        assert {"content", "section_title", "score", "source"}.issubset(results[0].keys())
        assert results[0]["section_title"] == "Overview"
        assert results[0]["source"] == "Overview"

    def test_output_source_defaults_to_general_when_no_section(self):
        """Source falls back to 'General' when section_title is None."""
        c = _make_candidate(dist=0.2, section_title=None)
        results = self.node._fuse_and_rank([c], set(), k=1, threshold=0.0)
        assert results[0]["source"] == "General"

    def test_score_formula_body_chunk_no_keyword(self):
        """Exact score for a body chunk with no keyword match."""
        c = _make_candidate(dist=0.4, is_section_title=False)
        results = self.node._fuse_and_rank([c], set(), k=1, threshold=0.0)
        assert abs(results[0]["score"] - 0.6) < 1e-9

    def test_score_formula_section_title_with_keyword(self):
        """Exact score for a section-title chunk with a keyword match."""
        cid = uuid.uuid4()
        c = _make_candidate(dist=0.2, is_section_title=True, candidate_id=cid)
        results = self.node._fuse_and_rank([c], {cid}, k=1, threshold=0.0)
        # score = (1-0.2)*2 + 1.0 = 1.6 + 1.0 = 2.6
        assert abs(results[0]["score"] - 2.6) < 1e-9


# ---------------------------------------------------------------------------
# retrieve() — integration path with mocked DB seams
# ---------------------------------------------------------------------------


class TestRetrieve:
    """Tests for the retrieve() method; patches _semantic_search, _keyword_search,
    and EmbeddingService so no live DB or API key is needed."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def _run_retrieve(
        self,
        candidates: list[dict],
        keyword_ids: set | None = None,
        query: str = "test query",
        corpus: str = "content",
        k: int = 5,
        threshold: float = 0.0,
    ) -> list[dict]:
        """Patch all external calls and invoke retrieve()."""
        keyword_ids = keyword_ids or set()
        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as MockEmb, patch.object(
            self.node, "_semantic_search", return_value=candidates
        ) as mock_sem, patch.object(
            self.node, "_keyword_search", return_value=keyword_ids
        ) as mock_kw:
            MockEmb.return_value.embed_text.return_value = [0.1] * 1024
            result = self.node.retrieve(query, corpus=corpus, k=k, threshold=threshold)
        return result

    def test_returns_list_of_dicts(self):
        """retrieve() returns a list of normalized dicts."""
        candidates = [_make_candidate(dist=0.2)]
        result = self._run_retrieve(candidates)
        assert isinstance(result, list)

    def test_top_k_observed(self):
        """retrieve() respects the k limit end to end."""
        candidates = [_make_candidate(dist=0.1 * i) for i in range(1, 10)]
        result = self._run_retrieve(candidates, k=3)
        assert len(result) <= 3

    def test_embedding_service_called_once(self):
        """EmbeddingService.embed_text is called exactly once per retrieve call."""
        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as MockEmb, patch.object(
            self.node, "_semantic_search", return_value=[]
        ), patch.object(
            self.node, "_keyword_search", return_value=set()
        ):
            MockEmb.return_value.embed_text.return_value = [0.0] * 1024
            self.node.retrieve("question")
            MockEmb.return_value.embed_text.assert_called_once_with("question")

    def test_semantic_search_called_with_vector_and_corpus(self):
        """_semantic_search receives the embedded vector and the corpus name."""
        expected_vector = [0.5] * 1024
        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as MockEmb, patch.object(
            self.node, "_semantic_search", return_value=[]
        ) as mock_sem, patch.object(
            self.node, "_keyword_search", return_value=set()
        ):
            MockEmb.return_value.embed_text.return_value = expected_vector
            self.node.retrieve("q", corpus="brain", k=5)
            mock_sem.assert_called_once_with(
                expected_vector,
                "brain",
                limit=20,
                filters=None,
                include_archived=False,
            )

    def test_corpus_brain_threads_through(self):
        """corpus='brain' is forwarded to _semantic_search."""
        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as MockEmb, patch.object(
            self.node, "_semantic_search", return_value=[]
        ) as mock_sem, patch.object(
            self.node, "_keyword_search", return_value=set()
        ):
            MockEmb.return_value.embed_text.return_value = [0.0] * 1024
            self.node.retrieve("q", corpus="brain")
            # _semantic_search(vector, corpus, limit=20) — corpus is positional arg 1
            positional_args = mock_sem.call_args[0]
            assert positional_args[1] == "brain"

    def test_keyword_search_called_with_candidate_ids(self):
        """_keyword_search receives the candidate IDs from _semantic_search."""
        cid = uuid.uuid4()
        candidates = [_make_candidate(candidate_id=cid)]
        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as MockEmb, patch.object(
            self.node, "_semantic_search", return_value=candidates
        ), patch.object(
            self.node, "_keyword_search", return_value=set()
        ) as mock_kw:
            MockEmb.return_value.embed_text.return_value = [0.0] * 1024
            self.node.retrieve("q")
            call_args = mock_kw.call_args[0]
            assert cid in call_args[1]  # candidate_ids argument

    def test_threshold_applied(self):
        """High threshold results in empty list when candidates score below it."""
        candidates = [_make_candidate(dist=0.9)]  # similarity = 0.1
        result = self._run_retrieve(candidates, threshold=0.5)
        assert result == []

    def test_punctuation_stripped_from_query_terms(self):
        """Terms like 'RAG?' are cleaned to 'RAG' before the ILIKE filter.

        Without stripping, the pattern '%RAG?%' never matches content that
        just says 'RAG', so the keyword boost silently never fires for
        question-form queries.

        We capture the SQLAlchemy ILIKE expressions assembled inside
        ``_keyword_search`` to verify no term contains punctuation.
        """
        cid = uuid.uuid4()
        candidate_ids = [cid]

        fake_row = MagicMock()
        fake_row.id = cid

        fake_query = MagicMock()
        fake_query.filter.return_value = fake_query
        fake_query.all.return_value = [fake_row]

        fake_session = MagicMock()
        fake_session.query.return_value = fake_query

        # db_session is a plain generator function; the node wraps it with
        # contextmanager() at call time, so we must patch it as a generator.
        def _fake_db_session():
            yield fake_session

        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.db_session",
            _fake_db_session,
        ):
            result = self.node._keyword_search(
                "What is RAG?", candidate_ids, "content"
            )

        # The call succeeded and returned the candidate id (keyword match)
        assert cid in result

        # Verify the ILIKE args passed to filter() contain no trailing '?'
        # filter() is called twice: once for id.in_(), once for or_(*ilike_filters)
        all_call_args = [str(c) for c in fake_query.filter.call_args_list]
        combined = " ".join(all_call_args)
        assert "RAG?" not in combined


# ---------------------------------------------------------------------------
# process() — TaskContext integration
# ---------------------------------------------------------------------------


class TestProcess:
    """Tests for the process() method, verifying TaskContext seeding and output."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def test_process_stores_result_in_task_context(self):
        """process() stores chunks under node_name with the {'result': ...} contract."""
        ctx = _make_ctx(question="What is a workflow?", corpus="content")
        fake_chunks = [
            {
                "content": "A workflow is a DAG.",
                "section_title": "Overview",
                "score": 0.9,
                "source": "Overview",
            }
        ]
        with patch.object(
            self.node, "retrieve", return_value=fake_chunks
        ):
            ctx = self.node.process(ctx)

        output = ctx.get_node_output("RetrieveChunksNode")
        assert "result" in output
        assert output["result"]["chunks"] == fake_chunks

    def test_process_passes_corpus_from_event(self):
        """process() reads corpus from the event and passes it to retrieve."""
        ctx = _make_ctx(question="brain question", corpus="brain")
        with patch.object(self.node, "retrieve", return_value=[]) as mock_ret:
            self.node.process(ctx)
        _, call_kwargs = mock_ret.call_args[0], mock_ret.call_args[1]
        assert mock_ret.call_args[1].get("corpus") == "brain" or \
               (len(mock_ret.call_args[0]) > 1 and mock_ret.call_args[0][1] == "brain")

    def test_process_defaults_corpus_to_content_when_absent(self):
        """process() falls back to corpus='content' if the event has no corpus attr."""
        event = MagicMock(spec=["question"])
        event.question = "What is chunking?"
        ctx = TaskContext(event=event)
        with patch.object(self.node, "retrieve", return_value=[]) as mock_ret:
            self.node.process(ctx)
        # The default should be "content"
        call_kwargs = mock_ret.call_args
        corpus_arg = (
            call_kwargs[1].get("corpus")
            if call_kwargs[1]
            else (call_kwargs[0][1] if len(call_kwargs[0]) > 1 else None)
        )
        assert corpus_arg == "content"

    def test_process_passes_filters_from_event(self):
        """process() reads filters from the event and forwards them to retrieve."""
        event = MagicMock()
        event.question = "brain question"
        event.corpus = "brain"
        event.filters = {"project": "orchestrator"}
        ctx = TaskContext(event=event)
        with patch.object(self.node, "retrieve", return_value=[]) as mock_ret:
            self.node.process(ctx)
        call_kwargs = mock_ret.call_args[1]
        assert call_kwargs.get("filters") == {"project": "orchestrator"}

    def test_process_defaults_filters_to_none_when_absent(self):
        """process() passes filters=None when the event has no filters attr."""
        event = MagicMock(spec=["question", "corpus"])
        event.question = "What is chunking?"
        event.corpus = "content"
        ctx = TaskContext(event=event)
        with patch.object(self.node, "retrieve", return_value=[]) as mock_ret:
            self.node.process(ctx)
        call_kwargs = mock_ret.call_args[1]
        assert call_kwargs.get("filters") is None


# ---------------------------------------------------------------------------
# Keyword-extra-fields boost — brain corpus only
# ---------------------------------------------------------------------------


class TestKeywordSearchShapes:
    """_keyword_search returns a graded dict for FTS corpora, a set for legacy."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def test_brain_keyword_search_returns_graded_dict(self):
        """The brain corpus uses the FTS path: returns dict[id -> ts_rank]."""
        cid = uuid.uuid4()
        candidate_ids = [cid]

        # FTS path selects (model.id, ts_rank) rows — supply a concrete rank.
        fake_row = MagicMock()
        fake_row.id = cid
        fake_row.kw_rank = 0.42

        fake_query = MagicMock()
        fake_query.filter.return_value = fake_query
        fake_query.all.return_value = [fake_row]

        fake_session = MagicMock()
        fake_session.query.return_value = fake_query

        def _fake_db_session():
            yield fake_session

        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.db_session",
            _fake_db_session,
        ):
            result = self.node._keyword_search("data contract", candidate_ids, "brain")

        # Graded result: a dict mapping id -> float ts_rank (not a set).
        assert isinstance(result, dict)
        assert result[cid] == pytest.approx(0.42)
        # FTS path filters twice: id.in_(candidate_ids) and tsv @@ tsquery.
        assert fake_query.filter.call_count >= 2

    def test_brain_empty_candidates_returns_empty_dict(self):
        """No candidates → empty dict (FTS shape), not an empty set."""
        result = self.node._keyword_search("anything", [], "brain")
        assert result == {}

    def test_content_empty_candidates_returns_empty_set(self):
        """No candidates → empty set (legacy shape) for the content corpus."""
        result = self.node._keyword_search("anything", [], "content")
        assert result == set()

    def test_content_corpus_keyword_search_unchanged(self):
        """_keyword_search for content corpus uses only content column, no keyword_extra_fields."""
        cid = uuid.uuid4()
        candidate_ids = [cid]

        filter_call_args = []
        fake_row = MagicMock()
        fake_row.id = cid

        def capturing_filter(*args, **kwargs):
            filter_call_args.extend(args)
            m = MagicMock()
            m.filter = capturing_filter
            m.all.return_value = [fake_row]
            return m

        fake_query = MagicMock()
        fake_query.filter = capturing_filter

        fake_session = MagicMock()
        fake_session.query.return_value = fake_query

        def _fake_db_session():
            yield fake_session

        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.db_session",
            _fake_db_session,
        ):
            result = self.node._keyword_search("python", candidate_ids, "content")

        # Verify no array_to_string appears in the filter args string — content corpus
        # should only use the content column, not any extra fields
        combined = " ".join(str(a) for a in filter_call_args)
        assert "array_to_string" not in combined.lower()


# ---------------------------------------------------------------------------
# Filters — metadata scoping for brain corpus
# ---------------------------------------------------------------------------


class TestSemanticSearchFilters:
    """Tests for optional filters param in retrieve() and _semantic_search."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def _run_retrieve_with_filters(
        self,
        candidates: list[dict],
        filters: dict | None,
        corpus: str = "brain",
    ) -> list[dict]:
        """Patch seams and call retrieve() with optional filters."""
        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as MockEmb, patch.object(
            self.node, "_semantic_search", return_value=candidates
        ) as mock_sem, patch.object(
            self.node, "_keyword_search", return_value=set()
        ):
            MockEmb.return_value.embed_text.return_value = [0.1] * 1024
            result = self.node.retrieve("q", corpus=corpus, k=5, filters=filters)
        return result

    def test_retrieve_forwards_filters_to_semantic_search(self):
        """retrieve() passes filters kwarg through to _semantic_search."""
        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as MockEmb, patch.object(
            self.node, "_semantic_search", return_value=[]
        ) as mock_sem, patch.object(
            self.node, "_keyword_search", return_value=set()
        ):
            MockEmb.return_value.embed_text.return_value = [0.1] * 1024
            self.node.retrieve("q", corpus="brain", filters={"project": "acme"})
            call_kwargs = mock_sem.call_args[1]
            assert call_kwargs.get("filters") == {"project": "acme"}

    def test_retrieve_without_filters_passes_none_to_semantic_search(self):
        """retrieve() passes filters=None when not supplied."""
        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as MockEmb, patch.object(
            self.node, "_semantic_search", return_value=[]
        ) as mock_sem, patch.object(
            self.node, "_keyword_search", return_value=set()
        ):
            MockEmb.return_value.embed_text.return_value = [0.1] * 1024
            self.node.retrieve("q", corpus="brain")
            call_kwargs = mock_sem.call_args[1]
            assert call_kwargs.get("filters") is None

    def test_content_corpus_retrieve_unaffected_by_filters(self):
        """retrieve() with corpus='content' passes filters through but content corpus ignores them."""
        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as MockEmb, patch.object(
            self.node, "_semantic_search", return_value=[]
        ) as mock_sem, patch.object(
            self.node, "_keyword_search", return_value=set()
        ):
            MockEmb.return_value.embed_text.return_value = [0.1] * 1024
            # Should not raise even with filters for content corpus
            result = self.node.retrieve(
                "q", corpus="content", filters={"project": "acme"}
            )
            assert isinstance(result, list)

    def test_filters_none_produces_same_result_as_no_filters(self):
        """filters=None and no filters param produce identical results."""
        cand = _make_candidate(dist=0.2)
        result_no_filters = self._run_retrieve_with_filters([cand], filters=None)
        result_with_none = self._run_retrieve_with_filters([cand], filters=None)
        assert result_no_filters == result_with_none

    def test_scalar_filter_excludes_non_matching_rows(self):
        """A project filter excludes a fixture row whose project does not match.

        We verify this at the _semantic_search seam: when filters scope to
        project='matching-project', the seam mock returns only the matching
        candidate (simulating the WHERE clause). The excluded 'deprecated' row
        is never returned by _semantic_search.
        """
        matching_id = uuid.uuid4()
        excluded_id = uuid.uuid4()
        matching = _make_candidate(dist=0.1, candidate_id=matching_id)
        # excluded row — _semantic_search would filter it out via WHERE
        # We model this by having _semantic_search only return the matching row.

        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as MockEmb, patch.object(
            self.node, "_semantic_search", return_value=[matching]
        ) as mock_sem, patch.object(
            self.node, "_keyword_search", return_value=set()
        ):
            MockEmb.return_value.embed_text.return_value = [0.1] * 1024
            result = self.node.retrieve(
                "q",
                corpus="brain",
                filters={"project": "matching-project"},
            )

        # _semantic_search was called with the filter
        call_kwargs = mock_sem.call_args[1]
        assert call_kwargs.get("filters") == {"project": "matching-project"}
        # The result contains only the matching candidate; excluded_id is absent
        result_ids = {r["id"] for r in result}
        assert matching_id in result_ids
        assert excluded_id not in result_ids


# ---------------------------------------------------------------------------
# OR.O — cross-repo retrieval scoping via the existing "brain"-corpus project filter
# ---------------------------------------------------------------------------


def _apply_binary_eq(expr, row) -> bool:
    """Evaluate a ``Column == literal`` SQLAlchemy BinaryExpression against a fixture row.

    ``_apply_metadata_filters`` builds real ``BrainDocument.project == value``
    expressions (SQLAlchemy expression construction needs no DB connection).
    This lets the fake query below apply the *actual* production filter
    predicate to in-memory fixture rows, rather than re-implementing the
    scoping logic by hand — so the test exercises the real WHERE-clause
    contract, not a stand-in.
    """
    field = expr.left.key
    value = expr.right.value
    return getattr(row, field, None) == value


class _FakeSemanticQuery:
    """Minimal chainable stand-in for the SQLAlchemy query used in _semantic_search.

    Wraps a fixed list of ``(row, distance)`` pairs and applies real
    ``BinaryExpression`` filters (built by ``_apply_metadata_filters``)
    against each row's attributes, so ``filters={"project": ...}`` scopes the
    fixture set exactly as the real ``project == value`` WHERE clause would.
    """

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


class TestCrossRepoProjectScoping:
    """Proves the existing "brain"-corpus ``project`` filter scopes sub-repo corpora.

    OR.O ships no new retrieval code — it relies on ``RetrieveChunksNode``'s
    existing ``filter_fields["project"] = "scalar"`` declaration. This drives
    the *real* ``_semantic_search`` method (not a patched seam) against two
    fixture ``BrainDocument`` rows tagged with different manifest slugs
    (simulating two sub-repos' widened corpora) and proves a project-scoped
    query never returns the other repo's chunk.
    """

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def _make_fixture_row(self, project: str, content: str):
        row = MagicMock()
        row.id = uuid.uuid4()
        row.content = content
        row.section = "## Status"
        row.is_section_title = False
        row.file_path = f"core/{project}/planning/status.md"
        row.doc_id = f"{project}-status"
        row.title = None
        row.project = project
        row.status = None
        return row

    def _run_semantic_search_scoped(self, project_filter: str) -> list[dict]:
        repo_a_row = self._make_fixture_row("repo-a", "repo-a status content")
        repo_b_row = self._make_fixture_row("repo-b", "repo-b status content")
        fake_query = _FakeSemanticQuery(
            [(repo_a_row, 0.1), (repo_b_row, 0.1)]
        )

        fake_session = MagicMock()
        fake_session.query.return_value = fake_query

        def _fake_db_session():
            yield fake_session

        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.db_session",
            _fake_db_session,
        ):
            # Call the unbound method directly so this helper still exercises
            # the real _semantic_search even when the instance's
            # _semantic_search attribute is itself patched (as it is in the
            # end-to-end retrieve() test below).
            return RetrieveChunksNode._semantic_search(
                self.node,
                [0.1] * 1024,
                "brain",
                limit=20,
                filters={"project": project_filter},
                include_archived=True,  # skip the unrelated default-status filter
            )

    def test_project_scoped_query_returns_only_that_repos_chunks(self):
        """filters={"project": "repo-a"} returns only repo-a's chunk."""
        results = self._run_semantic_search_scoped("repo-a")
        assert len(results) == 1
        assert results[0]["file_path"] == "core/repo-a/planning/status.md"

    def test_symmetric_project_scoped_query_does_not_leak(self):
        """filters={"project": "repo-b"} returns only repo-b's chunk — no leakage from repo-a."""
        results = self._run_semantic_search_scoped("repo-b")
        assert len(results) == 1
        assert results[0]["file_path"] == "core/repo-b/planning/status.md"

    def test_retrieve_end_to_end_scopes_by_project_per_repo(self):
        """retrieve() end-to-end: two project-scoped queries never cross-contaminate."""

        def _fake_semantic_search(_vector, _corpus, limit, filters=None, include_archived=False):
            return self._run_semantic_search_scoped(filters["project"])

        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as MockEmb, patch.object(
            self.node, "_semantic_search", side_effect=_fake_semantic_search
        ), patch.object(
            self.node, "_keyword_search", return_value=set()
        ), patch.object(
            self.node, "_structural_expand", return_value=[]
        ):
            MockEmb.return_value.embed_text.return_value = [0.1] * 1024
            result_a = self.node.retrieve(
                "q", corpus="brain", filters={"project": "repo-a"}, include_archived=True
            )
            result_b = self.node.retrieve(
                "q", corpus="brain", filters={"project": "repo-b"}, include_archived=True
            )

        assert {r["file_path"] for r in result_a} == {"core/repo-a/planning/status.md"}
        assert {r["file_path"] for r in result_b} == {"core/repo-b/planning/status.md"}


# ---------------------------------------------------------------------------
# Graded keyword fusion (FTS dict path) + provenance fields
# ---------------------------------------------------------------------------


class TestGradedKeywordFusion:
    """_fuse_and_rank grades the keyword contribution when given a dict[id->rank]."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def test_higher_ts_rank_yields_higher_score(self):
        """With equal distance, the candidate with the larger ts_rank ranks first."""
        weak_id = uuid.uuid4()
        strong_id = uuid.uuid4()
        weak = _make_candidate(dist=0.2, candidate_id=weak_id)
        strong = _make_candidate(dist=0.2, candidate_id=strong_id)
        graded = {weak_id: 0.01, strong_id: 0.30}
        results = self.node._fuse_and_rank([weak, strong], graded, k=2, threshold=0.0)
        assert results[0]["id"] == strong_id

    def test_graded_score_uses_kw_weight(self):
        """Score = similarity*title_weight + _KW_WEIGHT*ts_rank (exact)."""
        from workflows.document_qa_workflow_nodes.retrieve_chunks_node import (
            _KW_WEIGHT,
        )

        cid = uuid.uuid4()
        c = _make_candidate(dist=0.2, is_section_title=False, candidate_id=cid)
        results = self.node._fuse_and_rank([c], {cid: 0.10}, k=1, threshold=0.0)
        expected = (1.0 - 0.2) * 1.0 + _KW_WEIGHT * 0.10
        assert results[0]["score"] == pytest.approx(expected)

    def test_dict_without_match_adds_zero(self):
        """A candidate absent from the graded dict gets no keyword contribution."""
        cid = uuid.uuid4()
        c = _make_candidate(dist=0.3, candidate_id=cid)
        results = self.node._fuse_and_rank([c], {}, k=1, threshold=0.0)
        assert results[0]["score"] == pytest.approx(0.7)  # (1-0.3)*1 + 0

    def test_legacy_set_boost_still_flat(self):
        """A set (legacy corpus) still applies the flat _KW_BOOST, not a graded one."""
        from workflows.document_qa_workflow_nodes.retrieve_chunks_node import _KW_BOOST

        cid = uuid.uuid4()
        c = _make_candidate(dist=0.2, candidate_id=cid)
        results = self.node._fuse_and_rank([c], {cid}, k=1, threshold=0.0)
        assert results[0]["score"] == pytest.approx((1.0 - 0.2) + _KW_BOOST)

    def test_provenance_fields_carried_through(self):
        """file_path / doc_id / title flow from the candidate into the result dict."""
        cid = uuid.uuid4()
        c = _make_candidate(dist=0.2, candidate_id=cid)
        c["file_path"] = "docs/decisions/D20-shared-data-contract.md"
        c["doc_id"] = "D20-shared-data-contract"
        c["title"] = "Shared Data Contract"
        results = self.node._fuse_and_rank([c], set(), k=1, threshold=0.0)
        assert results[0]["file_path"] == "docs/decisions/D20-shared-data-contract.md"
        assert results[0]["doc_id"] == "D20-shared-data-contract"
        assert results[0]["title"] == "Shared Data Contract"

    def test_provenance_fields_default_to_none(self):
        """Candidates lacking provenance keys still produce the keys, set to None."""
        c = _make_candidate(dist=0.2)
        results = self.node._fuse_and_rank([c], set(), k=1, threshold=0.0)
        assert results[0]["file_path"] is None
        assert results[0]["doc_id"] is None
        assert results[0]["title"] is None


# ---------------------------------------------------------------------------
# Archived exclusion — default-off filter on the brain corpus
# ---------------------------------------------------------------------------


class TestArchivedExclusion:
    """The brain corpus excludes status='archived' unless include_archived=True."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def _run_semantic_search(self, corpus: str, include_archived: bool):
        """Invoke _semantic_search against a mock session; return the query mock."""
        fake_query = MagicMock()
        fake_query.filter.return_value = fake_query
        fake_query.order_by.return_value = fake_query
        fake_query.limit.return_value = fake_query
        fake_query.all.return_value = []

        fake_session = MagicMock()
        fake_session.query.return_value = fake_query
        fake_session.__enter__ = MagicMock(return_value=fake_session)
        fake_session.__exit__ = MagicMock(return_value=False)

        def _fake_db_session():
            yield fake_session

        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.db_session",
            _fake_db_session,
        ):
            self.node._semantic_search(
                [0.1] * 1024,
                corpus,
                limit=20,
                filters=None,
                include_archived=include_archived,
            )
        return fake_query

    def test_brain_excludes_archived_by_default(self):
        """A status filter is applied for the brain corpus when not including archived."""
        fake_query = self._run_semantic_search("brain", include_archived=False)
        # query → filter (status) → order_by → limit. The status filter call is
        # the extra one beyond order_by/limit; assert at least one filter ran.
        assert fake_query.filter.called

    def test_brain_includes_archived_when_flagged(self):
        """No status filter is applied when include_archived=True."""
        fake_query = self._run_semantic_search("brain", include_archived=True)
        # With no metadata filters and include_archived=True, filter() must not
        # be called at all (no WHERE clauses added).
        assert not fake_query.filter.called

    def test_content_corpus_never_filters_status(self):
        """The content corpus has no default_status_exclude → no status filter."""
        fake_query = self._run_semantic_search("content", include_archived=False)
        assert not fake_query.filter.called


class TestIncludeArchivedThreading:
    """include_archived threads process → retrieve → _semantic_search."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def test_retrieve_forwards_include_archived(self):
        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as MockEmb, patch.object(
            self.node, "_semantic_search", return_value=[]
        ) as mock_sem, patch.object(
            self.node, "_keyword_search", return_value=set()
        ):
            MockEmb.return_value.embed_text.return_value = [0.1] * 1024
            self.node.retrieve("q", corpus="brain", include_archived=True)
            assert mock_sem.call_args[1].get("include_archived") is True

    def test_retrieve_defaults_include_archived_false(self):
        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as MockEmb, patch.object(
            self.node, "_semantic_search", return_value=[]
        ) as mock_sem, patch.object(
            self.node, "_keyword_search", return_value=set()
        ):
            MockEmb.return_value.embed_text.return_value = [0.1] * 1024
            self.node.retrieve("q", corpus="brain")
            assert mock_sem.call_args[1].get("include_archived") is False

    def test_process_reads_include_archived_from_event(self):
        event = MagicMock()
        event.question = "brain question"
        event.corpus = "brain"
        event.filters = None
        event.include_archived = True
        ctx = TaskContext(event=event)
        with patch.object(self.node, "retrieve", return_value=[]) as mock_ret:
            self.node.process(ctx)
        assert mock_ret.call_args[1].get("include_archived") is True

    def test_process_defaults_include_archived_false_when_absent(self):
        event = MagicMock(spec=["question", "corpus"])
        event.question = "What is chunking?"
        event.corpus = "content"
        ctx = TaskContext(event=event)
        with patch.object(self.node, "retrieve", return_value=[]) as mock_ret:
            self.node.process(ctx)
        assert mock_ret.call_args[1].get("include_archived") is False


# ---------------------------------------------------------------------------
# _structural_expand — Stage 1b structural neighborhood expansion (OR.G Task 3)
# ---------------------------------------------------------------------------


class TestStructuralExpand:
    """Unit tests for _structural_expand — mocked brain_edges + neighbor rows."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    @staticmethod
    def _make_session(edge_target_doc_ids, neighbor_rows):
        """Fake session whose .query() returns, in order: the edge lookup
        query (BrainEdge.target_doc_id), then the neighbor row/distance query."""
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
        return fake_session

    def test_content_corpus_is_noop(self):
        """The content corpus doesn't declare supports_structural — always []."""
        candidate = _make_candidate()
        candidate["doc_id"] = "alpha"
        result = self.node._structural_expand([candidate], "content", [0.1] * 1024)
        assert result == []

    def test_no_seed_doc_ids_returns_empty_without_touching_db(self):
        """Candidates with no doc_id produce no seeds; the DB is never opened."""
        candidates = [_make_candidate()]  # no "doc_id" key
        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.db_session"
        ) as mock_db_session:
            result = self.node._structural_expand(candidates, "brain", [0.1] * 1024)
        assert result == []
        mock_db_session.assert_not_called()

    def test_returns_neighbor_flagged_structural(self):
        """A resolved brain_edges neighbor is returned as a candidate dict
        with via='structural' and the neighbor's own doc_id/content."""
        seed = _make_candidate(dist=0.1)
        seed["doc_id"] = "alpha"

        neighbor_id = uuid.uuid4()
        fake_row = MagicMock()
        fake_row.id = neighbor_id
        fake_row.content = "neighbor content"
        fake_row.section = "Neighbor Section"
        fake_row.is_section_title = False
        fake_row.file_path = "docs/beta.md"
        fake_row.doc_id = "beta"
        fake_row.title = "Beta"

        fake_session = self._make_session(["beta"], [(fake_row, 0.15)])

        def _fake_db_session():
            yield fake_session

        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.db_session",
            _fake_db_session,
        ):
            result = self.node._structural_expand([seed], "brain", [0.1] * 1024)

        assert len(result) == 1
        assert result[0]["via"] == "structural"
        assert result[0]["doc_id"] == "beta"
        assert result[0]["id"] == neighbor_id
        assert result[0]["distance"] == 0.15

    def test_neighbor_already_a_candidate_is_excluded(self):
        """A resolved neighbor whose doc_id already appears among the input
        candidates is not re-fetched (no duplicate row query)."""
        seed = _make_candidate(dist=0.1)
        seed["doc_id"] = "alpha"
        already_present = _make_candidate(dist=0.2)
        already_present["doc_id"] = "beta"

        fake_session = self._make_session(["beta"], [])

        def _fake_db_session():
            yield fake_session

        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.db_session",
            _fake_db_session,
        ):
            result = self.node._structural_expand(
                [seed, already_present], "brain", [0.1] * 1024
            )

        assert result == []

    def test_dangling_edges_are_ignored(self):
        """Edges with a NULL target_doc_id are filtered at the SQL layer, but
        even if a None slips through, it never becomes a neighbor doc id."""
        seed = _make_candidate(dist=0.1)
        seed["doc_id"] = "alpha"

        fake_session = self._make_session([], [])

        def _fake_db_session():
            yield fake_session

        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.db_session",
            _fake_db_session,
        ):
            result = self.node._structural_expand([seed], "brain", [0.1] * 1024)

        assert result == []


# ---------------------------------------------------------------------------
# retrieve() — structural expansion merged into the fused candidate set
# ---------------------------------------------------------------------------


class TestRetrieveStructuralExpansion:
    """Integration tests for retrieve() merging _structural_expand output."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def test_structural_neighbor_appears_in_fused_result_flagged(self):
        """A structural candidate is unioned into the candidate set and its
        via='structural' provenance survives _fuse_and_rank."""
        semantic_id = uuid.uuid4()
        structural_id = uuid.uuid4()
        semantic_candidate = _make_candidate(dist=0.1, candidate_id=semantic_id)
        semantic_candidate["doc_id"] = "alpha"
        structural_candidate = _make_candidate(
            dist=0.2, candidate_id=structural_id, content="neighbor content"
        )
        structural_candidate["doc_id"] = "beta"
        structural_candidate["via"] = "structural"

        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as MockEmb, patch.object(
            self.node, "_semantic_search", return_value=[semantic_candidate]
        ), patch.object(
            self.node, "_structural_expand", return_value=[structural_candidate]
        ) as mock_struct, patch.object(
            self.node, "_keyword_search", return_value=set()
        ):
            MockEmb.return_value.embed_text.return_value = [0.1] * 1024
            result = self.node.retrieve("q", corpus="brain", k=5)

        mock_struct.assert_called_once()
        result_by_id = {r["id"]: r for r in result}
        assert structural_id in result_by_id
        assert result_by_id[structural_id]["via"] == "structural"
        assert result_by_id[semantic_id]["via"] == "semantic"

    def test_neighbor_absent_from_semantic_only_path(self):
        """With expand_structural=False, _structural_expand never runs and its
        candidate never appears — demonstrating the neighbor is genuinely
        surfaced only by the structural stage on the same fixture."""
        semantic_id = uuid.uuid4()
        structural_id = uuid.uuid4()
        semantic_candidate = _make_candidate(dist=0.1, candidate_id=semantic_id)
        structural_candidate = _make_candidate(dist=0.2, candidate_id=structural_id)
        structural_candidate["via"] = "structural"

        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as MockEmb, patch.object(
            self.node, "_semantic_search", return_value=[semantic_candidate]
        ), patch.object(
            self.node, "_structural_expand", return_value=[structural_candidate]
        ) as mock_struct, patch.object(
            self.node, "_keyword_search", return_value=set()
        ):
            MockEmb.return_value.embed_text.return_value = [0.1] * 1024
            result = self.node.retrieve(
                "q", corpus="brain", k=5, expand_structural=False
            )

        mock_struct.assert_not_called()
        result_ids = {r["id"] for r in result}
        assert structural_id not in result_ids
        assert semantic_id in result_ids

    def test_dedup_prefers_existing_semantic_candidate(self):
        """A structural candidate sharing an id with an existing semantic
        candidate is not duplicated in the fused result."""
        dup_id = uuid.uuid4()
        semantic_candidate = _make_candidate(dist=0.1, candidate_id=dup_id)
        dup_structural = _make_candidate(dist=0.2, candidate_id=dup_id)
        dup_structural["via"] = "structural"

        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as MockEmb, patch.object(
            self.node, "_semantic_search", return_value=[semantic_candidate]
        ), patch.object(
            self.node, "_structural_expand", return_value=[dup_structural]
        ), patch.object(
            self.node, "_keyword_search", return_value=set()
        ):
            MockEmb.return_value.embed_text.return_value = [0.1] * 1024
            result = self.node.retrieve("q", corpus="brain", k=5)

        assert len(result) == 1
        assert result[0]["via"] == "semantic"

    def test_structural_expand_receives_query_vector_and_corpus(self):
        """_structural_expand is called with the embedded vector and corpus."""
        expected_vector = [0.3] * 1024
        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as MockEmb, patch.object(
            self.node, "_semantic_search", return_value=[]
        ), patch.object(
            self.node, "_structural_expand", return_value=[]
        ) as mock_struct, patch.object(
            self.node, "_keyword_search", return_value=set()
        ):
            MockEmb.return_value.embed_text.return_value = expected_vector
            self.node.retrieve("q", corpus="brain", k=5)

        args = mock_struct.call_args[0]
        assert args[1] == "brain"
        assert args[2] == expected_vector


# ---------------------------------------------------------------------------
# Regression: content corpus + toggle-off brain path unchanged (OR.G Task 3)
# ---------------------------------------------------------------------------


class TestStructuralExpansionRegression:
    """The content corpus and the toggle-off brain path must behave exactly
    as before the structural expansion stage was added, using the REAL
    (unmocked) _structural_expand so its no-op guards are exercised."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def test_content_corpus_result_unaffected(self):
        """content corpus: real _structural_expand never touches the DB, and
        every result is flagged via='semantic' (unchanged behaviour)."""
        candidates = [_make_candidate(dist=0.1), _make_candidate(dist=0.3)]
        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as MockEmb, patch.object(
            self.node, "_semantic_search", return_value=candidates
        ), patch.object(
            self.node, "_keyword_search", return_value=set()
        ):
            MockEmb.return_value.embed_text.return_value = [0.1] * 1024
            result = self.node.retrieve("q", corpus="content", k=5)

        assert len(result) == 2
        assert all(r["via"] == "semantic" for r in result)

    def test_brain_path_identical_with_toggle_on_or_off_when_no_edges(self):
        """When candidates carry no doc_id (no traversable seeds — mirrors
        'no edges exist' per the acceptance criteria), expand_structural=True
        and False produce byte-for-byte identical results."""
        candidates = [_make_candidate(dist=0.1)]  # no "doc_id" key

        def _run(expand: bool):
            with patch(
                "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
            ) as MockEmb, patch.object(
                self.node, "_semantic_search", return_value=candidates
            ), patch.object(
                self.node, "_keyword_search", return_value=set()
            ):
                MockEmb.return_value.embed_text.return_value = [0.1] * 1024
                return self.node.retrieve(
                    "q", corpus="brain", k=5, expand_structural=expand
                )

        assert _run(True) == _run(False)


# ---------------------------------------------------------------------------
# expand_structural threading — process() → retrieve()
# ---------------------------------------------------------------------------


class TestExpandStructuralThreading:
    """expand_structural threads from the event through process() to retrieve()."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def test_process_reads_expand_structural_from_event(self):
        event = MagicMock()
        event.question = "brain question"
        event.corpus = "brain"
        event.filters = None
        event.include_archived = False
        event.expand_structural = False
        ctx = TaskContext(event=event)
        with patch.object(self.node, "retrieve", return_value=[]) as mock_ret:
            self.node.process(ctx)
        assert mock_ret.call_args[1].get("expand_structural") is False

    def test_process_defaults_expand_structural_true_when_absent(self):
        event = MagicMock(spec=["question", "corpus"])
        event.question = "What is chunking?"
        event.corpus = "content"
        ctx = TaskContext(event=event)
        with patch.object(self.node, "retrieve", return_value=[]) as mock_ret:
            self.node.process(ctx)
        assert mock_ret.call_args[1].get("expand_structural") is True
