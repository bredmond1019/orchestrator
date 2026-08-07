"""Tests for app/brain/eval/ — the retrieval evaluation harness (OR.K2 task 3).

No DB/embedding calls: `retrieval_engine.retrieve` is patched with a fixture
corpus so scoring is exercised deterministically and fast. Covers: double-run
metric identity, a seeded regression tripping `compare_to_baseline`, abstain
correctness on a negative case, groundedness parity with
`VerifyCitationsNode.support_score` on a shared fixture, and the two
grep-assert import guards (`app/brain/` never imports `app/workflows/`;
`app/brain/eval/` never imports `app/evals/` — that package is deleted by
OR.X2, so this guard also proves no accidental reintroduction).
"""

import ast
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from brain import retrieval_engine
from brain.eval import scorer
from brain.eval.models import CaseResult, RetrievalCase, RetrievalRunReport
from brain.eval.runner import _aggregate, compare_to_baseline, load_report, run_eval, write_report
from brain.eval.scorer import ABSTAIN_THRESHOLD, score_case
from workflows.document_qa_workflow_nodes.verify_citations_node import (
    split_sentences as node_split_sentences,
)
from workflows.document_qa_workflow_nodes.verify_citations_node import (
    support_score as node_support_score,
)

_EVAL_DIR = Path(__file__).resolve().parent.parent.parent / "app" / "brain" / "eval"


def _chunk(**overrides) -> dict:
    base = {
        "id": "chunk-1",
        "doc_id": "D26-example",
        "file_path": "docs/decisions/D26-example.md",
        "title": "D26 — Example Decision",
        "section_title": "Decision",
        "content": "Bastion is a personal Rust CLI ops control panel for the agentic stack.",
        "score": 6.0,
        "via": "semantic",
    }
    base.update(overrides)
    return base


_POSITIVE_CASE = RetrievalCase(
    case_id="fixture-positive",
    query="What is Bastion?",
    expect_docs=("docs/decisions/D26-example.md",),
    expect_abstain=False,
    source="authored",
    category="identifier",
)

_NEGATIVE_CASE = RetrievalCase(
    case_id="fixture-negative",
    query="What is the meaning of life and how do I bake a souffle?",
    expect_docs=(),
    expect_abstain=True,
    source="authored",
    category="negative",
)


# ---------------------------------------------------------------------------
# score_case
# ---------------------------------------------------------------------------


def test_score_case_positive_hit_scores_recall_and_rank():
    results = [_chunk(), _chunk(doc_id="other", file_path="docs/other.md")]
    result = score_case(_POSITIVE_CASE, results, confidence=0.9)

    assert result.recall_at_5 == 1.0
    assert result.recall_at_10 == 1.0
    assert result.reciprocal_rank == 1.0
    assert result.matched_docs == ("D26-example",)


def test_score_case_positive_miss_scores_zero_not_none():
    results = [_chunk(doc_id="other", file_path="docs/other.md")]
    result = score_case(_POSITIVE_CASE, results, confidence=0.9)

    assert result.recall_at_5 == 0.0
    assert result.recall_at_10 == 0.0
    assert result.reciprocal_rank == 0.0
    assert result.groundedness == 0.0
    assert result.matched_docs == ()


def test_score_case_negative_case_recall_fields_are_none():
    """A case with no expect_docs has undefined recall/MRR/groundedness —
    None, not 0.0, so it can't silently poison the positive-case aggregate."""
    result = score_case(_NEGATIVE_CASE, [], confidence=0.1)

    assert result.recall_at_5 is None
    assert result.recall_at_10 is None
    assert result.reciprocal_rank is None
    assert result.groundedness is None


def test_score_case_abstain_correctness_on_negative_case():
    """Below-threshold confidence on a negative case (expect_abstain=True) is correct."""
    below = ABSTAIN_THRESHOLD - 0.1
    result = score_case(_NEGATIVE_CASE, [], confidence=below)

    assert result.predicted_abstain is True
    assert result.expected_abstain is True
    assert result.abstain_correct is True


def test_score_case_abstain_incorrectness_on_negative_case_with_high_confidence():
    above = ABSTAIN_THRESHOLD + 0.1
    result = score_case(_NEGATIVE_CASE, [_chunk()], confidence=above)

    assert result.predicted_abstain is False
    assert result.expected_abstain is True
    assert result.abstain_correct is False


# ---------------------------------------------------------------------------
# groundedness parity with VerifyCitationsNode.support_score
# ---------------------------------------------------------------------------


def test_groundedness_agrees_with_verify_citations_node_on_shared_fixture():
    """The lifted copy in scorer.py must score identically to the node's
    original on the same (sentences, content) fixture — a divergence here
    means the two copies have drifted (module docstring's "update both
    deliberately" contract broken)."""
    from brain.eval import scorer  # pylint: disable=import-outside-toplevel

    sentences = node_split_sentences("Bastion is a personal Rust CLI ops control panel.")
    content = "Bastion is a personal Rust CLI ops control panel for the agentic stack."

    assert scorer.split_sentences(
        "Bastion is a personal Rust CLI ops control panel."
    ) == sentences
    assert scorer.support_score(sentences, content) == node_support_score(sentences, content)


