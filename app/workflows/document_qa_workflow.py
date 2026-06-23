"""DocumentQAWorkflow — grounded Q&A with session memory over ingested documents (Project D).

Embeds the user question, retrieves the most relevant chunks from the ingested
corpus via two-stage hybrid retrieval, assembles the RAG context alongside prior
session turns, generates a grounded answer, and persists the new turn to the
chat session.

Graph (linear DAG — no router)::

    EmbedQuestionNode
        -> RetrieveChunksNode
            -> AssembleContextNode
                -> AnswerNode
                    -> UpdateSessionMemoryNode
"""

from core.schema import NodeConfig, WorkflowSchema
from core.workflow import Workflow
from schemas.document_qa_schema import DocumentQAEventSchema

from workflows.document_qa_workflow_nodes.answer_node import AnswerNode
from workflows.document_qa_workflow_nodes.assemble_context_node import AssembleContextNode
from workflows.document_qa_workflow_nodes.embed_question_node import EmbedQuestionNode
from workflows.document_qa_workflow_nodes.retrieve_chunks_node import RetrieveChunksNode
from workflows.document_qa_workflow_nodes.update_session_memory_node import (
    UpdateSessionMemoryNode,
)


class DocumentQAWorkflow(Workflow):
    workflow_schema = WorkflowSchema(
        description=(
            "Document Q&A pipeline: embed question -> two-stage hybrid retrieval -> "
            "assemble RAG context + session memory -> grounded answer -> persist turn."
        ),
        event_schema=DocumentQAEventSchema,
        start=EmbedQuestionNode,
        nodes=[
            NodeConfig(
                node=EmbedQuestionNode,
                connections=[RetrieveChunksNode],
                description="Embed the question text via Voyage.",
            ),
            NodeConfig(
                node=RetrieveChunksNode,
                connections=[AssembleContextNode],
                description=(
                    "Two-stage hybrid retrieval: semantic candidate set -> "
                    "keyword re-rank -> additive score fusion with section-title 2x weight."
                ),
            ),
            NodeConfig(
                node=AssembleContextNode,
                connections=[AnswerNode],
                description=(
                    "Build grounded context (chunk section + relevance score) "
                    "and prepend prior session turns."
                ),
            ),
            NodeConfig(
                node=AnswerNode,
                connections=[UpdateSessionMemoryNode],
                description="Generate grounded answer via Claude (system prompt from .j2).",
            ),
            NodeConfig(
                node=UpdateSessionMemoryNode,
                connections=[],
                description="Append the new Q&A turn to ChatSession and persist (terminal).",
            ),
        ],
    )
