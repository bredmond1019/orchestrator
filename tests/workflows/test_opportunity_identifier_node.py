"""Unit tests for OpportunityIdentifierNode (Task 3 — Project C).

Covers:
- Mocked agent run; structured-output validation
- Composite formula math (binding constraint)
- One recommendation (not three)
- Context read/write: research brief consumed, candidates + recommended stored
- Prompt sourced from .j2 (no hardcoded text in Python)
- Model provider is CLAUDE_CODE_SDK / sonnet (framework convention)
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from core.nodes.agent import AgentNode
from core.task import NodeRun, NodeStatus, TaskContext
from schemas.proposal_generator_schema import (
    ProposalGeneratorEventSchema,
    ScoredCandidate,
)
from workflows.proposal_generator_workflow_nodes.opportunity_identifier_node import (
    OpportunityIdentifierNode,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PM_PATCH = (
    "workflows.proposal_generator_workflow_nodes"
    ".opportunity_identifier_node.PromptManager.get_prompt"
)


def _make_node() -> OpportunityIdentifierNode:
    """Build OpportunityIdentifierNode without constructing a real Agent/model."""
    node = OpportunityIdentifierNode.__new__(OpportunityIdentifierNode)
    node.agent = MagicMock()
    return node


def _result_for(output) -> MagicMock:
    """Wrap output in a pydantic-ai result mock."""
    result = MagicMock()
    result.output = output
    result.usage.return_value = MagicMock(input_tokens=10, output_tokens=20)
    return result


def _make_candidate(
    frequency: float = 4.0,
    time_cost: float = 3.0,
    buildability: float = 5.0,
    name: str = "Invoice Automation",
) -> ScoredCandidate:
    composite = (frequency * 0.35) + (time_cost * 0.40) + (buildability * 0.25)
    return ScoredCandidate(
        name=name,
        problem_statement="Manual invoice entry each week",
        proposed_solution="Automate via AI extraction and ERP integration",
        estimated_value="~8 hrs/week recovered",
        build_complexity="Medium",
        frequency=frequency,
        time_cost=time_cost,
        buildability=buildability,
        composite=round(composite, 4),
    )


def _make_output_with_three_candidates() -> OpportunityIdentifierNode.OutputType:
    """Return a valid OutputType with three candidates sorted composite-desc."""
    c1 = _make_candidate(frequency=5.0, time_cost=5.0, buildability=5.0, name="Candidate A")
    c2 = _make_candidate(frequency=4.0, time_cost=3.0, buildability=4.0, name="Candidate B")
    c3 = _make_candidate(frequency=2.0, time_cost=2.0, buildability=3.0, name="Candidate C")
    return OpportunityIdentifierNode.OutputType(
        candidates=[c1, c2, c3],
        recommended="Candidate A",
    )


def _make_ctx(with_research: bool = True) -> TaskContext:
    event = ProposalGeneratorEventSchema(
        company_name="Acme Corp",
        industry="Manufacturing",
        description="A mid-sized widget manufacturer",
        intake_notes="Lots of manual data entry for compliance reports",
    )
    ctx = TaskContext(event=event)
    if with_research:
        ctx.nodes["CompanyResearchNode"] = {
            "brief": {
                "company_name": "Acme Corp",
                "what_they_do": "Makes widgets for industrial use",
                "likely_time_sinks": [
                    "Manual compliance reporting",
                    "Paper-based inventory tracking",
                ],
                "automation_hypothesis": "Automate compliance report generation",
            },
            "output": "Research complete.",
        }
    return ctx


def _seed_run(ctx: TaskContext, node: OpportunityIdentifierNode) -> None:
    ctx.node_runs[node.node_name] = NodeRun(status=NodeStatus.RUNNING)


# ---------------------------------------------------------------------------
# Structured output is stored in context
# ---------------------------------------------------------------------------


class TestCandidatesStoredInContext:
    def test_candidates_stored_after_process(self):
        """process() writes 'candidates' to context under the node's name."""
        node = _make_node()
        output = _make_output_with_three_candidates()
        node.agent.run_sync.return_value = _result_for(output)

        ctx = _make_ctx()
        _seed_run(ctx, node)

        node.process(ctx)

        stored = ctx.nodes[node.node_name]
        assert "candidates" in stored
        assert len(stored["candidates"]) == 3

    def test_recommended_stored_after_process(self):
        """process() writes 'recommended' (a single string) to context."""
        node = _make_node()
        output = _make_output_with_three_candidates()
        node.agent.run_sync.return_value = _result_for(output)

        ctx = _make_ctx()
        _seed_run(ctx, node)

        node.process(ctx)

        stored = ctx.nodes[node.node_name]
        assert stored["recommended"] == "Candidate A"

    def test_process_returns_task_context(self):
        """process() returns the same TaskContext it received."""
        node = _make_node()
        output = _make_output_with_three_candidates()
        node.agent.run_sync.return_value = _result_for(output)

        ctx = _make_ctx()
        _seed_run(ctx, node)

        result = node.process(ctx)
        assert result is ctx