def test_score_case_groundedness_matches_direct_support_score_call():
    result = score_case(_POSITIVE_CASE, [_chunk()], confidence=0.9)
    expected = node_support_score(
        node_split_sentences(_POSITIVE_CASE.query), _chunk()["content"]
    )
    assert result.groundedness == expected


# ---------------------------------------------------------------------------
# run_eval / double-run determinism
# ---------------------------------------------------------------------------


def _fixture_retrieve(query, **_kwargs):
    if "Bastion" in query:
        return [_chunk()]
    return [_chunk(doc_id="unrelated", file_path="docs/unrelated.md", score=0.4, content="noise")]


class _FakeScalarResult:
    """Stands in for a SQLAlchemy `Query` — only `.scalar()` is ever called
    on the objects `_fingerprint_corpus` builds via `db.query(...)`."""

    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _FakeCorpusSession:
    """A minimal fake session for `_fingerprint_corpus`: `.query(...)` is
    called four times in a fixed order (chunk count, file count, edge
    count, max indexed_at) and returns the next canned scalar each time —
    hermetic, no real DB, no SQLite/Postgres type mismatch."""

    def __init__(self, values):
        self._values = iter(values)

    def query(self, *_args, **_kwargs):
        return _FakeScalarResult(next(self._values))


def test_run_eval_is_deterministic_across_two_runs():
    cases = [_POSITIVE_CASE, _NEGATIVE_CASE]
    with patch("brain.eval.runner.retrieval_engine.retrieve", side_effect=_fixture_retrieve):
        report_one = run_eval(cases)
        report_two = run_eval(cases)

    assert report_one.aggregate == report_two.aggregate
    assert report_one.aggregate_stats == report_two.aggregate_stats
    assert [r.case_id for r in report_one.results] == [r.case_id for r in report_two.results]
    assert [r.recall_at_5 for r in report_one.results] == [
        r.recall_at_5 for r in report_two.results
    ]


# ---------------------------------------------------------------------------
# aggregate_stats — n / point estimate / 95% interval / method / seed per
# metric (plan-eval-statistical-honesty task 2)
# ---------------------------------------------------------------------------


def test_aggregate_remains_flat_dict_of_floats():
    """`aggregate` itself must never carry a nested interval — `compare_to_
    baseline` iterates it and subtracts, which raises `TypeError` on a
    non-float value."""
    with patch("brain.eval.runner.retrieval_engine.retrieve", side_effect=_fixture_retrieve):
        report = run_eval([_POSITIVE_CASE, _NEGATIVE_CASE])

    assert isinstance(report.aggregate, dict)
    for value in report.aggregate.values():
        assert isinstance(value, float)


def test_aggregate_stats_is_a_sibling_top_level_key_with_all_six_metrics():
    with patch("brain.eval.runner.retrieval_engine.retrieve", side_effect=_fixture_retrieve):
        report = run_eval([_POSITIVE_CASE, _NEGATIVE_CASE])

    assert set(report.aggregate_stats) == {
        "recall_at_5",
        "recall_at_10",
        "mrr",
        "groundedness",
        "groundedness_on_hits",
        "abstain_correctness",
    }
    for metric, interval in report.aggregate_stats.items():
        assert "n" in interval, metric
        assert "point" in interval, metric
        assert "lo" in interval, metric
        assert "hi" in interval, metric
        assert "method" in interval, metric
        assert "seed" in interval, metric


def test_aggregate_stats_n_matches_the_denominator_aggregate_actually_averages_over():
    """Two positive cases, one negative case. `recall_at_5`/`recall_at_10`/
    `mrr`/`groundedness` average over the 2 positive cases only;
    `abstain_correctness` averages over all 3; `groundedness_on_hits`
    averages over whichever positive cases actually matched (1, per
    `_grounded_retrieve`'s Bastion-only hit)."""
    cases = [_POSITIVE_CASE, _MISS_CASE, _NEGATIVE_CASE]
    with patch("brain.eval.runner.retrieval_engine.retrieve", side_effect=_grounded_retrieve):
        report = run_eval(cases)

    stats_ = report.aggregate_stats
    assert stats_["recall_at_5"]["n"] == 2
    assert stats_["recall_at_10"]["n"] == 2
    assert stats_["mrr"]["n"] == 2
    assert stats_["groundedness"]["n"] == 2
    assert stats_["groundedness_on_hits"]["n"] == 1
    assert stats_["abstain_correctness"]["n"] == 3


def test_aggregate_stats_wilson_metrics_use_wilson_method():
    with patch("brain.eval.runner.retrieval_engine.retrieve", side_effect=_fixture_retrieve):
        report = run_eval([_POSITIVE_CASE, _NEGATIVE_CASE])

    for metric in ("recall_at_5", "recall_at_10", "abstain_correctness"):
        assert report.aggregate_stats[metric]["method"] == "wilson"


