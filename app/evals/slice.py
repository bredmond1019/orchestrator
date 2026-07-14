"""Eval case and slice definitions for the offline eval harness (Bastion
Program Block OR.U).

An ``EvalSlice`` is the unit of work the runner (``evals.runner``) executes:
a named, domain-tagged collection of ``EvalCase`` objects bound to a single
scorer, run against one or more models under test. Slices are built offline
(see ``evals.slices.coding`` for the first, Task 5) and handed to
``evals.runner.run_slice`` — nothing here talks to a database or a model.

``EvalCase`` intentionally mirrors the duck-typed attributes
``evals.scorers.deterministic_scorer`` / ``reference_scorer`` read off their
``case`` argument (``schema_cls``, ``required_fields``, ``value_ranges``,
``reference``), so a case built here can be scored directly by either scorer
without adaptation.
"""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

from evals.scorers import ScoreResult


class EvalCase(BaseModel):
    """One case within an eval slice.

    Attributes:
        case_id: stable identifier for this case within its slice.
        input: the payload handed to the executor to produce a model output.
        expected: optional expected/gold output, for slices that want to
            keep the raw expectation around alongside the fields the scorer
            actually reads off ``reference``/``value_ranges``.
        reference: optional field name -> expected value mapping consumed by
            ``evals.scorers.reference_scorer``.
        schema_cls: optional pydantic model class consumed by
            ``evals.scorers.deterministic_scorer`` to validate output shape.
        required_fields: optional list of field names that must be present
            and non-None on the output, per ``deterministic_scorer``.
        value_ranges: optional field name -> (min, max) inclusive bounds,
            per ``deterministic_scorer``.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    case_id: str
    input: dict[str, Any]
    expected: dict[str, Any] | None = None
    reference: dict[str, Any] | None = None
    schema_cls: type[BaseModel] | None = None
    required_fields: list[str] | None = None
    value_ranges: dict[str, tuple[float, float]] | None = None


# A scorer takes (output, case) and returns a ScoreResult — the same shape
# every strategy in evals.scorers / evals.judge implements.
ScorerCallable = Callable[[Any, EvalCase], ScoreResult]

# An executor produces a model's output for one case, given the case and the
# model name under test. Real executors (e.g. invoking an agent, or loading
# recorded SDLC telemetry) are injected by callers (evals.runner, the CLI in
# Task 7); this module only depends on the callable shape.
Executor = Callable[[EvalCase, str], Any]


class EvalSlice(BaseModel):
    """A named, domain-tagged collection of cases bound to one scorer.

    Attributes:
        name: stable slice name (e.g. "coding") used as the regression-history
            key (``EvalRun.slice_name``).
        domain: one of the north-star domain strings (e.g. "coding");
            persisted as ``EvalRun.domain`` for by-domain aggregation.
        cases: the cases to execute.
        scorer: the scorer callable bound to this slice.
        scorer_name: human-readable name for the bound scorer, persisted on
            each ``EvalResult.scorer`` row.
        models: the models under test this slice should be run against.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    domain: str
    cases: list[EvalCase]
    scorer: ScorerCallable
    scorer_name: str = "deterministic"
    models: list[str]
