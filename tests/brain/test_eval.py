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
from pathlib import Path
from unittest.mock import patch

import pytest
from brain.eval.models import RetrievalCase
from brain.eval.runner import compare_to_baseline, run_eval, write_report
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
)

_NEGATIVE_CASE = RetrievalCase(
    case_id="fixture-negative",
    query="What is the meaning of life and how do I bake a souffle?",
    expect_docs=(),
    expect_abstain=True,
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


def test_run_eval_is_deterministic_across_two_runs():
    cases = [_POSITIVE_CASE, _NEGATIVE_CASE]
    with patch("brain.eval.runner.retrieval_engine.retrieve", side_effect=_fixture_retrieve):
        report_one = run_eval(cases)
        report_two = run_eval(cases)

    assert report_one.aggregate == report_two.aggregate
    assert [r.case_id for r in report_one.results] == [r.case_id for r in report_two.results]
    assert [r.recall_at_5 for r in report_one.results] == [
        r.recall_at_5 for r in report_two.results
    ]


def test_run_eval_forwards_case_scope_as_project_filter():
    scoped_case = RetrievalCase(
        case_id="scoped",
        query="OR.K2 retrieval eval harness",
        expect_docs=("planning/or-k2-retrieval-eval-harness/tasks.md",),
        expect_abstain=False,
        scope="orchestrator",
    )
    with patch(
        "brain.eval.runner.retrieval_engine.retrieve", return_value=[]
    ) as mock_retrieve:
        run_eval([scoped_case])

    _, kwargs = mock_retrieve.call_args
    assert kwargs["filters"] == {"project": "orchestrator"}


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

    deltas, regressed = compare_to_baseline(current, baseline)

    assert regressed is False
    assert deltas["recall_at_5"] == pytest.approx(0.3)
    assert deltas["mrr"] == pytest.approx(0.1)


def test_compare_to_baseline_flags_seeded_regression():
    baseline = {"aggregate": {"recall_at_5": 0.8, "mrr": 0.6, "groundedness": 0.7}}
    # Seeded regression: recall_at_5 drops.
    current = {"aggregate": {"recall_at_5": 0.4, "mrr": 0.6, "groundedness": 0.7}}

    deltas, regressed = compare_to_baseline(current, baseline)

    assert regressed is True
    assert deltas["recall_at_5"] == pytest.approx(-0.4)


def test_cli_eval_baseline_exits_non_zero_on_seeded_regression():
    """End-to-end through `syn eval --baseline` (CLI dispatch, everything
    else patched): a seeded regression must produce a non-zero exit code."""
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
        code = main(["eval", "--baseline", "/fake/baseline.json", "--json"])

    assert code == 1


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
