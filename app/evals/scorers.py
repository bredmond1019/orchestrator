"""Scorer library for the offline eval harness (Bastion Program Block OR.U).

Provides the shared ``ScoreResult`` type and the deterministic/structural and
reference-based scorer strategies described in the OR.U block contract
(``planning/master-plan.md`` -> "OR.1.H"). The third strategy, blind
LLM-as-judge, lives in ``evals.judge`` (Task 3).

Every scorer follows the common callable signature ``(output, case) ->
ScoreResult``, where ``case`` is duck-typed against the attributes an
``EvalCase`` (``evals.slice``, Task 4) provides:

- ``schema_cls``: optional pydantic model class the output must validate
  against.
- ``required_fields``: optional list of field names that must be present
  (and non-None) on the output.
- ``value_ranges``: optional mapping of field name -> (min, max) inclusive
  bounds checked against the output's value for that field.
- ``reference``: optional mapping of field name -> expected value, used by
  the reference-based scorer for normalized field matching.

Scorers accept ``case`` as any object exposing these attributes (via
``getattr``) rather than importing ``EvalCase`` directly, so this module has
no dependency on ``evals.slice`` and can be exercised standalone in tests.
"""

from typing import Any

from pydantic import BaseModel


class ScoreResult(BaseModel):
    """Outcome of applying one scorer to one case's output.

    Fields:
        passed: Whether the case passed according to this scorer.
        score: Optional continuous score (e.g. partial-credit fraction),
            in [0.0, 1.0] by convention when populated.
        detail: Free-form structured detail about the scoring outcome
            (e.g. which fields were missing or out of range).
    """

    passed: bool
    score: float | None = None
    detail: dict[str, Any] | None = None


def _get_field(output: Any, field: str) -> Any:
    """Read ``field`` off ``output``, supporting both mappings and objects."""
    if isinstance(output, dict):
        return output.get(field)
    return getattr(output, field, None)


def deterministic_scorer(output: Any, case: Any) -> ScoreResult:
    """Deterministic/structural scorer.

    Validates ``output`` against an optional pydantic schema class
    (``case.schema_cls``), checks that every name in ``case.required_fields``
    is present and non-None, and checks every ``case.value_ranges`` bound is
    satisfied. Passes only if all declared checks pass; a check that is not
    declared on the case (e.g. no ``schema_cls``) is skipped rather than
    counted as a failure.
    """
    schema_cls = getattr(case, "schema_cls", None)
    required_fields = getattr(case, "required_fields", None) or []
    value_ranges = getattr(case, "value_ranges", None) or {}

    failures: list[str] = []

    if schema_cls is not None:
        payload = output if isinstance(output, dict) else _get_field(output, "__dict__") or output
        try:
            schema_cls.model_validate(payload)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            failures.append(f"schema_invalid: {exc}")

    for field in required_fields:
        if _get_field(output, field) is None:
            failures.append(f"missing_field: {field}")

    for field, bounds in value_ranges.items():
        value = _get_field(output, field)
        if value is None:
            failures.append(f"missing_field_for_range: {field}")
            continue
        low, high = bounds
        if not low <= value <= high:
            failures.append(f"out_of_range: {field}={value} not in [{low}, {high}]")

    passed = not failures
    return ScoreResult(
        passed=passed,
        score=1.0 if passed else 0.0,
        detail={"failures": failures} if failures else None,
    )


def _normalize(value: Any) -> Any:
    """Normalize a value for comparison (stripped, case-insensitive strings)."""
    if isinstance(value, str):
        return value.strip().lower()
    return value


def reference_scorer(output: Any, case: Any) -> ScoreResult:
    """Reference-based scorer.

    Compares ``output`` against ``case.reference`` (a mapping of field name
    -> expected value) with a normalized exact match per field, awarding
    partial credit proportional to the fraction of fields that match. Passes
    only when every reference field matches (``score == 1.0``). A case with
    no reference data trivially passes.
    """
    reference: dict[str, Any] = getattr(case, "reference", None) or {}

    if not reference:
        return ScoreResult(passed=True, score=1.0, detail=None)

    field_matches: dict[str, bool] = {
        field: _normalize(_get_field(output, field)) == _normalize(expected)
        for field, expected in reference.items()
    }

    match_count = sum(1 for matched in field_matches.values() if matched)
    total = len(field_matches)
    score = match_count / total
    passed = match_count == total

    return ScoreResult(
        passed=passed,
        score=score,
        detail=None if passed else {"field_matches": field_matches},
    )
