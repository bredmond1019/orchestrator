"""Tests for the deterministic/structural and reference-based scorers."""

from types import SimpleNamespace

from evals.scorers import ScoreResult, deterministic_scorer, reference_scorer
from pydantic import BaseModel


class _OutputSchema(BaseModel):
    """Minimal schema used to exercise the deterministic scorer's schema check."""

    name: str
    count: int


def _case(**overrides):
    """Build a scorer case with sensible empty defaults, allowing overrides."""
    defaults = dict(
        schema_cls=None,
        required_fields=None,
        value_ranges=None,
        reference=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestDeterministicScorer:
    def test_known_good_passes(self):
        case = _case(
            schema_cls=_OutputSchema,
            required_fields=["name", "count"],
            value_ranges={"count": (0, 10)},
        )
        output = {"name": "alpha", "count": 5}

        result = deterministic_scorer(output, case)

        assert isinstance(result, ScoreResult)
        assert result.passed is True
        assert result.score == 1.0
        assert result.detail is None

    def test_schema_invalid_fails(self):
        case = _case(schema_cls=_OutputSchema)
        output = {"name": "alpha"}  # missing required 'count' for the schema

        result = deterministic_scorer(output, case)

        assert result.passed is False
        assert result.score == 0.0
        assert any("schema_invalid" in failure for failure in result.detail["failures"])

    def test_missing_required_field_fails(self):
        case = _case(required_fields=["name", "count"])
        output = {"name": "alpha"}

        result = deterministic_scorer(output, case)

        assert result.passed is False
        assert "missing_field: count" in result.detail["failures"]

    def test_out_of_range_fails(self):
        case = _case(value_ranges={"count": (0, 10)})
        output = {"count": 42}

        result = deterministic_scorer(output, case)

        assert result.passed is False
        assert any("out_of_range" in failure for failure in result.detail["failures"])

    def test_no_declared_checks_passes(self):
        case = _case()
        output = {"anything": "goes"}

        result = deterministic_scorer(output, case)

        assert result.passed is True

    def test_returns_shared_score_result_type(self):
        case = _case()
        result = deterministic_scorer({}, case)
        assert isinstance(result, ScoreResult)


class TestReferenceScorer:
    def test_exact_match_scores_one(self):
        case = _case(reference={"name": "alpha", "count": 5})
        output = {"name": "Alpha", "count": 5}  # normalized string match

        result = reference_scorer(output, case)

        assert result.passed is True
        assert result.score == 1.0
        assert result.detail is None

    def test_disjoint_scores_zero(self):
        case = _case(reference={"name": "alpha", "count": 5})
        output = {"name": "beta", "count": 99}

        result = reference_scorer(output, case)

        assert result.passed is False
        assert result.score == 0.0
        assert result.detail["field_matches"] == {"name": False, "count": False}

    def test_partial_match_scores_between(self):
        case = _case(reference={"name": "alpha", "count": 5})
        output = {"name": "alpha", "count": 99}

        result = reference_scorer(output, case)

        assert result.passed is False
        assert result.score == 0.5
        assert result.detail["field_matches"] == {"name": True, "count": False}

    def test_no_reference_data_trivially_passes(self):
        case = _case(reference=None)

        result = reference_scorer({"anything": "goes"}, case)

        assert result.passed is True
        assert result.score == 1.0

    def test_returns_shared_score_result_type(self):
        case = _case(reference={"name": "alpha"})
        result = reference_scorer({"name": "alpha"}, case)
        assert isinstance(result, ScoreResult)