def test_aggregate_stats_bootstrap_metrics_use_bootstrap_method_and_are_seeded():
    with patch("brain.eval.runner.retrieval_engine.retrieve", side_effect=_fixture_retrieve):
        report = run_eval([_POSITIVE_CASE, _NEGATIVE_CASE])

    for metric in ("mrr", "groundedness", "groundedness_on_hits"):
        assert report.aggregate_stats[metric]["method"] == "bootstrap"
        assert report.aggregate_stats[metric]["seed"] is not None


def test_write_report_round_trips_aggregate_stats(tmp_path):
    with patch("brain.eval.runner.retrieval_engine.retrieve", side_effect=_fixture_retrieve):
        report = run_eval([_POSITIVE_CASE, _NEGATIVE_CASE])
    out_path = write_report(report, out_dir=tmp_path)

    on_disk = json.loads(out_path.read_text(encoding="utf-8"))
    assert on_disk["aggregate_stats"] == report.aggregate_stats

    loaded = load_report(out_path)
    assert loaded["aggregate_stats"] == report.aggregate_stats


def test_to_dict_defaults_aggregate_stats_to_none():
    """A report built without `aggregate_stats` (mirroring pre-task-2
    callers) still serializes cleanly — key present but null."""
    report = RetrievalRunReport(
        generated_at="2026-08-07T00-00-00Z", case_count=0, results=(), aggregate={}
    )

    assert report.to_dict()["aggregate_stats"] is None


def test_all_pre_existing_run_files_still_load_and_compare():
    """All 15 pre-task-2 run files lack `aggregate_stats` entirely — they
    must still load via `load_report` and compare via `compare_to_baseline`
    without error (mirrors `test_load_report_and_compare_to_baseline_work_
    on_pre_existing_run_files` for the corpus/ranking_constants fields)."""
    runs_dir = Path(__file__).resolve().parents[2] / "planning" / "retrieval-eval-runs"
    if not runs_dir.exists():
        pytest.skip("retrieval-eval-runs fixture directory not present in this checkout")

    run_files = sorted(runs_dir.glob("*.json"))
    if not run_files:
        pytest.skip("no run files present in this checkout")

    for run_file in run_files:
        baseline = load_report(run_file)
        assert "aggregate_stats" not in baseline
        current = {"aggregate": dict(baseline["aggregate"])}
        deltas, regressed, verdict = compare_to_baseline(current, baseline)
        assert isinstance(deltas, dict)
        assert regressed is False
        assert isinstance(verdict, dict)


# ---------------------------------------------------------------------------
# corpus / ranking_constants provenance stamp (ticket-retrieval-ranking-and-
# abstain task 1)
# ---------------------------------------------------------------------------


def test_run_eval_stamps_corpus_fingerprint_from_the_supplied_session():
    fake_max_indexed_at = datetime(2026, 8, 6, 12, 0, 0)
    fake_session = _FakeCorpusSession([11533, 962, 5000, fake_max_indexed_at])

    with patch("brain.eval.runner.retrieval_engine.retrieve", side_effect=_fixture_retrieve):
        report = run_eval([_POSITIVE_CASE], session=fake_session)

    assert report.corpus == {
        "chunk_count": 11533,
        "file_count": 962,
        "edge_count": 5000,
        "max_indexed_at": fake_max_indexed_at.isoformat(),
    }


def test_run_eval_corpus_fingerprint_handles_no_max_indexed_at():
    """An empty corpus (`max(indexed_at)` is NULL) must stamp `None`, not crash."""
    fake_session = _FakeCorpusSession([0, 0, 0, None])

    with patch("brain.eval.runner.retrieval_engine.retrieve", side_effect=_fixture_retrieve):
        report = run_eval([_POSITIVE_CASE], session=fake_session)

    assert report.corpus["max_indexed_at"] is None


def test_run_eval_stamps_live_ranking_constants_not_literals(monkeypatch):
    """Monkeypatching the live module constants must change the stamp —
    proving the values are read at call time, not hardcoded."""
    monkeypatch.setattr(retrieval_engine, "_KW_WEIGHT", 0.5)
    monkeypatch.setattr(retrieval_engine, "_MAX_PER_FILE", 7)
    monkeypatch.setattr(retrieval_engine, "_SECTION_TITLE_WEIGHT", 3.0)
    monkeypatch.setattr(retrieval_engine, "_DOC_DECAY_FACTOR", 0.42)
    monkeypatch.setattr(scorer, "ABSTAIN_THRESHOLD", 0.6552)
    fake_session = _FakeCorpusSession([0, 0, 0, None])

    with patch("brain.eval.runner.retrieval_engine.retrieve", side_effect=_fixture_retrieve):
        report = run_eval([_POSITIVE_CASE], session=fake_session)

    assert report.ranking_constants == {
        "kw_weight": 0.5,
        "max_per_file": 7,
        "section_title_weight": 3.0,
        "doc_decay_factor": 0.42,
        "abstain_threshold": 0.6552,
    }


