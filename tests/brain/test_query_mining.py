"""Tests for app/brain/query_mining.py — OR.2.E task 3.

Covers the SQL-only aggregation contract (`GenericRepository.get_all()` is
never called), the four combined filters (golden-set exclusion, `surface ==
"eval"` exclusion, frequency floor, `--include-singletons` override), the
three candidate classes each produced from a seeded fixture, the
`confidently-wrong-suspect` heuristic caveat, the never-opens-the-golden-
set-for-writing guarantee, and the empty-log no-raise contract.
"""

import uuid
from datetime import datetime

import pytest
from brain import query_mining
from database.retrieval_query import RetrievalQuery
from database.session import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def session():
    """Fresh in-memory SQLite session exercising only `retrieval_queries`."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[RetrievalQuery.__table__])
    factory = sessionmaker(bind=engine)
    session_ = factory()
    yield session_
    session_.close()
    engine.dispose()


def _row(  # pylint: disable=too-many-arguments
    session_,
    query,
    *,
    surface="cli",
    retrieval_confidence=0.9,
    abstained=False,
    top_scores=None,
    via_mix=None,
    top_doc_ids=None,
    created_at=None,
    result_count=3,
):
    row = RetrievalQuery(
        id=uuid.uuid4(),
        query=query,
        surface=surface,
        hybrid=True,
        result_count=result_count,
        retrieval_confidence=retrieval_confidence,
        abstained=abstained,
        top_scores=top_scores,
        via_mix=via_mix or {"semantic": 2, "keyword": 1},
        top_doc_ids=top_doc_ids or ["doc-1", "doc-2"],
        created_at=created_at or datetime.now(),
    )
    session_.add(row)
    session_.commit()
    return row


# ---------------------------------------------------------------------------
# SQL-only aggregation
# ---------------------------------------------------------------------------


class TestSqlOnlyAggregation:
    def test_get_all_is_never_called(self, session, monkeypatch):
        from database.repository import GenericRepository

        def _boom(self):  # pylint: disable=unused-argument
            raise AssertionError("get_all() must never be called by query_mining")

        monkeypatch.setattr(GenericRepository, "get_all", _boom)

        _row(session, "what changed", created_at=datetime.now())
        _row(session, "what changed", created_at=datetime.now())

        # Must not raise — proves get_all() was never reached.
        query_mining.mine_candidates(session, golden_set_queries=set())

    def test_empty_log_yields_empty_list_without_raising(self, session):
        result = query_mining.mine_candidates(session, golden_set_queries=set())
        assert result == []


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


class TestFilters:
    def test_golden_set_queries_never_survive(self, session):
        _row(session, "in the golden set", abstained=True)
        _row(session, "in the golden set", abstained=True)
        _row(session, "not in the golden set", abstained=True)
        _row(session, "not in the golden set", abstained=True)

        result = query_mining.mine_candidates(
            session, golden_set_queries={"in the golden set"}
        )
        queries = {c.query for c in result}
        assert "in the golden set" not in queries
        assert "not in the golden set" in queries

    def test_eval_surface_rows_never_considered(self, session):
        _row(session, "harness only", surface="eval", abstained=True)
        _row(session, "harness only", surface="eval", abstained=True)

        result = query_mining.mine_candidates(session, golden_set_queries=set())
        assert result == []

    def test_singletons_excluded_by_default(self, session):
        _row(session, "seen once", abstained=True)

        result = query_mining.mine_candidates(session, golden_set_queries=set())
        assert result == []

    def test_include_singletons_override(self, session):
        _row(session, "seen once", abstained=True)

        result = query_mining.mine_candidates(
            session, golden_set_queries=set(), include_singletons=True
        )
        assert [c.query for c in result] == ["seen once"]

    def test_min_count_configurable(self, session):
        for _ in range(3):
            _row(session, "seen thrice", abstained=True)

        assert query_mining.mine_candidates(
            session, golden_set_queries=set(), min_count=4
        ) == []
        result = query_mining.mine_candidates(session, golden_set_queries=set(), min_count=3)
        assert [c.query for c in result] == ["seen thrice"]

    def test_all_four_filters_applied_together(self, session):
        # Golden-set query, logged only via eval, seen once — every filter
        # would independently exclude it; assert it is excluded once.
        _row(session, "golden", surface="eval", abstained=True)

        result = query_mining.mine_candidates(session, golden_set_queries={"golden"})
        assert result == []


# ---------------------------------------------------------------------------
# Candidate classes
# ---------------------------------------------------------------------------


class TestCandidateClasses:
    def test_abstained_class(self, session):
        _row(session, "genuinely unanswerable", abstained=True, retrieval_confidence=0.1)
        _row(session, "genuinely unanswerable", abstained=True, retrieval_confidence=0.1)

        result = query_mining.mine_candidates(session, golden_set_queries=set())
        assert len(result) == 1
        assert result[0].class_ == query_mining.CLASS_ABSTAINED
        assert "human decides" in result[0].rationale

    def test_low_confidence_answered_class(self, session):
        # A cluster of high-confidence rows plus one clear low-confidence
        # outlier, all non-abstained — the outlier should land in the
        # bottom quartile and be classified low-confidence-answered.
        for i in range(4):
            _row(session, f"high conf {i}", retrieval_confidence=0.95, abstained=False)
            _row(session, f"high conf {i}", retrieval_confidence=0.95, abstained=False)
        _row(session, "low conf outlier", retrieval_confidence=0.62, abstained=False)
        _row(session, "low conf outlier", retrieval_confidence=0.62, abstained=False)

        result = query_mining.mine_candidates(session, golden_set_queries=set())
        by_query = {c.query: c for c in result}
        assert by_query["low conf outlier"].class_ == query_mining.CLASS_LOW_CONFIDENCE_ANSWERED

    def test_confidently_wrong_suspect_class_from_score_gap(self, session):
        # Spread of filler confidences establishes a bottom-quartile boundary
        # well below the target's confidence, so the target is scored as
        # "high confidence, not the bottom quartile" rather than
        # low-confidence-answered — isolating the score-gap signal.
        filler_confidences = [0.40, 0.50, 0.60, 0.70]
        for i, confidence in enumerate(filler_confidences):
            _row(
                session,
                f"clear winner {i}",
                retrieval_confidence=confidence,
                abstained=False,
                top_scores=[0.95, 0.40, 0.30],
            )
            _row(
                session,
                f"clear winner {i}",
                retrieval_confidence=confidence,
                abstained=False,
                top_scores=[0.95, 0.40, 0.30],
            )
        _row(
            session,
            "narrow margin",
            retrieval_confidence=0.95,
            abstained=False,
            top_scores=[0.95, 0.94, 0.10],
        )
        _row(
            session,
            "narrow margin",
            retrieval_confidence=0.95,
            abstained=False,
            top_scores=[0.95, 0.94, 0.10],
        )

        result = query_mining.mine_candidates(session, golden_set_queries=set())
        by_query = {c.query: c for c in result}
        assert (
            by_query["narrow margin"].class_ == query_mining.CLASS_CONFIDENTLY_WRONG_SUSPECT
        )
        assert query_mining.CONFIDENTLY_WRONG_SUSPECT_CAVEAT in by_query["narrow margin"].rationale

    def test_confidently_wrong_suspect_class_from_keyword_dominance(self, session):
        filler_confidences = [0.40, 0.50, 0.60, 0.70]
        for i, confidence in enumerate(filler_confidences):
            _row(
                session,
                f"semantic win {i}",
                retrieval_confidence=confidence,
                abstained=False,
                top_scores=[0.95, 0.10],
                via_mix={"semantic": 4, "keyword": 0},
            )
            _row(
                session,
                f"semantic win {i}",
                retrieval_confidence=confidence,
                abstained=False,
                top_scores=[0.95, 0.10],
                via_mix={"semantic": 4, "keyword": 0},
            )
        _row(
            session,
            "keyword dominated",
            retrieval_confidence=0.95,
            abstained=False,
            top_scores=[0.95, 0.10],
            via_mix={"semantic": 0, "keyword": 4},
        )
        _row(
            session,
            "keyword dominated",
            retrieval_confidence=0.95,
            abstained=False,
            top_scores=[0.95, 0.10],
            via_mix={"semantic": 0, "keyword": 4},
        )

        result = query_mining.mine_candidates(session, golden_set_queries=set())
        by_query = {c.query: c for c in result}
        assert (
            by_query["keyword dominated"].class_
            == query_mining.CLASS_CONFIDENTLY_WRONG_SUSPECT
        )

    def test_uncategorized_query_is_excluded(self, session):
        # Filler establishes a low bottom-quartile boundary; the target has
        # high confidence, a wide score gap, and no keyword dominance — it
        # should not fit any of the three classes.
        filler_confidences = [0.40, 0.50, 0.60, 0.70]
        for i, confidence in enumerate(filler_confidences):
            _row(
                session,
                f"filler {i}",
                retrieval_confidence=confidence,
                abstained=False,
                top_scores=[0.95, 0.40],
                via_mix={"semantic": 3, "keyword": 0},
            )
            _row(
                session,
                f"filler {i}",
                retrieval_confidence=confidence,
                abstained=False,
                top_scores=[0.95, 0.40],
                via_mix={"semantic": 3, "keyword": 0},
            )
        for _ in range(3):
            _row(
                session,
                "boring but frequent",
                retrieval_confidence=0.95,
                abstained=False,
                top_scores=[0.95, 0.40],
                via_mix={"semantic": 3, "keyword": 0},
            )

        result = query_mining.mine_candidates(session, golden_set_queries=set())
        queries = {c.query for c in result}
        assert "boring but frequent" not in queries


# ---------------------------------------------------------------------------
# Never writes the golden set
# ---------------------------------------------------------------------------


class TestNeverWritesGoldenSet:
    def test_default_golden_set_load_never_opens_for_writing(self, session, monkeypatch, tmp_path):
        golden_set_path = tmp_path / "golden.yaml"
        golden_set_path.write_text(
            "cases:\n"
            "  - id: authored-01\n"
            "    query: 'already in the set'\n"
            "    expect_docs: ['some/doc.md']\n"
            "    expect_abstain: false\n"
            "    source: authored\n"
            "    category: identifier\n",
            encoding="utf-8",
        )

        real_open = open

        def _guarded_open(file, mode="r", *args, **kwargs):  # noqa: A002  # pylint: disable=keyword-arg-before-vararg
            if "w" in mode or "a" in mode or "+" in mode:
                raise AssertionError(f"golden set opened for writing: mode={mode!r}")
            return real_open(file, mode, *args, **kwargs)

        monkeypatch.setattr("builtins.open", _guarded_open)

        _row(session, "already in the set", abstained=True)
        _row(session, "already in the set", abstained=True)
        _row(session, "brand new query", abstained=True)
        _row(session, "brand new query", abstained=True)

        result = query_mining.mine_candidates(session, golden_set_path=golden_set_path)
        queries = {c.query for c in result}
        assert "already in the set" not in queries
        assert "brand new query" in queries


# ---------------------------------------------------------------------------
# Module docstring guards
# ---------------------------------------------------------------------------


class TestModuleDocstring:
    def test_docstring_explains_read_time_vs_rollup(self):
        doc = query_mining.__doc__
        assert "read time" in doc.lower() or "read-time" in doc.lower()
        assert "rollup" in doc.lower()

    def test_docstring_labels_third_class_a_heuristic(self):
        doc = query_mining.__doc__
        assert "heuristic" in doc.lower()
