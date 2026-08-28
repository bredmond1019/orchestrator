"""Tests for `app/brain/eval/report.py` (OR.ticket.publishable-eval-report task 3).

Five groups, in the order of what actually matters:

1. The scrub test — no sentinel from `CaseResult.matched_docs` or a case id
   ever reaches the rendered output.
2. Allow-list completeness / fail-closed — an unexpected field on the run
   model never renders and never raises.
3. Golden-file tests on a fixed fixture for the summary table and the
   history table — stable ordering, deterministic float formatting.
4. A definition-drift check — the rendered metric-definition keys are
   exactly the keys `runner._aggregate` produces, `==` on sorted tuples.
5. Heterogeneous-run tolerance — rendering survives the pre-existing run
   shape (missing `corpus`/`aggregate_stats`/`groundedness_on_hits`) and
   never counts `baseline.json` as a run.

No DB/embedding calls: `report.render_run` never touches Postgres or an
embedding backend — it only reads a `RetrievalRunReport` already in memory
plus run JSON files under a caller-supplied `runs_dir` (`tmp_path` here,
never the real `planning/retrieval-eval-runs/` corpus — using the real
corpus would make the golden-file tables non-deterministic across runs of
this suite as new runs land).
"""

import json
import re
from dataclasses import dataclass

from brain.eval import report
from brain.eval.models import CaseResult, RetrievalRunReport
from brain.eval.runner import _aggregate


def _case_result(**overrides) -> CaseResult:
    """A `CaseResult` fixture with sane defaults, override any field."""
    base = {
        "case_id": "archive-1",
        "recall_at_5": 1.0,
        "recall_at_10": 1.0,
        "reciprocal_rank": 1.0,
        "predicted_abstain": False,
        "expected_abstain": False,
        "abstain_correct": True,
        "groundedness": 0.8,
        "retrieval_confidence": 0.9,
        "matched_docs": ("some-doc",),
    }
    base.update(overrides)
    return CaseResult(**base)


def _run_report(**overrides) -> RetrievalRunReport:
    """A `RetrievalRunReport` fixture with sane defaults, override any field.

    `aggregate` defaults to whatever `_aggregate` actually produces from
    `results`, so a test that doesn't care about specific numbers still
    exercises the real key set.
    """
    results = overrides.pop("results", (_case_result(),))
    aggregate = overrides.pop("aggregate", _aggregate(list(results)))
    base = {
        "generated_at": "2026-08-20T00-00-00Z",
        "case_count": len(results),
        "results": tuple(results),
        "aggregate": aggregate,
    }
    base.update(overrides)
    return RetrievalRunReport(**base)


def _write_run_file(runs_dir, filename: str, payload: dict) -> None:
    """Write a run JSON fixture directly to `runs_dir` (bypasses
    `runner.write_report` so a test can author an intentionally
    heterogeneous/legacy shape).
    """
    (runs_dir / filename).write_text(json.dumps(payload), encoding="utf-8")


# --- 1. The scrub test — the one that matters ---------------------------


class TestScrub:
    """No sentinel planted on a disclosure-risk field ever reaches output."""

    def test_matched_docs_and_case_id_sentinels_never_appear(self, tmp_path):
        result = _case_result(
            case_id="archive-ZZSENTINELCASEID",
            matched_docs=("ZZSENTINELPATH/doc.md", "ZZSENTINELDOCID"),
        )
        run_report = _run_report(results=(result,))

        output = report.render_run(run_report, runs_dir=tmp_path)

        assert "ZZSENTINELCASEID" not in output
        assert "ZZSENTINELPATH" not in output
        assert "ZZSENTINELDOCID" not in output

    def test_history_run_file_content_sentinels_never_appear(self, tmp_path):
        # A sentinel planted on a field the history loader never reads
        # (only `generated_at`/`aggregate`/filename are consulted per
        # `_load_runs`) must not leak either, in case a future field is
        # added to the run JSON shape upstream.
        legacy_run = {
            "generated_at": "2026-01-01T00-00-00Z",
            "case_count": 1,
            "aggregate": {"recall_at_5": 1.0},
            "results": [
                {
                    "case_id": "archive-1",
                    "matched_docs": ["ZZSENTINELHISTORYPATH"],
                }
            ],
        }
        _write_run_file(tmp_path, "2026-01-01T00-00-00Z.json", legacy_run)

        run_report = _run_report()
        output = report.render_run(run_report, runs_dir=tmp_path)

        assert "ZZSENTINELHISTORYPATH" not in output