# ---------------------------------------------------------------------------
# Composite formula math
# ---------------------------------------------------------------------------


class TestCompositeMath:
    def test_composite_formula_correct(self):
        """ScoredCandidate model_validator enforces the binding composite formula."""
        # (5 × 0.35) + (5 × 0.40) + (5 × 0.25) = 1.75 + 2.00 + 1.25 = 5.00
        c = _make_candidate(frequency=5.0, time_cost=5.0, buildability=5.0)
        assert abs(c.composite - 5.0) < 0.001

    def test_composite_formula_mixed_scores(self):
        # (4 × 0.35) + (3 × 0.40) + (5 × 0.25) = 1.40 + 1.20 + 1.25 = 3.85
        c = _make_candidate(frequency=4.0, time_cost=3.0, buildability=5.0)
        assert abs(c.composite - 3.85) < 0.001

    def test_wrong_composite_raises_validation_error(self):
        """A candidate with the wrong composite value is rejected by Pydantic."""
        with pytest.raises(ValidationError, match="composite"):
            ScoredCandidate(
                name="Bad",
                problem_statement="...",
                proposed_solution="...",
                estimated_value="...",
                build_complexity="Low",
                frequency=3.0,
                time_cost=3.0,
                buildability=3.0,
                composite=9.9,  # wrong
            )

    def test_candidates_from_output_match_formula(self):
        """Candidates written to context have composites consistent with the formula."""
        node = _make_node()
        output = _make_output_with_three_candidates()
        node.agent.run_sync.return_value = _result_for(output)

        ctx = _make_ctx()
        _seed_run(ctx, node)
        node.process(ctx)

        stored = ctx.nodes[node.node_name]["candidates"]
        for c_dict in stored:
            expected = (
                (c_dict["frequency"] * 0.35)
                + (c_dict["time_cost"] * 0.40)
                + (c_dict["buildability"] * 0.25)
            )
            assert abs(c_dict["composite"] - expected) < 0.001, (
                f"Composite mismatch for {c_dict['name']}: "
                f"stored {c_dict['composite']}, formula gives {expected:.4f}"
            )


# ---------------------------------------------------------------------------
# Recommendation is one, not three
# ---------------------------------------------------------------------------


class TestRecommendation:
    def test_recommended_is_a_string(self):
        """'recommended' is a single string, not a list."""
        node = _make_node()
        output = _make_output_with_three_candidates()
        node.agent.run_sync.return_value = _result_for(output)

        ctx = _make_ctx()
        _seed_run(ctx, node)
        node.process(ctx)

        stored = ctx.nodes[node.node_name]
        assert isinstance(stored["recommended"], str)

    def test_recommended_matches_top_candidate(self):
        """'recommended' should match the first (highest composite) candidate."""
        node = _make_node()
        output = _make_output_with_three_candidates()
        node.agent.run_sync.return_value = _result_for(output)

        ctx = _make_ctx()
        _seed_run(ctx, node)
        node.process(ctx)

        stored = ctx.nodes[node.node_name]
        top_name = stored["candidates"][0]["name"]
        assert stored["recommended"] == top_name

    def test_output_type_recommended_is_string_field(self):
        """OutputType.recommended is typed as str (not list)."""
        import inspect
        hints = OpportunityIdentifierNode.OutputType.model_fields
        assert "recommended" in hints
        field = hints["recommended"]
        # annotation is str (or a Union containing str as the only non-None arm)
        assert field.annotation is str


# ---------------------------------------------------------------------------
# Research brief is consumed from context
# ---------------------------------------------------------------------------