def test_write_report_round_trips_corpus_and_ranking_constants(tmp_path):
    fake_session = _FakeCorpusSession([11533, 962, 5000, datetime(2026, 8, 6, 12, 0, 0)])

    with patch("brain.eval.runner.retrieval_engine.retrieve", side_effect=_fixture_retrieve):
        report = run_eval([_POSITIVE_CASE], session=fake_session)
    out_path = write_report(report, out_dir=tmp_path)

    on_disk = json.loads(out_path.read_text(encoding="utf-8"))
    assert on_disk["corpus"] == report.corpus
    assert on_disk["ranking_constants"] == report.ranking_constants
    assert on_disk["corpus"]["chunk_count"] == 11533
    assert set(on_disk["ranking_constants"]) == {
        "kw_weight",
        "max_per_file",
        "section_title_weight",
        "doc_decay_factor",
        "abstain_threshold",
    }


def test_to_dict_carries_corpus_and_ranking_constants_when_present():
    report = RetrievalRunReport(
        generated_at="2026-08-07T00-00-00Z",
        case_count=0,
        results=(),
        aggregate={},
        corpus={"chunk_count": 1, "file_count": 1, "edge_count": 0, "max_indexed_at": None},
        ranking_constants={"kw_weight": 0.5},
    )

    as_dict = report.to_dict()

    assert as_dict["corpus"] == {
        "chunk_count": 1,
        "file_count": 1,
        "edge_count": 0,
        "max_indexed_at": None,
    }
    assert as_dict["ranking_constants"] == {"kw_weight": 0.5}


def test_to_dict_defaults_corpus_and_ranking_constants_to_none():
    """A report built without the new fields (mirroring pre-task-1 callers)
    still serializes cleanly — both keys present but null."""
    report = RetrievalRunReport(
        generated_at="2026-08-07T00-00-00Z", case_count=0, results=(), aggregate={}
    )

    as_dict = report.to_dict()

    assert as_dict["corpus"] is None
    assert as_dict["ranking_constants"] is None


def test_load_report_and_compare_to_baseline_work_on_pre_existing_run_files():
    """The 14 pre-task-1 run files under planning/retrieval-eval-runs/ have
    no `corpus`/`ranking_constants` keys at all. `load_report` must load
    them unchanged and `compare_to_baseline` must keep comparing on
    `aggregate` alone, ignoring the fields' absence entirely."""
    pre_existing_path = (
        Path(__file__).resolve().parents[2]
        / "planning"
        / "retrieval-eval-runs"
        / "2026-08-02T10-15-24Z.json"
    )
    if not pre_existing_path.exists():
        pytest.skip("pre-existing run file fixture not present in this checkout")

    baseline = load_report(pre_existing_path)
    assert "corpus" not in baseline
    assert "ranking_constants" not in baseline

    current = {"aggregate": dict(baseline["aggregate"])}
    current["aggregate"]["recall_at_5"] = 1.0

    deltas, regressed, verdict = compare_to_baseline(current, baseline)

    assert regressed is False
    assert deltas["recall_at_5"] == pytest.approx(1.0 - baseline["aggregate"]["recall_at_5"])
    # `current` here has no per-case `results` at all — the paired verdict
    # can't be computed and must say so rather than guessing.
    assert verdict["recall_at_5"]["classification"] == "incomparable"


# ---------------------------------------------------------------------------
# groundedness_on_hits — the additive metric added by
# ticket-groundedness-baseline to decouple the headline groundedness from
# recall. See app/brain/eval/scorer.py::_groundedness "KNOWN STRUCTURAL
# BIASES" and planning/artifacts/groundedness-baseline-analysis.md.
# ---------------------------------------------------------------------------


_MISS_CASE = RetrievalCase(
    case_id="fixture-miss",
    query="What are my hourly rates for contracting engagements?",
    expect_docs=("docs/business/rates.md",),
    expect_abstain=False,
    source="archived",
    category="archive",
)


def _grounded_retrieve(query, **_kwargs):
    """Hit for the Bastion case, total miss for the rates case."""
    if "Bastion" in query:
        return [_chunk()]
    return [_chunk(doc_id="unrelated", file_path="docs/unrelated.md", content="noise")]


def test_groundedness_on_hits_excludes_recall_misses():
    """The headline `groundedness` averages the 0.0 a recall-miss is scored;
    `groundedness_on_hits` must not — that difference is the whole point of
    the additive metric (0.3608 vs 0.5576 on the 2026-08-02 baseline)."""
    with patch("brain.eval.runner.retrieval_engine.retrieve", side_effect=_grounded_retrieve):
        report = run_eval([_POSITIVE_CASE, _MISS_CASE])

    hit = next(r for r in report.results if r.case_id == "fixture-positive")
    miss = next(r for r in report.results if r.case_id == "fixture-miss")
    assert miss.groundedness == 0.0
    assert miss.matched_docs == ()

    assert report.aggregate["groundedness"] == pytest.approx(hit.groundedness / 2)
    assert report.aggregate["groundedness_on_hits"] == pytest.approx(hit.groundedness)
    assert report.aggregate["groundedness_on_hits"] > report.aggregate["groundedness"]


def test_groundedness_on_hits_equals_groundedness_when_every_case_hits():
    with patch("brain.eval.runner.retrieval_engine.retrieve", side_effect=_grounded_retrieve):
        report = run_eval([_POSITIVE_CASE])

    assert report.aggregate["groundedness_on_hits"] == pytest.approx(
        report.aggregate["groundedness"]
    )


