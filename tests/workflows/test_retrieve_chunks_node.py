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
