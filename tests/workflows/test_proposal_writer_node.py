"""Unit tests for ProposalWriterNode.

All agents are mocked — no real API call, no model, no key required.
Tests verify:
- Valid AutomationRoadmap is produced from OpportunityIdentifierNode output
- PT and EN language paths are both exercised
- top_profiles contains at most 3 entries
- candidates order is preserved (composite-desc)
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from core.nodes.agent import AgentNode
from core.task import NodeRun, NodeStatus, TaskContext
from schemas.proposal_generator_schema import (
    AutomationRoadmap,
    ScoredCandidate,
    WorkflowProfile,
)
from workflows.proposal_generator_workflow_nodes.proposal_writer_node import (
    ProposalWriterNode,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_node() -> ProposalWriterNode:
    """Construct ProposalWriterNode without building a real Agent."""
    node = ProposalWriterNode.__new__(ProposalWriterNode)
    node.agent = MagicMock()
    return node


def _result_for(output) -> MagicMock:
    r = MagicMock()
    r.output = output
    r.usage.return_value = MagicMock(input_tokens=1, output_tokens=1)
    return r


def _scored_candidate(name: str, frequency: float, time_cost: float, buildability: float) -> ScoredCandidate:
    composite = round((frequency * 0.35) + (time_cost * 0.40) + (buildability * 0.25), 4)
    return ScoredCandidate(
        name=name,
        problem_statement=f"{name} takes too long manually.",
        proposed_solution=f"Automate {name} with an agent pipeline.",
        estimated_value="8 hrs/week recovered",
        build_complexity="Medium",
        frequency=frequency,
        time_cost=time_cost,
        buildability=buildability,
        composite=composite,
    )


def _workflow_profile(name: str) -> WorkflowProfile:
    return WorkflowProfile(
        name=name,
        current_state="Manual spreadsheet process",
        proposed_solution="Automated agent pipeline",
        stack=["Python", "FastAPI"],
        rough_scope_weeks=(4, 6),
        roi_hrs_per_week=8.0,
    )


def _make_roadmap_output(language: str = "PT", num_candidates: int = 3) -> "ProposalWriterNode.OutputType":
    """Build a ProposalWriterNode.OutputType instance (raw agent output)."""
    candidates = [
        _scored_candidate("Invoice Processing", 5.0, 5.0, 4.0),
        _scored_candidate("Inventory Sync", 4.0, 4.0, 4.0),
        _scored_candidate("Report Generation", 3.0, 3.0, 4.0),
    ][:num_candidates]

    profiles = [_workflow_profile(c.name) for c in candidates[:3]]

    raw = ProposalWriterNode.OutputType(
        situation_summary=(
            "Empresa Acme opera manualmente em três processos críticos."
            if language == "PT"
            else "Acme operates manually across three critical processes."
        ),
        candidates=candidates,
        top_profiles=profiles,
        recommended_workflow=candidates[0].name,
        engagement_scope=(
            "Automatizar o processamento de faturas em 6 semanas com entrega de uma API de ingestão."
            if language == "PT"
            else "Automate invoice processing in 6 weeks delivering a single ingestion API."
        ),
        price_range_brl=(15000, 25000),
        body_pt="Corpo em português." if language == "PT" else None,
        body_en=None if language == "PT" else "English body.",
    )
    return raw


def _make_ctx(language: str = "PT") -> TaskContext:
    """Seed a TaskContext with OpportunityIdentifierNode output."""
    from schemas.proposal_generator_schema import ProposalGeneratorEventSchema

    event = ProposalGeneratorEventSchema(
        company_name="Acme Corp",
        industry="Retail",
        description="Small retail company",
        language=language,  # type: ignore[arg-type]
    )
    ctx = TaskContext(event=event)

    # Seed OpportunityIdentifierNode output (what the writer reads)
    candidates = [
        _scored_candidate("Invoice Processing", 5.0, 5.0, 4.0),
        _scored_candidate("Inventory Sync", 4.0, 4.0, 4.0),
        _scored_candidate("Report Generation", 3.0, 3.0, 4.0),
    ]
    opportunity_output = {
        "candidates": [c.model_dump() for c in candidates],
        "recommended": "Invoice Processing",
        "situation_notes": "Three pain points identified.",
    }
    ctx.nodes["OpportunityIdentifierNode"] = {"result": opportunity_output}
    ctx.node_runs["ProposalWriterNode"] = NodeRun(status=NodeStatus.RUNNING)
    return ctx


# ---------------------------------------------------------------------------
# Core behaviour
# ---------------------------------------------------------------------------


class TestProposalWriterNodeProducesValidRoadmap:
    def test_produces_valid_automation_roadmap(self):
        """process() stores a valid AutomationRoadmap in the context."""
        node = _make_node()
        raw = _make_roadmap_output("PT")
        node.agent.run_sync.return_value = _result_for(raw)

        ctx = _make_ctx("PT")
        node.process(ctx)

        stored = ctx.nodes["ProposalWriterNode"]["result"]
        assert isinstance(stored, AutomationRoadmap)
        assert stored.situation_summary
        assert stored.recommended_workflow == "Invoice Processing"
        assert stored.price_range_brl == (15000, 25000)

    def test_candidates_order_preserved(self):
        """candidates are stored in the same composite-desc order as the agent produced."""
        node = _make_node()
        raw = _make_roadmap_output("PT")
        node.agent.run_sync.return_value = _result_for(raw)

        ctx = _make_ctx("PT")
        node.process(ctx)

        stored = ctx.nodes["ProposalWriterNode"]["result"]
        composites = [c.composite for c in stored.candidates]
        assert composites == sorted(composites, reverse=True)

    def test_top_profiles_at_most_three(self):
        """top_profiles must not exceed 3 entries."""
        node = _make_node()
        raw = _make_roadmap_output("PT", num_candidates=3)
        node.agent.run_sync.return_value = _result_for(raw)

        ctx = _make_ctx("PT")
        node.process(ctx)

        stored = ctx.nodes["ProposalWriterNode"]["result"]
        assert len(stored.top_profiles) <= 3

    def test_process_returns_task_context(self):
        """process() returns the same TaskContext it received."""
        node = _make_node()
        raw = _make_roadmap_output("PT")
        node.agent.run_sync.return_value = _result_for(raw)

        ctx = _make_ctx("PT")
        result = node.process(ctx)

        assert result is ctx


# ---------------------------------------------------------------------------
# Language paths
# ---------------------------------------------------------------------------


class TestLanguagePT:
    def test_pt_language_passed_to_agent(self):
        """When event.language is PT, the prompt includes language=PT."""
        node = _make_node()
        raw = _make_roadmap_output("PT")
        node.agent.run_sync.return_value = _result_for(raw)

        ctx = _make_ctx("PT")
        node.process(ctx)

        node.agent.run_sync.assert_called_once()
        prompt = node.agent.run_sync.call_args.kwargs["user_prompt"]
        data = json.loads(prompt)
        assert data["language"] == "PT"

    def test_pt_roadmap_has_body_pt_populated(self):
        """A PT-language run produces a roadmap with body_pt set."""
        node = _make_node()
        raw = _make_roadmap_output("PT")
        node.agent.run_sync.return_value = _result_for(raw)

        ctx = _make_ctx("PT")
        node.process(ctx)

        stored = ctx.nodes["ProposalWriterNode"]["result"]
        assert stored.body_pt is not None


class TestLanguageEN:
    def test_en_language_passed_to_agent(self):
        """When event.language is EN, the prompt includes language=EN."""
        node = _make_node()
        raw = _make_roadmap_output("EN")
        node.agent.run_sync.return_value = _result_for(raw)

        ctx = _make_ctx("EN")
        node.process(ctx)

        node.agent.run_sync.assert_called_once()
        prompt = node.agent.run_sync.call_args.kwargs["user_prompt"]
        data = json.loads(prompt)
        assert data["language"] == "EN"

    def test_en_roadmap_has_body_en_populated(self):
        """A EN-language run produces a roadmap with body_en set."""
        node = _make_node()
        raw = _make_roadmap_output("EN")
        node.agent.run_sync.return_value = _result_for(raw)

        ctx = _make_ctx("EN")
        node.process(ctx)

        stored = ctx.nodes["ProposalWriterNode"]["result"]
        assert stored.body_en is not None


# ---------------------------------------------------------------------------
# top_profiles with fewer than 3 candidates
# ---------------------------------------------------------------------------


class TestTopProfilesFewerThanThree:
    def test_one_candidate_gives_one_profile(self):
        """With only one candidate, top_profiles has exactly one entry."""
        node = _make_node()
        raw = _make_roadmap_output("PT", num_candidates=1)
        node.agent.run_sync.return_value = _result_for(raw)

        ctx = _make_ctx("PT")
        # Override the seeded candidates to just one
        one_candidate = _scored_candidate("Invoice Processing", 5.0, 5.0, 4.0)
        ctx.nodes["OpportunityIdentifierNode"] = {
            "result": {
                "candidates": [one_candidate.model_dump()],
                "recommended": "Invoice Processing",
                "situation_notes": "One pain point.",
            }
        }
        node.process(ctx)

        stored = ctx.nodes["ProposalWriterNode"]["result"]
        assert len(stored.top_profiles) == 1

    def test_two_candidates_gives_two_profiles(self):
        """With two candidates, top_profiles has exactly two entries."""
        node = _make_node()
        raw = _make_roadmap_output("PT", num_candidates=2)
        node.agent.run_sync.return_value = _result_for(raw)

        ctx = _make_ctx("PT")
        candidates = [
            _scored_candidate("Invoice Processing", 5.0, 5.0, 4.0),
            _scored_candidate("Inventory Sync", 4.0, 4.0, 4.0),
        ]
        ctx.nodes["OpportunityIdentifierNode"] = {
            "result": {
                "candidates": [c.model_dump() for c in candidates],
                "recommended": "Invoice Processing",
                "situation_notes": "Two pain points.",
            }
        }
        node.process(ctx)

        stored = ctx.nodes["ProposalWriterNode"]["result"]
        assert len(stored.top_profiles) == 2


# ---------------------------------------------------------------------------
# Opportunity output is threaded into the user prompt
# ---------------------------------------------------------------------------


class TestOpportunityOutputPassedToAgent:
    def test_opportunity_output_in_user_prompt(self):
        """The OpportunityIdentifierNode output is serialized into the agent prompt."""
        node = _make_node()
        raw = _make_roadmap_output("PT")
        node.agent.run_sync.return_value = _result_for(raw)

        ctx = _make_ctx("PT")
        node.process(ctx)

        prompt = node.agent.run_sync.call_args.kwargs["user_prompt"]
        data = json.loads(prompt)
        assert "opportunity_output" in data
        # opportunity_output is the raw dict (result key extracted by the node)
        assert "candidates" in data["opportunity_output"]