# --- 2. Allow-list completeness / fail-closed ----------------------------


class TestAllowListCompleteness:
    """An unexpected field on the run model never renders and never raises."""

    def test_unexpected_field_is_never_rendered_and_does_not_raise(self, tmp_path):
        @dataclass(frozen=True)
        class _LeakyRunReport(RetrievalRunReport):
            """A subclass carrying a field the renderer has never heard of."""

            secret_field: str = "ZZLEAKED_EXTRA_FIELD"

        base = _run_report()
        leaky_report = _LeakyRunReport(
            generated_at=base.generated_at,
            case_count=base.case_count,
            results=base.results,
            aggregate=base.aggregate,
            corpus=base.corpus,
            ranking_constants=base.ranking_constants,
            aggregate_stats=base.aggregate_stats,
            secret_field="ZZLEAKED_EXTRA_FIELD",
        )

        output = report.render_run(leaky_report, runs_dir=tmp_path)

        assert "ZZLEAKED_EXTRA_FIELD" not in output

    def test_unrecognized_aggregate_key_still_renders_with_placeholder(self, tmp_path):
        # An unrecognized metric key must not vanish silently — it renders
        # with the generic placeholder rather than being dropped.
        aggregate = dict(_aggregate([_case_result()]))
        aggregate["future_metric"] = 0.5
        run_report = _run_report(aggregate=aggregate)

        output = report.render_run(run_report, runs_dir=tmp_path)

        assert "future_metric" in output
        assert report._UNKNOWN_METRIC_DEFINITION in output


# --- 3. Golden-file tests -------------------------------------------------


class TestGoldenFiles:
    """Fixed fixtures rendered to an exact expected string."""

    def test_summary_table_is_stable_and_deterministic(self):
        aggregate = {
            "recall_at_5": 1.0,
            "recall_at_10": 0.8824,
            "mrr": 0.6667,
            "groundedness": 0.36084,
            "groundedness_on_hits": 0.5576,
            "abstain_correctness": 1.0,
        }
        aggregate_stats = {"recall_at_5": {"lo": 0.9, "hi": 1.0}}
        run_report = _run_report(aggregate=aggregate, aggregate_stats=aggregate_stats)

        rows = report._metric_rows(run_report)
        table = report._render_summary_table(rows)

        expected = "\n".join(
            [
                "| Metric | Value | 95% CI |",
                "| --- | --- | --- |",
                "| Abstain correctness | 1.0000 | n/a |",
                "| Groundedness | 0.3608 | n/a |",
                "| Groundedness (on hits) | 0.5576 | n/a |",
                "| MRR | 0.6667 | n/a |",
                "| Recall@10 | 0.8824 | n/a |",
                "| Recall@5 | 1.0000 | [0.9000, 1.0000] |",
            ]
        )
        assert table == expected

    def test_history_table_is_stable_and_deterministic(self, tmp_path):
        older_run = {
            "generated_at": "2026-08-05T00-00-00Z",
            "case_count": 1,
            "aggregate": {"mrr": 0.7, "recall_at_10": 0.9412},
        }
        _write_run_file(tmp_path, "2026-08-05T00-00-00Z.json", older_run)

        # This exact filename is the one `_RUN_ANNOTATIONS` keys the
        # 2026-08-06 regression note off of — reusing it here pins the
        # annotation text into this golden test too.
        regressed_run = {
            "generated_at": "2026-08-06T13-56-48Z",
            "case_count": 1,
            "aggregate": {"mrr": 0.75, "recall_at_10": 0.8824},
        }
        _write_run_file(tmp_path, "2026-08-06T13-56-48Z.json", regressed_run)

        runs = report._load_runs(tmp_path)
        metric_keys = report._history_metric_keys(runs)
        rows = report._history_rows(runs, metric_keys)
        table = report._render_history_table(rows, metric_keys)

        expected = "\n".join(
            [
                "| Run | MRR | MRR Δ | Recall@10 | Recall@10 Δ | Notes |",
                "| --- | --- | --- | --- | --- | --- |",
                "| `2026-08-05T00-00-00Z` | 0.7000 | n/a | 0.9412 | n/a |  |",
                "| `2026-08-06T13-56-48Z` | 0.7500 | +0.0500 | 0.8824 | "
                "-0.0588 | "
                + report._RUN_ANNOTATIONS["2026-08-06T13-56-48Z.json"]
                + " |",
            ]
        )
        assert table == expected

    def test_history_table_empty_when_no_runs(self):
        assert report._render_history_table([], ()) == "No run history available."