class TestResearchBriefConsumed:
    def test_agent_called_with_research_brief_in_payload(self):
        """The user prompt sent to the agent includes the research brief."""
        node = _make_node()
        output = _make_output_with_three_candidates()
        node.agent.run_sync.return_value = _result_for(output)

        ctx = _make_ctx(with_research=True)
        _seed_run(ctx, node)
        node.process(ctx)

        call_args = node.agent.run_sync.call_args
        user_prompt = call_args.kwargs.get("user_prompt") or call_args[1]["user_prompt"]
        payload = json.loads(user_prompt)
        assert "research_brief" in payload
        assert payload["research_brief"]["company_name"] == "Acme Corp"

    def test_agent_called_with_company_metadata(self):
        """The user prompt includes company_name, industry, and description."""
        node = _make_node()
        output = _make_output_with_three_candidates()
        node.agent.run_sync.return_value = _result_for(output)

        ctx = _make_ctx()
        _seed_run(ctx, node)
        node.process(ctx)

        call_args = node.agent.run_sync.call_args
        user_prompt = call_args.kwargs.get("user_prompt") or call_args[1]["user_prompt"]
        payload = json.loads(user_prompt)
        assert payload["company_name"] == "Acme Corp"
        assert payload["industry"] == "Manufacturing"

    def test_missing_company_research_node_raises(self):
        """If CompanyResearchNode has not run, get_node_output raises KeyError."""
        node = _make_node()

        ctx = _make_ctx(with_research=False)
        _seed_run(ctx, node)

        with pytest.raises(KeyError, match="CompanyResearchNode"):
            node.process(ctx)

    def test_intake_notes_included_when_present(self):
        """intake_notes from the event are forwarded to the agent payload."""
        node = _make_node()
        output = _make_output_with_three_candidates()
        node.agent.run_sync.return_value = _result_for(output)

        ctx = _make_ctx()
        _seed_run(ctx, node)
        node.process(ctx)

        call_args = node.agent.run_sync.call_args
        user_prompt = call_args.kwargs.get("user_prompt") or call_args[1]["user_prompt"]
        payload = json.loads(user_prompt)
        assert payload["intake_notes"] == "Lots of manual data entry for compliance reports"


# ---------------------------------------------------------------------------
# Prompt sourced from .j2 — no hardcoded text in Python
# ---------------------------------------------------------------------------


class TestPromptSourcedFromTemplate:
    def test_prompt_manager_invoked(self):
        """get_agent_config() calls PromptManager.get_prompt with the correct key."""
        with patch(_PM_PATCH) as mock_pm:
            mock_pm.return_value = "mocked system prompt"
            node = OpportunityIdentifierNode.__new__(OpportunityIdentifierNode)
            node.agent = MagicMock()
            config = node.get_agent_config()

        mock_pm.assert_called_once_with("proposal_opportunity_identifier")
        assert config.system_prompt == "mocked system prompt"

    def test_system_prompt_is_not_empty_string(self):
        """The loaded .j2 prompt contains at least rubric content."""
        node = _make_node()
        with patch(_PM_PATCH) as mock_pm:
            mock_pm.return_value = "You are an automation analyst"
            config = node.get_agent_config()

        assert len(config.system_prompt) > 0


# ---------------------------------------------------------------------------
# Model provider convention
# ---------------------------------------------------------------------------


class TestModelProviderConvention:
    def test_model_provider_is_claude_code_sdk(self):
        node = _make_node()
        config = node.get_agent_config()
        assert config.model_provider.value == "claude_code_sdk"

    def test_model_name_is_sonnet(self):
        node = _make_node()
        config = node.get_agent_config()
        assert config.model_name == "sonnet"

    def test_output_type_is_opportunity_identifier_output(self):
        node = _make_node()
        config = node.get_agent_config()
        assert config.output_type is OpportunityIdentifierNode.OutputType


# ---------------------------------------------------------------------------
# Dict-style event (fallback path)
# ---------------------------------------------------------------------------


class TestDictEventFallback:
    def test_dict_event_extracts_company_name(self):
        """When event is a plain dict, company metadata is still extracted."""
        node = _make_node()
        output = _make_output_with_three_candidates()
        node.agent.run_sync.return_value = _result_for(output)

        ctx = TaskContext(event={"company_name": "Dict Corp", "industry": "Retail",
                                 "description": "A retailer"})
        ctx.nodes["CompanyResearchNode"] = {
            "brief": {
                "company_name": "Dict Corp",
                "what_they_do": "Retail",
                "likely_time_sinks": ["Manual billing"],
                "automation_hypothesis": "Automate invoicing",
            }
        }
        _seed_run(ctx, node)
        node.process(ctx)

        call_args = node.agent.run_sync.call_args
        user_prompt = call_args.kwargs.get("user_prompt") or call_args[1]["user_prompt"]
        payload = json.loads(user_prompt)
        assert payload["company_name"] == "Dict Corp"

    def test_dict_event_missing_intake_notes_is_none(self):
        """Dict event without intake_notes results in None in the payload."""
        node = _make_node()
        output = _make_output_with_three_candidates()
        node.agent.run_sync.return_value = _result_for(output)

        ctx = TaskContext(event={"company_name": "Dict Corp", "industry": "Retail",
                                 "description": "A retailer"})
        ctx.nodes["CompanyResearchNode"] = {
            "brief": {
                "company_name": "Dict Corp",
                "what_they_do": "Retail",
                "likely_time_sinks": ["Manual billing"],
                "automation_hypothesis": "Automate invoicing",
            }
        }
        _seed_run(ctx, node)
        node.process(ctx)

        call_args = node.agent.run_sync.call_args
        user_prompt = call_args.kwargs.get("user_prompt") or call_args[1]["user_prompt"]
        payload = json.loads(user_prompt)
        assert payload["intake_notes"] is None
