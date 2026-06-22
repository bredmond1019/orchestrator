"""ProposalGeneratorWorkflow — diagnostic-aligned client proposal generator (Project C).

Research → structured scored opportunities → PT/EN roadmap → review/revise routing → storage.

Graph::

    ProposalCompanyResearchNode
        → OpportunityIdentifierNode
            → ProposalWriterNode
                → ProposalReviewNode
                    → ProposalReviewRouterNode
                        → StorageNode          (pass branch)
                        → ProposalReviseNode   (revise branch)
                            → StorageNode

The router is marked ``is_router=True``. The revise branch flows strictly to
``StorageNode`` with no loop-back, keeping the DAG acyclic so ``WorkflowValidator``
passes. ``StorageNode`` appears in the nodes list once and is shared by both
branches. Persistence goes through ``GenericRepository`` / ``db_session`` with
no deployment logic in any node.
"""

from core.schema import NodeConfig, WorkflowSchema
from core.workflow import Workflow
from schemas.proposal_generator_schema import ProposalGeneratorEventSchema

from workflows.proposal_generator_workflow_nodes.company_research_node import (
    ProposalCompanyResearchNode,
)
from workflows.proposal_generator_workflow_nodes.opportunity_identifier_node import (
    OpportunityIdentifierNode,
)
from workflows.proposal_generator_workflow_nodes.proposal_review_node import (
    ProposalReviewNode,
)
from workflows.proposal_generator_workflow_nodes.proposal_review_router_node import (
    ProposalReviewRouterNode,
)
from workflows.proposal_generator_workflow_nodes.proposal_revise_node import (
    ProposalReviseNode,
)
from workflows.proposal_generator_workflow_nodes.proposal_writer_node import (
    ProposalWriterNode,
)
from workflows.proposal_generator_workflow_nodes.storage_node import StorageNode


class ProposalGeneratorWorkflow(Workflow):
    """Diagnostic-aligned proposal generator: research → score → write → review → store."""

    workflow_schema = WorkflowSchema(
        description=(
            "Proposal generator: research a client company, score automation "
            "opportunities, produce a PT/EN diagnostic roadmap, review and revise "
            "with router routing, then persist via BrainDocument storage."
        ),
        event_schema=ProposalGeneratorEventSchema,
        start=ProposalCompanyResearchNode,
        nodes=[
            NodeConfig(
                node=ProposalCompanyResearchNode,
                connections=[OpportunityIdentifierNode],
                description=(
                    "Subclass of Project B's CompanyResearchNode — runs the tool-use "
                    "research loop with proposal-specific context and prompt."
                ),
            ),
            NodeConfig(
                node=OpportunityIdentifierNode,
                connections=[ProposalWriterNode],
                description=(
                    "Reads research evidence, scores three automation candidates using "
                    "the binding composite formula, and selects one recommendation."
                ),
            ),
            NodeConfig(
                node=ProposalWriterNode,
                connections=[ProposalReviewNode],
                description=(
                    "Produces the full AutomationRoadmap (four required sections) in "
                    "PT or EN per event.language."
                ),
            ),
            NodeConfig(
                node=ProposalReviewNode,
                connections=[ProposalReviewRouterNode],
                description=(
                    "Validates the roadmap against the five Diagnostic delivery criteria "
                    "and emits a pass/revise verdict."
                ),
            ),
            NodeConfig(
                node=ProposalReviewRouterNode,
                connections=[StorageNode, ProposalReviseNode],
                description="Routes pass → StorageNode, revise → ProposalReviseNode.",
                is_router=True,
            ),
            NodeConfig(
                node=ProposalReviseNode,
                connections=[StorageNode],
                description=(
                    "Addresses review failures and produces the corrected roadmap. "
                    "Flows linearly to StorageNode — no loop-back, DAG stays acyclic."
                ),
            ),
            NodeConfig(
                node=StorageNode,
                connections=[],
                description=(
                    "Embeds and persists the final AutomationRoadmap as a BrainDocument "
                    "via GenericRepository + db_session (no deployment logic)."
                ),
            ),
        ],
    )
