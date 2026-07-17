"""DocumentQAWorkflow — grounded Q&A with session memory over ingested documents (Project D).

Embeds the user question, retrieves the most relevant chunks from the ingested
corpus via two-stage hybrid retrieval, and routes on retrieval confidence
(block OR.L): weak or empty retrieval abstains deterministically; confident
retrieval assembles the RAG context alongside prior session turns, generates
a grounded answer, and deterministically verifies its citations. Either
branch persists the new turn to the chat session.

Graph::

    EmbedQuestionNode
        -> RetrieveChunksNode
            -> GroundingRouterNode (router)
                -> AbstainNode -> UpdateSessionMemoryNode
                -> AssembleContextNode -> AnswerNode
                    -> VerifyCitationsNode -> UpdateSessionMemoryNode

``GroundingRouterNode`` routes to ``AbstainNode`` when ``retrieval_confidence``
(from ``RetrieveChunksNode``) falls below ``event.confidence_threshold`` or
zero chunks were retrieved; otherwise it falls through to
``AssembleContextNode``. ``AbstainNode`` makes no LLM call — it writes the
unified answer envelope directly. On the answered branch,
``VerifyCitationsNode`` deterministically checks ``AnswerNode``'s citations
against the retrieved chunks (existence + lexical claim support) and either
completes the envelope (verified/unverified citations, corroboration) or
withholds it (all citations unverified) — no LLM judging involved. Both
branches converge on ``UpdateSessionMemoryNode``, which persists the turn
identically regardless of which terminal node produced the envelope.
"""

from core.schema import NodeConfig, WorkflowSchema
from core.workflow import Workflow
from schemas.document_qa_schema import DocumentQAEventSchema

from workflows.document_qa_workflow_nodes.abstain_node import AbstainNode
from workflows.document_qa_workflow_nodes.answer_node import AnswerNode
from workflows.document_qa_workflow_nodes.assemble_context_node import AssembleContextNode
from workflows.document_qa_workflow_nodes.embed_question_node import EmbedQuestionNode
from workflows.document_qa_workflow_nodes.grounding_router_node import (
    GroundingRouterNode,
)
from workflows.document_qa_workflow_nodes.retrieve_chunks_node import RetrieveChunksNode
from workflows.document_qa_workflow_nodes.update_session_memory_node import (
    UpdateSessionMemoryNode,
)
from workflows.document_qa_workflow_nodes.verify_citations_node import (
    VerifyCitationsNode,
)


class DocumentQAWorkflow(Workflow):
    workflow_schema = WorkflowSchema(
        description=(
            "Document Q&A pipeline: embed question -> two-stage hybrid retrieval -> "
            "confidence-gated abstain router -> assemble RAG context + session memory -> "
            "grounded answer -> deterministic citation verification -> persist turn."
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
                connections=[GroundingRouterNode],
                description=(
                    "Two-stage hybrid retrieval: semantic candidate set -> "
                    "keyword re-rank -> additive score fusion with section-title 2x weight."
                ),
            ),
            NodeConfig(
                node=GroundingRouterNode,
                connections=[AbstainNode, AssembleContextNode],
                description=(
                    "Route to the deterministic abstain path when retrieval "
                    "confidence is below threshold (or zero chunks); else proceed."
                ),
                is_router=True,
            ),
            NodeConfig(
                node=AbstainNode,
                connections=[UpdateSessionMemoryNode],
                description=(
                    "Deterministic no-LLM abstain envelope for weak/empty retrieval."
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
                connections=[VerifyCitationsNode],
                description="Generate grounded answer via Claude (system prompt from .j2).",
            ),
            NodeConfig(
                node=VerifyCitationsNode,
                connections=[UpdateSessionMemoryNode],
                description=(
                    "Deterministically verify each cited section against the "
                    "retrieved chunks (existence + lexical claim support); "
                    "withhold the answer if all citations fail."
                ),
            ),
            NodeConfig(
                node=UpdateSessionMemoryNode,
                connections=[],
                description="Append the new Q&A turn to ChatSession and persist (terminal).",
            ),
        ],
    )