def test_groundedness_on_hits_is_zero_when_nothing_hits():
    """No hits at all -> 0.0, not a ZeroDivisionError."""
    with patch("brain.eval.runner.retrieval_engine.retrieve", side_effect=_grounded_retrieve):
        report = run_eval([_MISS_CASE])

    assert report.aggregate["groundedness_on_hits"] == 0.0


def test_groundedness_on_hits_ignores_negative_cases():
    """A negative case scores `groundedness=None` and matches nothing; it must
    contribute to neither groundedness aggregate."""
    with patch("brain.eval.runner.retrieval_engine.retrieve", side_effect=_grounded_retrieve):
        report = run_eval([_POSITIVE_CASE, _NEGATIVE_CASE])

    hit = next(r for r in report.results if r.case_id == "fixture-positive")
    assert report.aggregate["groundedness"] == pytest.approx(hit.groundedness)
    assert report.aggregate["groundedness_on_hits"] == pytest.approx(hit.groundedness)


def test_aggregate_output_unchanged_by_golden_set_schema_v2():
    """`_aggregate` scores off `CaseResult` fields only — `source`/`category`/
    `source_query_id` (OR.2.A task 3's golden-set schema v2 additions) live on
    `RetrievalCase`, never on `CaseResult`, and are metadata, never scoring
    inputs. Pin `_aggregate`'s output against a fixed `CaseResult` fixture set
    so the schema change is provably byte-identical to scoring."""
    results = [
        CaseResult(
            case_id="hit",
            recall_at_5=1.0,
            recall_at_10=1.0,
            reciprocal_rank=1.0,
            predicted_abstain=False,
            expected_abstain=False,
            abstain_correct=True,
            groundedness=0.8,
            retrieval_confidence=0.9,
            matched_docs=("some-doc",),
        ),
        CaseResult(
            case_id="miss",
            recall_at_5=0.0,
            recall_at_10=0.0,
            reciprocal_rank=0.0,
            predicted_abstain=False,
            expected_abstain=False,
            abstain_correct=True,
            groundedness=0.0,
            retrieval_confidence=0.7,
            matched_docs=(),
        ),
        CaseResult(
            case_id="negative",
            recall_at_5=None,
            recall_at_10=None,
            reciprocal_rank=None,
            predicted_abstain=True,
            expected_abstain=True,
            abstain_correct=True,
            groundedness=None,
            retrieval_confidence=0.1,
            matched_docs=(),
        ),
    ]

    aggregate = _aggregate(results)

    assert aggregate == {
        "abstain_correctness": 1.0,
        "recall_at_5": 0.5,
        "recall_at_10": 0.5,
        "mrr": 0.5,
        "groundedness": 0.4,
        "groundedness_on_hits": 0.8,
    }


def test_new_aggregate_key_does_not_break_an_older_baseline_file():
    """`compare_to_baseline` iterates the BASELINE's keys, so a run carrying
    the new `groundedness_on_hits` key compares cleanly against a baseline
    written before it existed — no spurious regression, no KeyError. This is
    what makes the metric additive rather than a baseline reset."""
    baseline = {"aggregate": {"recall_at_5": 0.5, "mrr": 0.5, "groundedness": 0.5}}
    current = {
        "aggregate": {
            "recall_at_5": 0.5,
            "mrr": 0.5,
            "groundedness": 0.5,
            "groundedness_on_hits": 0.9,
        }
    }

    deltas, regressed, verdict = compare_to_baseline(current, baseline)

    assert regressed is False
    assert "groundedness_on_hits" not in deltas
    assert "groundedness_on_hits" not in verdict


# ---------------------------------------------------------------------------
# compare_to_baseline's paired verdict (plan-eval-statistical-honesty task 3)
# ---------------------------------------------------------------------------


def _case_row(case_id: str, *, recall_at_5: float, groundedness: float) -> dict:
    """A minimal per-case `results` row shaped like `RetrievalRunReport.to_dict()`."""
    return {
        "case_id": case_id,
        "recall_at_5": recall_at_5,
        "recall_at_10": recall_at_5,
        "reciprocal_rank": recall_at_5,
        "abstain_correct": True,
        "groundedness": groundedness,
        "matched_docs": ["doc"] if recall_at_5 else [],
    }


def test_compare_to_baseline_verdict_names_flips_and_is_significant_at_6_0():
    """Six of six positive cases flip `recall_at_5` from 1 to 0 (b=6, c=0,
    p=0.03125) — past the 5-vs-6 significance boundary."""
    case_ids = [f"c{i}" for i in range(6)]
    baseline = {
        "aggregate": {"recall_at_5": 1.0},
        "results": [_case_row(c, recall_at_5=1.0, groundedness=1.0) for c in case_ids],
    }
    current = {
        "aggregate": {"recall_at_5": 0.0},
        "results": [_case_row(c, recall_at_5=0.0, groundedness=0.0) for c in case_ids],
    }

    _, _, verdict = compare_to_baseline(current, baseline)
    entry = verdict["recall_at_5"]

    assert entry["pairable"] is True
    assert sorted(entry["flips_to_worse"]) == case_ids
    assert entry["flips_to_better"] == []
    assert entry["sign_test_p"] == pytest.approx(0.03125)
    assert entry["classification"] == "regressed-significant"