# --- 4. Definition-drift check -------------------------------------------


class TestDefinitionDrift:
    """The rendered metric-definition keys never drift from what `_aggregate`
    actually produces.
    """

    def test_rendered_definition_keys_exactly_match_aggregate_output(self):
        results = [
            _case_result(),
            _case_result(
                case_id="archive-2",
                recall_at_5=0.0,
                recall_at_10=0.0,
                reciprocal_rank=0.0,
                groundedness=0.0,
                matched_docs=(),
            ),
        ]
        aggregate = _aggregate(results)
        run_report = _run_report(results=tuple(results), aggregate=aggregate)

        rows = report._metric_rows(run_report)
        definitions_text = report._render_definitions(rows)

        rendered_keys = tuple(sorted(set(re.findall(r"`([a-z0-9_]+)`", definitions_text))))
        assert rendered_keys == tuple(sorted(aggregate.keys()))

    def test_known_metric_tables_cover_exactly_the_aggregate_keys(self):
        # A subset assertion cannot catch an added metric — `==` on sorted
        # tuples is the point.
        produced_keys = tuple(sorted(_aggregate([_case_result()]).keys()))
        assert tuple(sorted(report._ALLOWED_METRIC_KEYS)) == produced_keys
        assert tuple(sorted(report._METRIC_LABELS.keys())) == produced_keys
        assert tuple(sorted(report._METRIC_DEFINITIONS.keys())) == produced_keys


# --- 5. Heterogeneous-run tolerance ---------------------------------------


class TestHeterogeneousRunTolerance:
    """Rendering survives the pre-existing 14-file run shape and never
    double-counts `baseline.json` as a run.
    """

    def test_render_run_tolerates_pre_existing_run_shape(self, tmp_path):
        legacy_run = {
            "generated_at": "2026-01-01T00-00-00Z",
            "case_count": 3,
            "aggregate": {
                "recall_at_5": 1.0,
                "recall_at_10": 1.0,
                "mrr": 1.0,
                "abstain_correctness": 1.0,
                "groundedness": 0.5,
                # no groundedness_on_hits — predates that metric
            },
            # no aggregate_stats, no corpus, no ranking_constants
            "results": [],
        }
        _write_run_file(tmp_path, "2026-01-01T00-00-00Z.json", legacy_run)
        _write_run_file(
            tmp_path,
            "baseline.json",
            {"run": "2026-01-01T00-00-00Z.json", "promoted_at": "2026-01-02T00-00-00Z"},
        )

        run_report = _run_report(corpus=None, aggregate_stats=None)
        output = report.render_run(run_report, runs_dir=tmp_path)

        assert "n/a" in output
        assert "Corpus fingerprint unavailable" in output

    def test_baseline_pointer_is_never_counted_as_a_run(self, tmp_path):
        run_payload = {
            "generated_at": "2026-01-01T00-00-00Z",
            "case_count": 1,
            "aggregate": {"mrr": 1.0},
        }
        _write_run_file(tmp_path, "2026-01-01T00-00-00Z.json", run_payload)
        _write_run_file(
            tmp_path,
            "baseline.json",
            {"run": "2026-01-01T00-00-00Z.json", "promoted_at": "2026-01-02T00-00-00Z"},
        )

        runs = report._load_runs(tmp_path)

        assert len(runs) == 1
        assert runs[0]["_filename"] == "2026-01-01T00-00-00Z.json"

    def test_unreadable_run_file_is_skipped_not_raised(self, tmp_path):
        (tmp_path / "2026-01-01T00-00-00Z.json").write_text("not json", encoding="utf-8")

        runs = report._load_runs(tmp_path)

        assert not runs

    def test_baseline_section_states_no_pin_when_pointer_absent(self, tmp_path):
        assert report._render_baseline_section(tmp_path) == (
            "No run has been promoted to the baseline pin."
        )

    def test_baseline_section_reads_pointer_when_present(self, tmp_path):
        _write_run_file(
            tmp_path,
            "baseline.json",
            {"run": "2026-01-01T00-00-00Z.json", "promoted_at": "2026-01-02T00-00-00Z"},
        )

        section = report._render_baseline_section(tmp_path)

        assert "2026-01-01T00-00-00Z.json" in section
        assert "2026-01-02T00-00-00Z" in section

    def test_render_run_end_to_end_does_not_raise_on_empty_runs_dir(self, tmp_path):
        run_report = _run_report()
        output = report.render_run(run_report, runs_dir=tmp_path)
        assert "No run history available." in output
