"""DocumentQAEventSchema — event payload for the Document Q&A query workflow.

Validates the inbound event for ``POST /events/`` with
``workflow_type="DOCUMENT_QA"``. The schema requires a document id and a
question; the session id defaults to a new UUID if absent so callers can
start a fresh session without generating an id client-side.
"""

from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class DocumentQAEventSchema(BaseModel):
    """Event schema for the Document Q&A query workflow.

    Fields:
        doc_id: The document to answer over (must exist in content_chunks).
        question: The user question text.
        session_id: Q&A session identifier; generated if absent.
        corpus: Corpus to retrieve from — ``"content"`` (content_chunks,
            the default) or ``"brain"`` (brain_documents).
        workspace_id: The D47 workspace name to scope memory retrieval to;
            same string semantics as the brain corpus ``project`` filter.
        peer_id: Optional narrowing to a single entity's memory.
        include_memory: Opt-in gate for surfacing accumulated
            ``SemanticMemory`` facts alongside brain/content retrieval.
        apply_decay: Opt-out gate for the ``authored_at``-based ranking decay
            applied to ``"brain"`` corpus results. Defaults to True; set
            False to reproduce pre-decay ranking exactly (e.g. for a "what
            did we decide in June" query that decay would otherwise
            sabotage).
    """

    doc_id: UUID = Field(..., description="Document to answer over")
    question: str = Field(..., description="The user question")
    session_id: UUID = Field(
        default_factory=uuid4,
        description="Q&A session id; new UUID if absent",
    )
    corpus: str = Field(
        default="content",
        description="'content' or 'brain'",
    )
    filters: dict | None = Field(
        default=None,
        description=(
            "Optional metadata filters for 'brain' corpus retrieval. "
            "Supported keys: 'layer' (array overlap), 'project' (scalar ==), "
            "'status' (scalar ==). Ignored for 'content' corpus."
        ),
    )
    include_archived: bool = Field(
        default=False,
        description=(
            "When False (default), the 'brain' corpus excludes docs with "
            "status='archived' from retrieval. Set True to surface archived "
            "historical context. No effect on the 'content' corpus."
        ),
    )
    expand_structural: bool = Field(
        default=True,
        description=(
            "When True (default), the 'brain' corpus retrieval widens the "
            "Stage-1 semantic candidate set through the 'related:'-neighborhood "
            "of the top hits before keyword re-rank. Set False to disable the "
            "structural expansion stage. No effect on the 'content' corpus."
        ),
    )
    workspace_id: str | None = Field(
        default=None,
        description=(
            "The D47 workspace name to scope memory retrieval to — same "
            "string semantics as the brain corpus 'project' filter. Required "
            "(non-None) alongside include_memory=True for memory retrieval "
            "to run at all."
        ),
    )
    peer_id: str | None = Field(
        default=None,
        description="Optional narrowing of memory retrieval to one entity.",
    )
    include_memory: bool = Field(
        default=False,
        description=(
            "Opt-in gate for surfacing accumulated SemanticMemory facts as a "
            "fourth via='memory' candidate source alongside semantic/"
            "structural/keyword. Requires a non-None workspace_id to take "
            "effect. No effect on the 'content' corpus."
        ),
    )
    apply_decay: bool = Field(
        default=True,
        description=(
            "When True (default), 'brain' corpus results are down-weighted "
            "by authored_at age (gentler than memory's decay — see "
            "RetrieveChunksNode._DOC_DECAY_FACTOR). Set False to reproduce "
            "pre-decay ranking exactly. No effect on the 'content' corpus or "
            "on rows with authored_at=None."
        ),
    )
