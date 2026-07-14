"""Tests for the coding-domain eval slice (Bastion Program Block OR.U, Task 5).

Fixture records mirror the real ``SDLCFlowWorkflow`` task_context storage
shape (standing rule 9): a ``{"nodes": {...}}`` mapping where
``UpdateTaskStatusNode``'s ``result`` is exactly
``schemas.sdlc_schema.SDLCState.model_dump()`` (see
``update_task_status_node.py``) and ``ConsolidatedReviewNode``'s ``result``
is ``{"verdict": str, "summary": str, "issues": list[str]}`` (see
``consolidated_review_node.py``) — not an invented layout.
"""

from evals.slice import EvalSlice
from evals.slices.coding import (
    CODING_DOMAIN,
    build_coding_slice,
    coding_scorer,
    retry_rate_scorer,
    review_pass_rate_scorer,
    spec_shipped_pass_rate_scorer,
)
from schemas.sdlc_schema import (
    SDLCReviewVerdict,
    SDLCState,
    SDLCTask,
    SDLCTaskStatus,
    SDLCTelemetry,
)


def _task(task_id, status, attempt_count=1, max_attempts=3):
    return SDLCTask(
        task_id=task_id,
        title=f"Task {task_id}",
        description="desc",
        status=status,
        attempt_count=attempt_count,
        max_attempts=max_attempts,
    )


def _clean_run_record():
    """A clean run: two tasks, both DONE, one needed a retry, review PASS."""
    state = SDLCState(
        spec_slug="fixture-spec",
        global_status=SDLCTaskStatus.DONE.value,
        tasks=[
            _task(1, SDLCTaskStatus.DONE, attempt_count=1),
            _task(2, SDLCTaskStatus.DONE, attempt_count=2),
        ],
        telemetry=SDLCTelemetry(total_attempts=3, tasks_passed=2, tasks_failed=0),
    )
    return {
        "nodes": {
            "LoadTaskStateNode": {"result": state.model_dump()},
            "UpdateTaskStatusNode": {"result": state.model_dump()},
            "ConsolidatedReviewNode": {
                "result": {
                    "verdict": SDLCReviewVerdict.PASS.value,
                    "summary": "Looks good.",
                    "issues": [],
                }
            },
        }
    }


def _bailed_run_record():
    """A MAJOR_BAIL run: one task exhausted attempts and was mutated to FAILED."""
    state = SDLCState(
        spec_slug="fixture-spec-bailed",
        global_status=SDLCTaskStatus.FAILED.value,
        tasks=[
            _task(1, SDLCTaskStatus.DONE, attempt_count=1),
            _task(2, SDLCTaskStatus.FAILED, attempt_count=3, max_attempts=3),
        ],
        telemetry=SDLCTelemetry(total_attempts=5, tasks_passed=1, tasks_failed=1),
    )
    return {
        "nodes": {
            "LoadTaskStateNode": {"result": state.model_dump()},
            "UpdateTaskStatusNode": {"result": state.model_dump()},
            # A MAJOR_BAIL routes straight to WrapUpNode — review never runs.
        }
    }


def _partial_review_run_record():
    """A run whose review verdict was FAIL but tasks still resolved DONE."""
    state = SDLCState(
        spec_slug="fixture-spec-review-fail",
        global_status=SDLCTaskStatus.DONE.value,
        tasks=[_task(1, SDLCTaskStatus.DONE, attempt_count=1)],
        telemetry=SDLCTelemetry(total_attempts=1, tasks_passed=1, tasks_failed=0),
    )
    return {
        "nodes": {
            "UpdateTaskStatusNode": {"result": state.model_dump()},
            "ConsolidatedReviewNode": {
                "result": {
                    "verdict": SDLCReviewVerdict.FAIL.value,
                    "summary": "Structural issue.",
                    "issues": ["bad diff"],
                }
            },
        }
    }


class TestSpecShippedPassRateScorer:
    def test_clean_run_scores_full_pass_rate(self):
        result = spec_shipped_pass_rate_scorer(_clean_run_record(), None)
        assert result.passed is True
        assert result.score == 1.0
        assert result.detail == {"done_count": 2, "task_count": 2}

    def test_bailed_run_scores_partial_pass_rate_and_fails(self):
        result = spec_shipped_pass_rate_scorer(_bailed_run_record(), None)
        assert result.passed is False
        assert result.score == 0.5
        assert result.detail == {"done_count": 1, "task_count": 2}


class TestRetryRateScorer:
    def test_computes_fraction_of_tasks_retried(self):
        result = retry_rate_scorer(_clean_run_record(), None)
        assert result.score == 0.5
        assert result.detail == {"retried_count": 1, "task_count": 2}

    def test_no_retries_scores_zero(self):
        result = retry_rate_scorer(_partial_review_run_record(), None)
        assert result.score == 0.0
        assert result.passed is True


class TestReviewPassRateScorer:
    def test_pass_verdict_scores_pass(self):
        result = review_pass_rate_scorer(_clean_run_record(), None)
        assert result.passed is True
        assert result.score == 1.0
        assert result.detail == {"verdict": "PASS"}

    def test_fail_verdict_scores_fail(self):
        result = review_pass_rate_scorer(_partial_review_run_record(), None)
        assert result.passed is False
        assert result.score == 0.0

    def test_review_not_reached_is_none_not_a_failure(self):
        result = review_pass_rate_scorer(_bailed_run_record(), None)
        assert result.score is None
        assert result.detail == {"reason": "review not reached"}


class TestCodingScorer:
    def test_clean_run_passes(self):
        result = coding_scorer(_clean_run_record(), None)
        assert result.passed is True
        assert result.detail["pass_rate"] == 1.0
        assert result.detail["retry_rate"] == 0.5
        assert result.detail["review_pass_rate"] == 1.0

    def test_bailed_run_fails(self):
        result = coding_scorer(_bailed_run_record(), None)
        assert result.passed is False
        assert result.detail["pass_rate"] == 0.5
        assert result.detail["review_pass_rate"] is None


class TestBuildCodingSlice:
    def test_produces_coding_domain_slice_with_one_case_per_record(self):
        records = [_clean_run_record(), _bailed_run_record()]

        eval_slice = build_coding_slice(records, models=["sonnet"], name="coding-fixture")

        assert isinstance(eval_slice, EvalSlice)
        assert eval_slice.domain == CODING_DOMAIN
        assert eval_slice.name == "coding-fixture"
        assert eval_slice.models == ["sonnet"]
        assert len(eval_slice.cases) == 2
        assert eval_slice.cases[0].input == records[0]
        assert eval_slice.cases[1].input == records[1]

    def test_defaults_models_to_recorded_placeholder(self):
        eval_slice = build_coding_slice([_clean_run_record()])
        assert eval_slice.models == ["recorded"]

    def test_bound_scorer_scores_clean_and_bailed_cases_via_identity_executor(self):
        records = [_clean_run_record(), _bailed_run_record()]
        eval_slice = build_coding_slice(records, name="coding-scoring-check")

        def identity_executor(case, model_name):
            del model_name
            return case.input

        scored = [
            eval_slice.scorer(identity_executor(case, "recorded"), case)
            for case in eval_slice.cases
        ]

        assert scored[0].passed is True
        assert scored[1].passed is False
