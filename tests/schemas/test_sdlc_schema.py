"""Tests for the SDLC Flow schemas (Task 1 — OR.Z).

Covers:
- SDLCTask construction, defaults, and status transitions
- SDLCFlowEventSchema field validation, defaults, and task_range parsing
- SDLCState / SDLCTelemetry construction and round-trip serialization
- SDLCTriageVerdict / SDLCReviewVerdict enum members
"""

import pytest
from pydantic import ValidationError

from schemas.sdlc_schema import (
    SDLCFlowEventSchema,
    SDLCReviewVerdict,
    SDLCState,
    SDLCTask,
    SDLCTaskStatus,
    SDLCTelemetry,
    SDLCTriageVerdict,
)


# ---------------------------------------------------------------------------
# SDLCTask
# ---------------------------------------------------------------------------


class TestSDLCTask:
    def test_required_fields_and_defaults(self):
        task = SDLCTask(task_id=1, title="Do the thing", description="Detailed description")
        assert task.task_id == 1
        assert task.title == "Do the thing"
        assert task.description == "Detailed description"
        assert task.acceptance_criteria == []
        assert task.status == SDLCTaskStatus.PENDING
        assert task.validation_commands == []
        assert task.attempt_count == 0
        assert task.max_attempts == 3

    def test_missing_required_field_rejected(self):
        with pytest.raises(ValidationError):
            SDLCTask(task_id=1, title="Do the thing")

    def test_status_transitions(self):
        task = SDLCTask(task_id=1, title="t", description="d")
        task.status = SDLCTaskStatus.IN_PROGRESS
        assert task.status == SDLCTaskStatus.IN_PROGRESS
        task.status = SDLCTaskStatus.DONE
        assert task.status == SDLCTaskStatus.DONE

    def test_status_rejects_invalid_value(self):
        with pytest.raises(ValidationError):
            SDLCTask(task_id=1, title="t", description="d", status="bogus")

    def test_attempt_count_cannot_be_negative(self):
        with pytest.raises(ValidationError):
            SDLCTask(task_id=1, title="t", description="d", attempt_count=-1)

    def test_max_attempts_must_be_at_least_one(self):
        with pytest.raises(ValidationError):
            SDLCTask(task_id=1, title="t", description="d", max_attempts=0)

    def test_round_trip_serialization(self):
        task = SDLCTask(
            task_id=2,
            title="Round trip",
            description="desc",
            acceptance_criteria=["works"],
            validation_commands=["pytest"],
        )
        payload = task.model_dump_json()
        restored = SDLCTask.model_validate_json(payload)
        assert restored == task


# ---------------------------------------------------------------------------
# SDLCFlowEventSchema
# ---------------------------------------------------------------------------


class TestSDLCFlowEventSchema:
    def test_required_field_and_defaults(self):
        event = SDLCFlowEventSchema(spec_slug="sdlc-workflow-architecture")
        assert event.spec_slug == "sdlc-workflow-architecture"
        assert event.task_range is None
        assert event.resume is False
        assert event.auto_pr is True
        assert event.branch_name is None

    def test_missing_spec_slug_rejected(self):
        with pytest.raises(ValidationError):
            SDLCFlowEventSchema()

    def test_optional_fields_accepted(self):
        event = SDLCFlowEventSchema(
            spec_slug="my-spec",
            task_range="1-3,5",
            resume=True,
            auto_pr=False,
            branch_name="my-branch",
        )
        assert event.task_range == "1-3,5"
        assert event.resume is True
        assert event.auto_pr is False
        assert event.branch_name == "my-branch"

    def test_task_range_malformed_rejected(self):
        with pytest.raises(ValidationError):
            SDLCFlowEventSchema(spec_slug="s", task_range="3-1")

    def test_task_range_non_numeric_rejected(self):
        with pytest.raises(ValidationError):
            SDLCFlowEventSchema(spec_slug="s", task_range="abc")

    @pytest.mark.parametrize(
        ("task_range", "expected"),
        [
            (None, None),
            ("1-3,5", [1, 2, 3, 5]),
            ("5", [5]),
            ("1-3,2-4", [1, 2, 3, 4]),
            (" 1 , 2 ", [1, 2]),
        ],
    )
    def test_parse_task_range(self, task_range, expected):
        assert SDLCFlowEventSchema.parse_task_range(task_range) == expected

    def test_round_trip_serialization(self):
        event = SDLCFlowEventSchema(spec_slug="s", task_range="1-2", branch_name="b")
        payload = event.model_dump_json()
        restored = SDLCFlowEventSchema.model_validate_json(payload)
        assert restored == event


# ---------------------------------------------------------------------------
# SDLCTelemetry / SDLCState
# ---------------------------------------------------------------------------


class TestSDLCTelemetry:
    def test_defaults(self):
        telemetry = SDLCTelemetry()
        assert telemetry.total_attempts == 0
        assert telemetry.budget_spent == 0.0
        assert telemetry.tasks_passed == 0
        assert telemetry.tasks_failed == 0

    def test_negative_values_rejected(self):
        with pytest.raises(ValidationError):
            SDLCTelemetry(total_attempts=-1)
        with pytest.raises(ValidationError):
            SDLCTelemetry(budget_spent=-0.01)


class TestSDLCState:
    def test_construction_with_defaults(self):
        state = SDLCState(spec_slug="s")
        assert state.spec_slug == "s"
        assert state.phase_id is None
        assert state.block_id is None
        assert state.global_status == SDLCTaskStatus.PENDING.value
        assert state.tasks == []
        assert isinstance(state.telemetry, SDLCTelemetry)

    def test_construction_with_tasks(self):
        task = SDLCTask(task_id=1, title="t", description="d")
        state = SDLCState(spec_slug="s", tasks=[task])
        assert len(state.tasks) == 1
        assert state.tasks[0].task_id == 1

    def test_round_trip_serialization(self):
        task = SDLCTask(task_id=1, title="t", description="d")
        state = SDLCState(
            spec_slug="s",
            phase_id="phase-1",
            block_id="OR.Z",
            tasks=[task],
            telemetry=SDLCTelemetry(total_attempts=2, tasks_passed=1),
        )
        payload = state.model_dump_json()
        restored = SDLCState.model_validate_json(payload)
        assert restored == state


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestVerdictEnums:
    def test_triage_verdict_members(self):
        assert set(SDLCTriageVerdict) == {
            SDLCTriageVerdict.PASS,
            SDLCTriageVerdict.RETRYABLE,
            SDLCTriageVerdict.MAJOR_BAIL,
        }

    def test_review_verdict_members(self):
        assert set(SDLCReviewVerdict) == {
            SDLCReviewVerdict.PASS,
            SDLCReviewVerdict.FAIL,
            SDLCReviewVerdict.PARTIAL,
        }

    def test_task_status_members(self):
        assert set(SDLCTaskStatus) == {
            SDLCTaskStatus.PENDING,
            SDLCTaskStatus.IN_PROGRESS,
            SDLCTaskStatus.DONE,
            SDLCTaskStatus.FAILED,
            SDLCTaskStatus.SKIPPED,
        }