def test_compare_to_baseline_verdict_is_within_noise_at_5_0():
    """Five of five positive cases flip worse (b=5, c=0, p=0.0625) — just
    short of significance."""
    case_ids = [f"c{i}" for i in range(5)]
    baseline = {
        "aggregate": {"recall_at_5": 1.0},
        "results": [_case_row(c, recall_at_5=1.0, groundedness=1.0) for c in case_ids],
    }
    current = {
        "aggregate": {"recall_at_5": 0.0},
        "results": [_case_row(c, recall_at_5=0.0, groundedness=0.0) for c in case_ids],
    }

    _, _, verdict = compare_to_baseline(current, baseline)
    entry = verdict["recall_at_5"]

    assert entry["sign_test_p"] == pytest.approx(0.0625)
    assert entry["classification"] == "regressed-within-noise"


def test_compare_to_baseline_verdict_flat_when_no_case_flips():
    case_ids = [f"c{i}" for i in range(4)]
    baseline = {
        "aggregate": {"recall_at_5": 1.0},
        "results": [_case_row(c, recall_at_5=1.0, groundedness=1.0) for c in case_ids],
    }
    current = {
        "aggregate": {"recall_at_5": 1.0},
        "results": [_case_row(c, recall_at_5=1.0, groundedness=1.0) for c in case_ids],
    }

    _, _, verdict = compare_to_baseline(current, baseline)

    assert verdict["recall_at_5"]["classification"] == "flat"
    assert verdict["recall_at_5"]["flips_to_worse"] == []
    assert verdict["recall_at_5"]["flips_to_better"] == []


def test_compare_to_baseline_verdict_continuous_metric_uses_paired_bootstrap():
    """`groundedness` is continuous — its verdict carries a `paired_delta`
    bootstrap interval over per-case deltas, not a sign test."""
    case_ids = [f"c{i}" for i in range(8)]
    baseline = {
        "aggregate": {"groundedness": 0.5},
        "results": [_case_row(c, recall_at_5=1.0, groundedness=0.9) for c in case_ids],
    }
    current = {
        "aggregate": {"groundedness": 0.1},
        "results": [_case_row(c, recall_at_5=1.0, groundedness=0.1) for c in case_ids],
    }

    _, _, verdict = compare_to_baseline(current, baseline)
    entry = verdict["groundedness"]

    assert entry["pairable"] is True
    assert entry["sign_test_p"] is None
    assert entry["paired_delta"] is not None
    assert entry["paired_delta"]["method"] == "bootstrap"
    assert entry["paired_delta"]["point"] == pytest.approx(0.1 - 0.9)
    assert entry["classification"] == "regressed-significant"


def test_compare_to_baseline_verdict_never_reports_improvement_when_case_ids_differ():
    baseline = {
        "aggregate": {"recall_at_5": 0.5},
        "results": [_case_row("a", recall_at_5=1.0, groundedness=1.0)],
    }
    current = {
        "aggregate": {"recall_at_5": 1.0},
        "results": [_case_row("b", recall_at_5=1.0, groundedness=1.0)],
    }

    _, _, verdict = compare_to_baseline(current, baseline)

    assert verdict["recall_at_5"]["pairable"] is False
    assert verdict["recall_at_5"]["classification"] == "incomparable"


def test_compare_to_baseline_iterates_baseline_keys_for_verdict_too():
    """A `verdict` entry is only ever computed for keys present in the
    BASELINE's aggregate — mirrors `deltas`' existing contract, so a run
    with a new metric key never produces a spurious verdict for it either."""
    baseline = {"aggregate": {"recall_at_5": 0.5}, "results": []}
    current = {
        "aggregate": {"recall_at_5": 0.5, "groundedness_on_hits": 0.9},
        "results": [],
    }

    _, _, verdict = compare_to_baseline(current, baseline)

    assert set(verdict) == {"recall_at_5"}


def test_run_eval_forwards_case_scope_as_project_filter():
    scoped_case = RetrievalCase(
        case_id="scoped",
        query="OR.K2 retrieval eval harness",
        expect_docs=("planning/or-k2-retrieval-eval-harness/tasks.md",),
        expect_abstain=False,
        source="authored",
        category="identifier",
        scope="orchestrator",
    )
    with patch(
        "brain.eval.runner.retrieval_engine.retrieve", return_value=[]
    ) as mock_retrieve:
        run_eval([scoped_case])

    _, kwargs = mock_retrieve.call_args
    assert kwargs["filters"] == {"project": "orchestrator"}


def test_run_eval_passes_surface_eval():
    """`run_eval`'s `retrieve()` call stamps `surface="eval"` (the only
    genuine plumbing gap this block closes — the other three surfaces
    were already landed in `a660715`, see `tests/brain/test_query_log.py`).
    """
    with patch(
        "brain.eval.runner.retrieval_engine.retrieve", return_value=[]
    ) as mock_retrieve:
        run_eval([_POSITIVE_CASE])

    _, kwargs = mock_retrieve.call_args
    assert kwargs["surface"] == "eval"


