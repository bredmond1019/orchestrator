"""MemoryConsolidationWorkflow — dream-time consolidation (block OR.S, Task 4).

The second stage of the two-stage memory pipeline (Honcho reference
architecture, D25): deep reasoning across a peer's (or every peer's, in a
workspace) recently accumulated episodes and current facts to distill
durable ``SemanticMemory`` rows, resolve contradictions, and refresh
``Peer.representation``. Fast, per-interaction extraction is the separate
``MemoryIngestWorkflow`` (Task 3).

**D35 (frontier-only rule):** this workflow's ``ConsolidationNode`` must stay
on Claude, never a local model — see the guard docstring and pinned
``model_provider`` in ``memory_consolidation_workflow_nodes/consolidation_node.py``.

*Scheduling* the nightly consolidation run (Celery beat/cron) is deployment
config and explicitly out of scope for this block (design decision 5) — this
workflow is only ever event-dispatched, the same as every other workflow in
this repo.

Graph (linear DAG — no router)::

    LoadMemoryContextNode
        -> ConsolidationNode
        -> ConsolidationWriteNode
"""

from core.schema import NodeConfig, WorkflowSchema
from core.workflow import Workflow
from schemas.memory_schema import MemoryConsolidationEventSchema

from workflows.memory_consolidation_workflow_nodes.consolidation_node import ConsolidationNode
from workflows.memory_consolidation_workflow_nodes.consolidation_write_node import (
    ConsolidationWriteNode,
)
from workflows.memory_consolidation_workflow_nodes.load_memory_context_node import (
    LoadMemoryContextNode,
)


class MemoryConsolidationWorkflow(Workflow):
    workflow_schema = WorkflowSchema(
        description=(
            "Dream-time consolidation: reason deeply across a peer's (or every "
            "peer's) recent episodes and current facts to distill durable "
            "memory, resolve contradictions, and refresh the peer's "
            "representation. Claude only (D35)."
        ),
        event_schema=MemoryConsolidationEventSchema,
        start=LoadMemoryContextNode,
        nodes=[
            NodeConfig(
                node=LoadMemoryContextNode,
                connections=[ConsolidationNode],
                description=(
                    "Load recent episodes, current facts, and prior representation "
                    "for every peer in scope."
                ),
            ),
            NodeConfig(
                node=ConsolidationNode,
                connections=[ConsolidationWriteNode],
                description=(
                    "Deep, per-peer consolidation pass via Claude (system prompt "
                    "from .j2): durable facts, contradiction resolutions, refreshed "
                    "representation."
                ),
            ),
            NodeConfig(
                node=ConsolidationWriteNode,
                connections=[],
                description=(
                    "Write the consolidated facts (never-overwrite contradiction "
                    "rule) and refresh each peer's representation (terminal)."
                ),
            ),
        ],
    )
