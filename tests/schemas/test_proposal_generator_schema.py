"""Tests for proposal_generator schemas (Task 1 — Project C).

Covers:
- ProposalGeneratorEventSchema field validation and defaults
- ScoredCandidate composite formula validation
- AutomationRoadmap sort invariant and top_profiles limit
- Registry-presence regression guard (both workflow_registry and schema_registry)
"""

from uuid import UUID

import pytest
from pydantic import ValidationError

from api.schema_registry import SCHEMA_MAP
from schemas.proposal_generator_schema import (
    AutomationRoadmap,
    Opportunity,
    ProposalGeneratorEventSchema,
    ScoredCandidate,
    WorkflowProfile,
)
from workflows.proposal_generator_workflow import ProposalGeneratorWorkflow
from workflows.workflow_registry import WorkflowRegistry


# ---------------------------------------------------------------------------
# ProposalGeneratorEventSchema
# ---------------------------------------------------------------------------


class TestProposalGeneratorEventSchema:
    """Field validation, defaults, and required-field enforcement."""

    def test_required_fields_present(self):
        event = ProposalGeneratorEventSchema(
            company_name="Acme", industry="Tech", description="A tech company"
        )
        assert event.company_name == "Acme"
        assert event.industry == "Tech"
        assert event.description == "A tech company"

    def test_language_defaults_to_pt(self):
        event = ProposalGeneratorEventSchema(
            company_name="Acme", industry="Tech", description="A tech company"
        )
        assert event.language == "PT"

    def test_language_en_accepted(self):
        event = ProposalGeneratorEventSchema(
            company_name="Acme", industry="Tech", description="A tech company", language="EN"
        )
        assert event.language == "EN"

    def test_language_invalid_rejected(self):
        with pytest.raises(ValidationError):
            ProposalGeneratorEventSchema(
                company_name="Acme", industry="Tech", description="desc", language="FR"
            )

    def test_artifact_id_auto_generated(self):
        event = ProposalGeneratorEventSchema(
            company_name="Acme", industry="Tech", description="desc"
        )
        assert isinstance(event.artifact_id, UUID)

    def test_timestamp_timezone_aware(self):
        event = ProposalGeneratorEventSchema(
            company_name="Acme", industry="Tech", description="desc"
        )
        assert event.timestamp.tzinfo is not None

    def test_intake_notes_optional(self):
        event = ProposalGeneratorEventSchema(
            company_name="Acme", industry="Tech", description="desc"
        )
        assert event.intake_notes is None

    def test_intake_notes_accepts_string(self):
        event = ProposalGeneratorEventSchema(
            company_name="Acme",
            industry="Tech",
            description="desc",
            intake_notes="Raw intake data here",
        )
        assert event.intake_notes == "Raw intake data here"

    def test_missing_company_name_raises(self):
        with pytest.raises(ValidationError):
            ProposalGeneratorEventSchema(industry="Tech", description="desc")

    def test_missing_industry_raises(self):
        with pytest.raises(ValidationError):
            ProposalGeneratorEventSchema(company_name="Acme", description="desc")


# ---------------------------------------------------------------------------
# ScoredCandidate / Opportunity alias
# ---------------------------------------------------------------------------


def _make_candidate(
    frequency: float = 4.0,
    time_cost: float = 3.0,
    buildability: float = 5.0,
    **overrides,
) -> dict:
    """Build a valid ScoredCandidate payload with correct composite."""
    composite = (frequency * 0.35) + (time_cost * 0.40) + (buildability * 0.25)
    base = {
        "name": "Test Opportunity",
        "problem_statement": "Manual data entry wastes time",
        "proposed_solution": "Automate via RPA",
        "estimated_value": "10 hrs/week recovered",
        "build_complexity": "Medium",
        "frequency": frequency,
        "time_cost": time_cost,
        "buildability": buildability,
        "composite": round(composite, 4),
    }
    base.update(overrides)
    return base


class TestScoredCandidate:
    """Composite formula validation."""

    def test_valid_candidate_is_created(self):
        data = _make_candidate()
        candidate = ScoredCandidate(**data)
        assert candidate.name == "Test Opportunity"

    def test_composite_formula_computed_correctly(self):
        # (4 × 0.35) + (3 × 0.40) + (5 × 0.25) = 1.40 + 1.20 + 1.25 = 3.85
        data = _make_candidate(frequency=4.0, time_cost=3.0, buildability=5.0)
        candidate = ScoredCandidate(**data)
        assert abs(candidate.composite - 3.85) < 0.001

    def test_wrong_composite_raises(self):
        data = _make_candidate()
        data["composite"] = 1.0  # deliberately wrong
        with pytest.raises(ValidationError, match="composite"):
            ScoredCandidate(**data)

    def test_frequency_out_of_range_raises(self):
        data = _make_candidate()
        data["frequency"] = 6.0  # > 5 is invalid
        with pytest.raises(ValidationError):
            ScoredCandidate(**data)

    def test_opportunity_alias_is_scored_candidate(self):
        """Opportunity is the backward-compatible alias for ScoredCandidate."""
        assert Opportunity is ScoredCandidate


# ---------------------------------------------------------------------------
# WorkflowProfile
# ---------------------------------------------------------------------------