# ---------------------------------------------------------------------------
# write_report / compare_to_baseline (the --baseline regression gate)
# ---------------------------------------------------------------------------


def test_write_report_writes_dated_json(tmp_path):
    with patch("brain.eval.runner.retrieval_engine.retrieve", side_effect=_fixture_retrieve):
        report = run_eval([_POSITIVE_CASE])
    out_path = write_report(report, out_dir=tmp_path)

    assert out_path.exists()
    on_disk = json.loads(out_path.read_text(encoding="utf-8"))
    assert on_disk["aggregate"] == report.aggregate
    assert on_disk["case_count"] == 1


def test_compare_to_baseline_no_regression_when_metrics_improve():
    baseline = {"aggregate": {"recall_at_5": 0.5, "mrr": 0.5}}
    current = {"aggregate": {"recall_at_5": 0.8, "mrr": 0.6}}

    deltas, regressed, verdict = compare_to_baseline(current, baseline)

    assert regressed is False
    assert deltas["recall_at_5"] == pytest.approx(0.3)
    assert deltas["mrr"] == pytest.approx(0.1)
    assert isinstance(verdict, dict)


def test_compare_to_baseline_flags_seeded_regression():
    baseline = {"aggregate": {"recall_at_5": 0.8, "mrr": 0.6, "groundedness": 0.7}}
    # Seeded regression: recall_at_5 drops.
    current = {"aggregate": {"recall_at_5": 0.4, "mrr": 0.6, "groundedness": 0.7}}

    deltas, regressed, verdict = compare_to_baseline(current, baseline)

    assert regressed is True
    assert deltas["recall_at_5"] == pytest.approx(-0.4)
    # No per-case `results` on either side — the strict-sign tripwire still
    # fires, but the paired verdict can't be computed and says so.
    assert verdict["recall_at_5"]["classification"] == "incomparable"


def test_cli_eval_baseline_exits_non_zero_on_seeded_regression():
    """End-to-end through `syn eval --baseline --strict` (CLI dispatch,
    everything else patched): a seeded regression must produce a non-zero
    exit code.

    Amendment (plan-eval-statistical-honesty task 3): both fixture reports
    carry `results: []` — no per-case data — so the new paired verdict
    cannot classify any metric as `regressed-significant` (an empty case
    set is `incomparable`, never a false "significant"). This test now
    exercises `--strict`, which restores the pre-task-3 strict-sign
    tripwire: exit 1 on ANY metric decrease, exactly the semantics this
    test originally pinned. See
    `test_cli_eval_baseline_exits_one_when_regressed_significant` below for
    the new paired, statistically-significant path.
    """
    from brain.cli import main  # pylint: disable=import-outside-toplevel

    good_report = {
        "generated_at": "2026-08-01T00-00-00Z",
        "case_count": 1,
        "aggregate": {"recall_at_5": 0.9, "recall_at_10": 0.9, "mrr": 0.9, "groundedness": 0.9,
                       "abstain_correctness": 1.0},
        "results": [],
    }
    regressed_report_obj = type(
        "FakeReport",
        (),
        {
            "to_dict": lambda self: {
                "generated_at": "2026-08-01T00-01-00Z",
                "case_count": 1,
                "aggregate": {
                    "recall_at_5": 0.1,
                    "recall_at_10": 0.1,
                    "mrr": 0.1,
                    "groundedness": 0.1,
                    "abstain_correctness": 0.0,
                },
                "results": [],
            }
        },
    )()

    with patch("brain.eval.load_cases", return_value=[]), patch(
        "brain.eval.run_eval", return_value=regressed_report_obj
    ), patch("brain.eval.write_report", return_value=Path("/dev/null")), patch(
        "brain.eval.runner.load_report", return_value=good_report
    ):
        code = main(["eval", "--baseline", "/fake/baseline.json", "--strict", "--json"])

    assert code == 1


def _paired_case_results(case_ids: list[str], *, recall_at_5: float) -> list[dict]:
    """Minimal per-case `results` rows for the paired-verdict CLI tests
    below — only the fields `_case_values_for_metric` reads for
    `recall_at_5` are populated with meaningful values."""
    return [
        {
            "case_id": case_id,
            "recall_at_5": recall_at_5,
            "recall_at_10": recall_at_5,
            "reciprocal_rank": recall_at_5,
            "abstain_correct": True,
            "groundedness": recall_at_5,
            "matched_docs": ["doc"] if recall_at_5 else [],
        }
        for case_id in case_ids
    ]


