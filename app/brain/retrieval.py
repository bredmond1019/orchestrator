"""app/brain/retrieval.py — the Brain's recall read core (exact-id, semantic, hybrid).

Extracted out of ``scripts/query_brain.py`` (OR.N1, CLAUDE.md rule 10 — extract
on the second consumer) once both the manual `query_brain.py` smoke-test CLI
and the new `syn recall` console command needed the same
exact-id / semantic / hybrid search paths. Behavior is byte-for-byte identical
to the original script functions; only the module changed. Display formatting
(`format_result` / `format_hybrid_result`) stays in `scripts/query_brain.py` —
it is not part of the read core.
"""

import re

# Matches structured brain identifiers like "D20", "OR.V", "MV.3B.Q": one to
# five uppercase letters, followed by either a run of digits (D20) or one or
# more dot-separated alphanumeric segments (OR.V, MV.3B.Q). Requiring digits
# or a dot segment (rather than bare letters) keeps this from matching
# ordinary capitalized words like "I" or "What".
ID_PATTERN = re.compile(r"\b[A-Z]{1,5}(?:[0-9]{1,4}|(?:\.[A-Z0-9]{1,5})+)\b")


def find_exact_id(query: str) -> str | None:
    """Return the first structured-ID token in `query`, or None if absent.

    Recognizes bare codes such as `D20`, `OR.V`, `MV.3B.Q` — identifiers that
    embeddings don't reliably encode as semantically distinct from ordinary
    prose (see planning/ticket-brain-retrieval-improvements/tasks.md Finding B).
    """
    match = ID_PATTERN.search(query)
    return match.group(0) if match else None


def exact_id_lookup(id_str: str, session, limit: int = 5) -> list:
    """Resolve `id_str` via a deterministic doc_id/file_path ILIKE lookup.

    Args:
        id_str: The structured ID token (e.g. "D20") to look up.
        session: An open SQLAlchemy session (injected by the caller).
        limit: Maximum number of rows to return.

    Returns:
        A list of `BrainDocument` rows matching `id_str` in either `doc_id`
        or `file_path`, most-relevant first (doc_id exact-ish matches before
        file_path substring matches).
    """
    # local import: app/ only on sys.path at call time
    from database.brain_document import BrainDocument  # pylint: disable=import-outside-toplevel
    from sqlalchemy import or_  # pylint: disable=import-outside-toplevel

    pattern = f"%{id_str}%"
    return (
        session.query(BrainDocument)
        .filter(or_(BrainDocument.doc_id.ilike(pattern), BrainDocument.file_path.ilike(pattern)))
        .limit(limit)
        .all()
    )


def semantic_search(query: str, session, embedding_service, limit: int = 5) -> list[tuple]:
    """Embed `query` and return the `limit` nearest `BrainDocument` rows.

    Args:
        query: Natural-language question to embed and search for.
        session: An open SQLAlchemy session (injected by the caller via
            `database.session.db_session` — never constructed here).
        embedding_service: An `EmbeddingService` instance (injected so tests
            can substitute a fake without a live Ollama/Voyage call).
        limit: Maximum number of rows to return.

    Returns:
        A list of `(BrainDocument, distance)` tuples ordered nearest-first
        (cosine distance — 0.0 is identical, larger is less similar).
    """
    # local import: app/ only on sys.path at call time
    from database.brain_document import BrainDocument  # pylint: disable=import-outside-toplevel

    vector = embedding_service.embed_text(query)
    distance = BrainDocument.embedding.cosine_distance(vector).label("distance")
    return session.query(BrainDocument, distance).order_by(distance).limit(limit).all()


def hybrid_search(query: str, limit: int = 5) -> list[dict]:
    """Run RetrieveChunksNode's keyword+semantic fusion pipeline over the brain corpus.

    Reuses the production `_keyword_search_fts` + `_fuse_and_rank` logic
    (`app/workflows/document_qa_workflow_nodes/retrieve_chunks_node.py`)
    instead of the raw cosine-distance-only `semantic_search` above, so a
    manual test session sees the same ranking the production `DOCUMENT_QA`
    workflow would produce.

    Args:
        query: Natural-language question to search for.
        limit: Maximum number of fused results to return (`k`).

    Returns:
        A list of up to `limit` normalized chunk dicts (see
        `RetrieveChunksNode._fuse_and_rank`), sorted by fused score
        descending.
    """
    # local import: app/ only on sys.path at call time
    from workflows.document_qa_workflow_nodes.retrieve_chunks_node import (  # pylint: disable=import-outside-toplevel
        RetrieveChunksNode,
    )

    node = RetrieveChunksNode()
    return node.retrieve(query, corpus="brain", k=limit)


def _normalize_doc_row(doc, distance: float) -> dict:
    """Normalize a `(BrainDocument, distance)` result into a plain dict."""
    return {
        "doc_id": getattr(doc, "doc_id", None),
        "file_path": doc.file_path,
        "title": doc.title,
        "section": doc.section,
        "content": doc.content,
        "score": distance,
        "via": "exact-id" if distance == 0.0 else "semantic",
    }


def recall(  # pylint: disable=unused-argument
    query: str,
    *,
    limit: int = 5,
    hybrid: bool = False,
    workspace: str | None = None,
    session=None,
    embedding_service=None,
) -> list[dict]:
    """Dispatch exact-id -> semantic/hybrid exactly as `query_brain.main()` does.

    A single typed entry point so the `syn recall` CLI and (later) MCP tools
    share one implementation with the manual `query_brain.py` script instead
    of reimplementing the exact-id / semantic / hybrid dispatch order.

    Args:
        query: Natural-language question (or a bare structured ID) to search.
        limit: Maximum number of results to return.
        hybrid: When True, use `hybrid_search` (RetrieveChunksNode fusion)
            instead of the raw exact-id / semantic-search dispatch.
        workspace: Optional workspace name to scope results to a `project`.
            Left unapplied when unset so default behavior is unchanged;
            resolution to a concrete filter is deferred to the CLI layer.
        session: An open SQLAlchemy session (injected; opened via
            `database.session.db_session` when omitted and not `hybrid`).
        embedding_service: An `EmbeddingService` instance (injected; built
            lazily when omitted and needed).

    Returns:
        A list of normalized result dicts with `doc_id`, `file_path`,
        `title`, `section`, `content`, `score`, and `via` keys.
    """
    if hybrid:
        return hybrid_search(query, limit=limit)

    owns_session = session is None
    if owns_session:
        from database.session import (  # pylint: disable=import-outside-toplevel
            db_session as _db_session,
        )

        session = next(_db_session())

    exact_id = find_exact_id(query)
    if exact_id is not None:
        id_results = exact_id_lookup(exact_id, session, limit=limit)
        return [_normalize_doc_row(doc, 0.0) for doc in id_results]

    if embedding_service is None:
        from services.embedding_service import (  # pylint: disable=import-outside-toplevel
            EmbeddingService,
        )

        embedding_service = EmbeddingService()

    results = semantic_search(query, session, embedding_service, limit=limit)
    return [_normalize_doc_row(doc, distance) for doc, distance in results]
