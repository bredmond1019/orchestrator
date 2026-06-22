"""ResearchAgentWorkflow — thin-cut company research agent (Project B).

A single-node workflow that takes a company name and produces a structured
research brief (what they do, where they bleed time, one automation hypothesis).

Graph::

    CompanyResearchNode (terminal)

No Celery wiring, no critic/revise loop, no storage/embedding/BrainDocument.
Those belong to the hardened version (Phase 1 B, hardened), deferred until a
real prospect demands more depth.
"""

from core.schema import NodeConfig, WorkflowSchema
from core.workflow import Workflow
from schemas.research_agent_schema import ResearchAgentEventSchema

from workflows.research_agent_workflow_nodes.company_research_node import (
    CompanyResearchNode,
)


class ResearchAgentWorkflow(Workflow):
    """Single-node research agent workflow for the thin-cut deliverable."""

    workflow_schema = WorkflowSchema(
        description=(
            "Thin-cut research agent: given a company name, produce a structured "
            "diagnostic brief (what they do, time sinks, automation hypothesis) "
            "using a raw Anthropic tool-use loop with Tavily web search."
        ),
        event_schema=ResearchAgentEventSchema,
        start=CompanyResearchNode,
        nodes=[
            NodeConfig(
                node=CompanyResearchNode,
                connections=[],
                description=(
                    "Research the company via web search and emit a structured brief."
                ),
            ),
        ],
    )