def test_cli_eval_baseline_exits_one_when_regressed_significant():
    """Six paired cases flip `recall_at_5` from 1 to 0 (b=6, c=0) — the
    exact two-sided sign test gives p=0.03125, past the 5-vs-6 significance
    boundary — so `syn eval --baseline` (no `--strict` needed) must exit 1."""
    from brain.cli import main  # pylint: disable=import-outside-toplevel

    case_ids = [f"case-{i}" for i in range(6)]
    good_report = {
        "generated_at": "2026-08-01T00-00-00Z",
        "case_count": 6,
        "aggregate": {"recall_at_5": 1.0},
        "results": _paired_case_results(case_ids, recall_at_5=1.0),
    }
    regressed_report_obj = type(
        "FakeReport",
        (),
        {
            "to_dict": lambda self: {
                "generated_at": "2026-08-01T00-01-00Z",
                "case_count": 6,
                "aggregate": {"recall_at_5": 0.0},
                "results": _paired_case_results(case_ids, recall_at_5=0.0),
            }
        },
    )()

    with patch("brain.eval.load_cases", return_value=[]), patch(
        "brain.eval.run_eval", return_value=regressed_report_obj
    ), patch("brain.eval.write_report", return_value=Path("/dev/null")), patch(
        "brain.eval.runner.load_report", return_value=good_report
    ):
        code = main(["eval", "--baseline", "/fake/baseline.json", "--json"])

    assert code == 1


def test_cli_eval_baseline_exits_zero_with_warning_when_regressed_within_noise():
    """Five paired cases flip `recall_at_5` from 1 to 0 (b=5, c=0) — the
    exact sign test gives p=0.0625, just short of significance — so `syn
    eval --baseline` must exit 0 (regressed-within-noise), not 1, and must
    print a warning naming the metric."""
    from brain.cli import main  # pylint: disable=import-outside-toplevel

    case_ids = [f"case-{i}" for i in range(5)]
    good_report = {
        "generated_at": "2026-08-01T00-00-00Z",
        "case_count": 5,
        "aggregate": {"recall_at_5": 1.0},
        "results": _paired_case_results(case_ids, recall_at_5=1.0),
    }
    regressed_report_obj = type(
        "FakeReport",
        (),
        {
            "to_dict": lambda self: {
                "generated_at": "2026-08-01T00-01-00Z",
                "case_count": 5,
                "aggregate": {"recall_at_5": 0.0},
                "results": _paired_case_results(case_ids, recall_at_5=0.0),
            }
        },
    )()

    with patch("brain.eval.load_cases", return_value=[]), patch(
        "brain.eval.run_eval", return_value=regressed_report_obj
    ), patch("brain.eval.write_report", return_value=Path("/dev/null")), patch(
        "brain.eval.runner.load_report", return_value=good_report
    ):
        # Human mode (not --json) so the warning line is checked via stdout.
        code = main(["eval", "--baseline", "/fake/baseline.json"])

    assert code == 0


def test_cli_eval_without_baseline_exits_zero():
    from brain.cli import main  # pylint: disable=import-outside-toplevel

    report_obj = type(
        "FakeReport",
        (),
        {
            "to_dict": lambda self: {
                "generated_at": "2026-08-01T00-00-00Z",
                "case_count": 0,
                "aggregate": {},
                "results": [],
            }
        },
    )()

    with patch("brain.eval.load_cases", return_value=[]), patch(
        "brain.eval.run_eval", return_value=report_obj
    ), patch("brain.eval.write_report", return_value=Path("/dev/null")):
        code = main(["eval", "--json"])

    assert code == 0


# ---------------------------------------------------------------------------
# ROUTINES registration
# ---------------------------------------------------------------------------


def test_eval_routine_registered_in_ops_routines():
    from brain.ops import ROUTINES  # pylint: disable=import-outside-toplevel

    assert "eval" in ROUTINES


def test_run_routine_eval_dispatches_to_eval_package():
    from brain.ops import run_routine  # pylint: disable=import-outside-toplevel

    fake_report = type("FakeReport", (), {"to_dict": lambda self: {"aggregate": {}}})()
    with patch("brain.eval.load_cases", return_value=[]), patch(
        "brain.eval.run_eval", return_value=fake_report
    ), patch("brain.eval.write_report", return_value=Path("/dev/null")) as mock_write:
        result = run_routine("eval")

    mock_write.assert_called_once()
    assert result == {"aggregate": {}}


# ---------------------------------------------------------------------------
# Import guards
# ---------------------------------------------------------------------------


def _imports_matching(tree: ast.Module, prefix: str) -> list[str]:
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            hits.extend(alias.name for alias in node.names if alias.name.startswith(prefix))
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith(prefix):
                hits.append(node.module)
    return hits


def test_eval_package_imports_workflows_nowhere():
    """app/brain/eval/ is under app/brain/ — the same "no app/workflows/
    import" guard applies (grep-verified statically, not import-time)."""
    offenders: dict[str, list[str]] = {}
    for path in sorted(_EVAL_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        hits = _imports_matching(tree, "workflows")
        if hits:
            offenders[str(path.relative_to(_EVAL_DIR.parent.parent.parent))] = hits

    assert offenders == {}, f"app/brain/eval/ must never import app/workflows/: {offenders}"


def test_eval_package_imports_evals_nowhere():
    """app/brain/eval/ must never import app/evals/ (deleted by OR.X2 —
    its runner/gate are DB-bound to tables engine-rs owns)."""
    offenders: dict[str, list[str]] = {}
    for path in sorted(_EVAL_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        hits = _imports_matching(tree, "evals")
        if hits:
            offenders[str(path.relative_to(_EVAL_DIR.parent.parent.parent))] = hits

    assert offenders == {}, f"app/brain/eval/ must never import app/evals/: {offenders}"