def _make_profile(**overrides) -> dict:
    base = {
        "name": "Invoice Automation",
        "current_state": "Manual invoice entry each week",
        "proposed_solution": "AI extraction + ERP integration",
        "stack": ["Python", "FastAPI", "Celery"],
        "rough_scope_weeks": (4, 6),
        "roi_hrs_per_week": 8.0,
    }
    base.update(overrides)
    return base


class TestWorkflowProfile:
    def test_valid_profile_created(self):
        profile = WorkflowProfile(**_make_profile())
        assert profile.name == "Invoice Automation"
        assert profile.rough_scope_weeks == (4, 6)

    def test_stack_is_list(self):
        profile = WorkflowProfile(**_make_profile())
        assert isinstance(profile.stack, list)


# ---------------------------------------------------------------------------
# AutomationRoadmap
# ---------------------------------------------------------------------------


def _make_roadmap(candidates: list[dict], top_profiles: list[dict] | None = None) -> dict:
    if top_profiles is None:
        top_profiles = [_make_profile()]
    return {
        "situation_summary": "Client has significant manual workload",
        "candidates": candidates,
        "top_profiles": top_profiles,
        "recommended_workflow": "Invoice Automation",
        "engagement_scope": "Phase 1: invoice extraction pilot (4–6 weeks)",
        "price_range_brl": (15000, 25000),
    }


class TestAutomationRoadmap:
    """Sort invariant and top_profiles limit."""

    def test_valid_roadmap_with_sorted_candidates(self):
        c1 = _make_candidate(frequency=5.0, time_cost=5.0, buildability=5.0)
        c2 = _make_candidate(frequency=3.0, time_cost=2.0, buildability=4.0)
        # c1.composite > c2.composite so [c1, c2] is sorted descending
        roadmap_data = _make_roadmap([c1, c2])
        roadmap = AutomationRoadmap(**roadmap_data)
        assert roadmap.candidates[0].composite >= roadmap.candidates[1].composite

    def test_unsorted_candidates_raises(self):
        c1 = _make_candidate(frequency=2.0, time_cost=2.0, buildability=2.0)
        c2 = _make_candidate(frequency=5.0, time_cost=5.0, buildability=5.0)
        # c2.composite > c1.composite — [c1, c2] is ascending (wrong order)
        roadmap_data = _make_roadmap([c1, c2])
        with pytest.raises(ValidationError, match="sorted"):
            AutomationRoadmap(**roadmap_data)

    def test_top_profiles_up_to_3(self):
        c1 = _make_candidate(frequency=5.0, time_cost=5.0, buildability=5.0)
        profiles = [_make_profile(name=f"Workflow {i}") for i in range(3)]
        roadmap_data = _make_roadmap([c1], top_profiles=profiles)
        roadmap = AutomationRoadmap(**roadmap_data)
        assert len(roadmap.top_profiles) == 3

    def test_top_profiles_exceeding_3_raises(self):
        c1 = _make_candidate(frequency=5.0, time_cost=5.0, buildability=5.0)
        profiles = [_make_profile(name=f"Workflow {i}") for i in range(4)]
        roadmap_data = _make_roadmap([c1], top_profiles=profiles)
        with pytest.raises(ValidationError, match="top_profiles"):
            AutomationRoadmap(**roadmap_data)

    def test_top_profiles_fewer_than_3_is_valid(self):
        """When fewer than 3 candidates exist, fewer profiles are acceptable."""
        c1 = _make_candidate(frequency=5.0, time_cost=5.0, buildability=5.0)
        profiles = [_make_profile()]  # only 1
        roadmap_data = _make_roadmap([c1], top_profiles=profiles)
        roadmap = AutomationRoadmap(**roadmap_data)
        assert len(roadmap.top_profiles) == 1

    def test_price_range_brl_is_tuple(self):
        c1 = _make_candidate(frequency=5.0, time_cost=5.0, buildability=5.0)
        roadmap_data = _make_roadmap([c1])
        roadmap = AutomationRoadmap(**roadmap_data)
        assert isinstance(roadmap.price_range_brl, tuple)
        assert len(roadmap.price_range_brl) == 2


# ---------------------------------------------------------------------------
# Registry-presence regression guard
# ---------------------------------------------------------------------------


class TestRegistryPresence:
    """PROPOSAL_GENERATOR must appear in both registries.

    Regression guard for the Project B gap: workflow added to WorkflowRegistry
    but missing from SCHEMA_MAP caused the API dispatcher to 422 all requests.
    """

    def test_proposal_generator_in_workflow_registry(self):
        assert WorkflowRegistry.PROPOSAL_GENERATOR.value is ProposalGeneratorWorkflow

    def test_proposal_generator_in_schema_map(self):
        assert WorkflowRegistry.PROPOSAL_GENERATOR.name in SCHEMA_MAP
        assert SCHEMA_MAP[WorkflowRegistry.PROPOSAL_GENERATOR.name] is ProposalGeneratorEventSchema

    def test_every_workflow_registry_member_in_schema_map(self):
        """All WorkflowRegistry members must have a SCHEMA_MAP entry."""
        missing = [
            member.name
            for member in WorkflowRegistry
            if member.name not in SCHEMA_MAP
        ]
        assert not missing, (
            f"WorkflowRegistry members missing from SCHEMA_MAP: {missing}. "
            "Add them to app/api/schema_registry.py."
        )
