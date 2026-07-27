"""Response schemas for the GET /recall, /walk, /pulse endpoints (OR.Q2).

These are pure serialization mirrors of the ``app/brain/`` read core's
existing return shapes — ``retrieval.recall()``, ``graph.walk()``, and
``pulse.pulse().to_dict()`` — not a new shape. Do not add a ``workspace``
field anywhere; wiring ``recall()``'s ``workspace`` argument to the HTTP
surface is explicitly out of scope for this block.
"""

from pydantic import BaseModel, Field


class RecallResult(BaseModel):
    """One normalized result row, matching `app/brain/retrieval.py::_normalize_doc_row`."""

    doc_id: str | None = Field(..., description="Structured doc id, or None if unset")
    file_path: str = Field(..., description="Corpus-relative source file path")
    title: str | None = Field(..., description="OKF frontmatter title, or None if unset")
    section: str | None = Field(..., description="Section label, or None if whole-document")
    content: str = Field(..., description="Chunk or document content")
    score: float = Field(..., description="Distance/relevance score (0.0 for exact-id matches)")
    via: str = Field(..., description="Retrieval path: exact-id, semantic, or hybrid")


class RecallResponse(BaseModel):
    """Success response body for `GET /recall`."""

    query: str = Field(..., description="Echoes the query string that was searched")
    count: int = Field(..., description="Number of results returned")
    results: list[RecallResult] = Field(..., description="Normalized recall results")


class WalkNode(BaseModel):
    """One resolved neighbor node, matching `app/brain/graph.py::walk`'s `nodes` entries."""

    doc_id: str = Field(..., description="Neighbor document id")
    file_path: str | None = Field(..., description="Neighbor's source file path, or None")
    title: str | None = Field(..., description="Neighbor's OKF title, or None")


class WalkResponse(BaseModel):
    """Success response body for `GET /walk`, matching `app/brain/graph.py::walk`'s return."""

    root: str = Field(..., description="The root doc_id traversal started from")
    depth: int = Field(..., description="Maximum hop count requested")
    levels: list[list[str]] = Field(
        ..., description="One entry per hop that produced new neighbors; empty if no edges"
    )
    nodes: dict[str, WalkNode] = Field(..., description="Resolved neighbor nodes keyed by doc_id")


class PulseResponse(BaseModel):
    """Success response body for `GET /pulse`, mirroring `app/brain/pulse.py::PulseReport`."""

    pgvector_reachable: bool = Field(..., description="Whether pgvector responded to the probe")
    embedding_reachable: bool = Field(..., description="Whether the embedding backend responded")
    embedding_error: str | None = Field(..., description="Embedding probe error, or None")
    brain_documents_count: int = Field(..., description="Live row count of brain_documents")
    brain_edges_count: int = Field(..., description="Live row count of brain_edges")
    max_indexed_at: str | None = Field(
        ..., description="Most recent brain_documents.indexed_at, ISO-8601 or None"
    )
    max_authored_at: str | None = Field(
        ..., description="Most recent brain_documents.authored_at, ISO-8601 or None"
    )
    edges_empty_but_related_exists: bool = Field(
        ..., description="True if brain_edges is empty but related frontmatter exists"
    )
    healthy: bool = Field(..., description="Overall health verdict")
    errors: list[str] = Field(..., description="Collected probe error messages")
