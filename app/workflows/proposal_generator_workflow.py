"""ProposalGeneratorWorkflow — diagnostic-aligned client proposal generator (Project C).

Research → structured scored opportunities → PT/EN roadmap → review/revise routing → storage.

Graph (wired in Task 7)::

    CompanyResearchNode
        → OpportunityIdentifierNode
        → ProposalWriterNode
        → ProposalReviewNode
        → ProposalReviewRouterNode
            → StorageNode          (pass branch)
            → ReviseNode           (revise branch)
                → StorageNode

The DAG nodes list and connections are filled in Task 7. This module provides
the scaffold stub: event schema registration + minimal WorkflowSchema so the
registries can be wired and the API dispatcher can validate inbound events.
"""

from core.schema import NodeConfig, WorkflowSchema
from core.workflow import Workflow
from schemas.proposal_generator_schema import ProposalGeneratorEventSchema

from workflows.proposal_generator_workflow_nodes.initial_node import InitialNode


class ProposalGeneratorWorkflow(Workflow):
    """Stub workflow — DAG wired in Task 7."""

    workflow_schema = WorkflowSchema(
        description=(
            "Proposal generator: research a client company, score automation "
            "opportunities, produce a PT/EN diagnostic roadmap, review and revise "
            "with router routing, then persist via BrainDocument storage."
        ),
        event_schema=ProposalGeneratorEventSchema,
        start=InitialNode,
        nodes=[
            NodeConfig(
                node=InitialNode,
                connections=[],
                description="Scaffold placeholder — replaced in Task 7.",
            ),
        ],
    )
