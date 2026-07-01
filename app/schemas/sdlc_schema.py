"""Event and state schemas for the SDLC Flow (OR.Z) workflow.

These models replace markdown-based task parsing with a structured JSON task
schema so the SDLC execution runtime can drive Claude Code via Engine-native
Node/Workflow primitives. See ``planning/sdlc-workflow-architecture/`` for the
full design.
"""

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class SDLCTaskStatus(StrEnum):
    """Lifecycle states for a single SDLC task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class SDLCTriageVerdict(StrEnum):
    """Classification produced by ``TriageTaskNode`` for a test-failure."""

    PASS = "PASS"
    RETRYABLE = "RETRYABLE"
    MAJOR_BAIL = "MAJOR_BAIL"


class SDLCReviewVerdict(StrEnum):
    """Verdict produced by ``ConsolidatedReviewNode``."""

    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"


class SDLCTask(BaseModel):
    """A single task within an SDLC spec's task list."""

    task_id: int = Field(..., description="1-indexed task number within the spec")
    title: str = Field(..., description="Short human-readable task title")
    description: str = Field(..., description="Full task description / implementation notes")
    acceptance_criteria: list[str] = Field(
        default_factory=list,
        description="Observable acceptance criteria for this task",
    )
    status: SDLCTaskStatus = Field(
        default=SDLCTaskStatus.PENDING, description="Current lifecycle status"
    )
    validation_commands: list[str] = Field(
        default_factory=list,
        description="Shell commands used to validate this task's implementation",
    )
    attempt_count: int = Field(
        default=0, ge=0, description="Number of implement→test attempts made so far"
    )
    max_attempts: int = Field(
        default=3, ge=1, description="Maximum number of attempts before a MAJOR_BAIL"
    )


class SDLCFlowEventSchema(BaseModel):
    """Inbound event schema for the ``SDLC_FLOW`` workflow."""

    spec_slug: str = Field(..., description="Slug identifying the target spec directory")
    task_range: str | None = Field(
        default=None,
        description='Optional task-range filter, e.g. "1-3,5" (1-indexed, inclusive)',
    )
    resume: bool = Field(
        default=False, description="Whether to reattach to an existing worktree/state"
    )
    auto_pr: bool = Field(
        default=True, description="Whether to open a PR automatically once the run completes"
    )
    branch_name: str | None = Field(
        default=None,
        description="Override for the git branch name; derived from spec_slug if unset",
    )

    @staticmethod
    def parse_task_range(task_range: str | None) -> list[int] | None:
        """Parse a range string like ``"1-3,5"`` into a sorted list of task ids.

        Returns ``None`` if ``task_range`` is ``None`` (meaning: all tasks).
        """
        if task_range is None:
            return None

        task_ids: set[int] = set()
        for chunk in task_range.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            if "-" in chunk:
                start_str, end_str = chunk.split("-", 1)
                start, end = int(start_str), int(end_str)
                if end < start:
                    raise ValueError(f"Invalid task range chunk (end < start): {chunk!r}")
                task_ids.update(range(start, end + 1))
            else:
                task_ids.add(int(chunk))
        return sorted(task_ids)

    @field_validator("task_range")
    @classmethod
    def _validate_task_range_format(cls, value: str | None) -> str | None:
        if value is None:
            return value
        # Raises ValueError on malformed input; surfaces as a Pydantic ValidationError.
        cls.parse_task_range(value)
        return value


class SDLCTelemetry(BaseModel):
    """Aggregate telemetry counters for an SDLC flow run."""

    total_attempts: int = Field(
        default=0, ge=0, description="Total implement→test attempts made"
    )
    budget_spent: float = Field(
        default=0.0, ge=0.0, description="Cumulative token/dollar cost spent"
    )
    tasks_passed: int = Field(default=0, ge=0, description="Number of tasks that reached DONE")
    tasks_failed: int = Field(default=0, ge=0, description="Number of tasks that reached FAILED")


class SDLCState(BaseModel):
    """The full durable state for an in-flight or completed SDLC flow run."""

    spec_slug: str = Field(..., description="Slug identifying the target spec directory")
    phase_id: str | None = Field(default=None, description="Owning phase identifier, if known")
    block_id: str | None = Field(
        default=None, description="Owning program block identifier, if known"
    )
    global_status: str = Field(
        default=SDLCTaskStatus.PENDING.value,
        description="Overall run status (mirrors SDLCTaskStatus values)",
    )
    tasks: list[SDLCTask] = Field(
        default_factory=list, description="Ordered list of tasks in this spec"
    )
    telemetry: SDLCTelemetry = Field(
        default_factory=SDLCTelemetry, description="Aggregate telemetry for this run"
    )
