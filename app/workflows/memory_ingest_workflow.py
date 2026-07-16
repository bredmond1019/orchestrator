"""MemoryIngestWorkflow — fast, per-interaction memory extraction (block OR.S).

The first stage of the two-stage memory pipeline (Honcho reference
architecture, D25): extract what happened, what was learned, and any
contradicted facts from a single interaction, then write it to the memory
store. Dream-time deep reasoning across accumulated episodes is a separate
workflow, ``MemoryConsolidationWorkflow`` (Task 4).

Graph (linear DAG — no router)::

    IngestTimeExtractionNode
        -> MemoryWriteNode
"""

from core.schema import NodeConfig, WorkflowSchema
from core.workflow import Workflow
from schemas.memory_schema import MemoryIngestEventSchema

from workflows.memory_ingest_workflow_nodes.ingest_time_extraction_node import (
    IngestTimeExtractionNode,
)
from workflows.memory_ingest_workflow_nodes.memory_write_node import MemoryWriteNode


class MemoryIngestWorkflow(Workflow):
    workflow_schema = WorkflowSchema(
        description=(
            "Fast, per-interaction memory ingest: extract episode summary + "
            "candidate facts from one interaction -> write episode and upsert "
            "facts into the memory store."
        ),
        event_schema=MemoryIngestEventSchema,
        start=IngestTimeExtractionNode,
        nodes=[
            NodeConfig(
                node=IngestTimeExtractionNode,
                connections=[MemoryWriteNode],
                description=(
                    "Extract episode summary, outcome, tags, and candidate facts "
                    "via Claude (system prompt from .j2)."
                ),
            ),
            NodeConfig(
                node=MemoryWriteNode,
                connections=[],
                description=(
                    "Write the AgentEpisode (upserting the owning Peer) and "
                    "upsert the extracted facts as SemanticMemory rows (terminal)."
                ),
            ),
        ],
    )
