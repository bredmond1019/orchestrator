"""Tests for the assembled research_agent (Project B) workflow.

Two layers:

* **Structure** — registration, schema wiring, WorkflowValidator, stub removal.
* **Diagnostic alignment** — driving the node with a mocked client that returns
  a ``submit_research_brief`` tool call yields a valid ``ResearchBriefOutput``
  whose ``likely_time_sinks`` is non-empty and all fields are populated.
"""

from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from pydantic import BaseModel, ValidationError

from schemas.research_agent_schema import ResearchAgentEventSchema, ResearchBriefOutput
from workflows.research_agent_workflow import ResearchAgentWorkflow
from workflows.research_agent_workflow_nodes.company_research_node import (
    CompanyResearchNode,
)
from workflows.workflow_registry import WorkflowRegistry

_ANTHROPIC_PATCH = "core.nodes.tool_use.anthropic.Anthropic"
_PM_PATCH = (
    "workflows.research_agent_workflow_nodes.company_research_node.PromptManager.get_prompt"
)


# ---------------------------------------------------------------------------
# Structure tests
# ---------------------------------------------------------------------------


def test_research_agent_registered() -> None:
    """RESEARCH_AGENT maps to ResearchAgentWorkflow in the registry."""
    assert WorkflowRegistry.RESEARCH_AGENT.value is ResearchAgentWorkflow


def test_workflow_schema_wired_to_event_schema() -> None:
    """The workflow schema references the event schema and starts at CompanyResearchNode."""
    schema = ResearchAgentWorkflow.workflow_schema
    assert schema.event_schema is ResearchAgentEventSchema
    assert schema.start is CompanyResearchNode


def test_event_schema_is_pydantic_model() -> None:
    """ResearchAgentEventSchema is a Pydantic BaseModel subclass."""
    assert issubclass(ResearchAgentEventSchema, BaseModel)


def test_event_schema_fields_and_defaults() -> None:
    """The event schema requires company_name and defaults artifact_id and timestamp."""
    event = ResearchAgentEventSchema(company_name="Acme Corp")
    assert event.company_name == "Acme Corp"
    assert isinstance(event.artifact_id, UUID)
    assert event.timestamp.tzinfo is not None
    with pytest.raises(ValidationError):
        ResearchAgentEventSchema()


def test_workflow_validates_and_builds_node_map() -> None:
    """The assembled workflow passes WorkflowValidator and registers the node."""
    with patch(_ANTHROPIC_PATCH):
        workflow = ResearchAgentWorkflow()
    assert CompanyResearchNode in workflow.nodes


def test_initial_scaffold_node_removed() -> None:
    """The scaffold InitialNode module is deleted and no longer importable."""
    with pytest.raises(ImportError):
        __import__(
            "workflows.research_agent_workflow_nodes.initial_node",
            fromlist=["InitialNode"],
        )


def test_graph_is_single_terminal_node() -> None:
    """WorkflowValidator passes: single-node graph with no connections (terminal)."""
    with patch(_ANTHROPIC_PATCH):
        workflow = ResearchAgentWorkflow()
    workflow.validator.validate()


def test_workflow_description_filled() -> None:
    """The workflow carries a non-empty description."""
    assert ResearchAgentWorkflow.workflow_schema.description
    assert ResearchAgentWorkflow.workflow_schema.description.strip() != ""


def test_single_node_has_no_connections() -> None:
    """CompanyResearchNode is the only node and has no downstream connections."""
    configs = {nc.node: nc for nc in ResearchAgentWorkflow.workflow_schema.nodes}
    assert configs[CompanyResearchNode].connections == []


# ---------------------------------------------------------------------------
# Diagnostic alignment test
# ---------------------------------------------------------------------------


def _tool_use_response(tool_id: str, name: str, tool_input: dict):
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = tool_input
    r = MagicMock()
    r.stop_reason = "tool_use"
    r.content = [block]
    r.usage = MagicMock(input_tokens=10, output_tokens=20)
    return r


def _end_turn_response():
    r = MagicMock()
    r.stop_reason = "end_turn"
    r.content = []
    r.usage = MagicMock(input_tokens=5, output_tokens=5)
    return r


def test_diagnostic_alignment_brief_valid_and_non_empty() -> None:
    """Driving the node with a mocked submit_research_brief call yields valid output.

    Satisfies notes.md §2 test constraint (scaled to thin-cut schema):
    - ResearchBriefOutput is populated with non-empty likely_time_sinks
    - all required fields are present
    """
    brief_payload = {
        "company_name": "Initech",
        "what_they_do": "Mid-market B2B SaaS for project management",
        "likely_time_sinks": [
            "Manual weekly status report compilation",
            "Client onboarding spreadsheet handoff",
            "Ad-hoc invoice reconciliation",
        ],
        "automation_hypothesis": (
            "Automating the weekly status report aggregation via API integration "
            "could recover 6+ hours per PM per week"
        ),
    }

    with patch(_ANTHROPIC_PATCH) as mock_cls, patch(_PM_PATCH, return_value="mocked prompt"):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.side_effect = [
            _tool_use_response("id1", "submit_research_brief", brief_payload),
            _end_turn_response(),
        ]

        workflow = ResearchAgentWorkflow()
        ctx = workflow.run({"company_name": "Initech"})

    # The node should have stored the brief output
    stored = ctx.get_node_output("CompanyResearchNode")
    assert stored is not None
    # The structured brief is stored under 'brief'; 'output' is the text
    # extracted by the parent ToolUseNode.process at loop end.
    assert "brief" in stored, f"Expected 'brief' key in stored output, got: {stored}"

    brief = ResearchBriefOutput(**stored["brief"])

    # Diagnostic alignment assertions
    assert brief.company_name == "Initech"
    assert brief.what_they_do
    assert len(brief.likely_time_sinks) >= 1, "likely_time_sinks must be non-empty"
    assert brief.automation_hypothesis
    # All fields populated (no empty strings)
    assert brief.what_they_do.strip() != ""
    assert brief.automation_hypothesis.strip() != ""
    assert all(s.strip() != "" for s in brief.likely_time_sinks)
