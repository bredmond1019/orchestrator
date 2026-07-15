"""query_brain.py — manual semantic-search smoke test for `brain_documents`.

Embeds a natural-language query via the configured `EmbeddingService` (local
Ollama `mxbai-embed-large` by default — see `app/services/embedding_service.py`)
and returns the nearest `brain_documents` rows by cosine distance. This is a
raw-retrieval check only: no keyword fusion, no structural graph expansion, no
LLM answer synthesis. It exists so a human can eyeball retrieval quality right
after `scripts/index_brain.py --rebuild` without standing up the API/Celery
stack and driving the full `DOCUMENT_QA` workflow (see `docs/brain-rag.md` for
that fuller pipeline).

Usage:
    python scripts/query_brain.py "What is the Bastion program?"
    python scripts/query_brain.py "some question" --limit 10 --show-content
"""

import argparse
import re
import sys
from pathlib import Path

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
    from database.brain_document import BrainDocument
    from sqlalchemy import or_

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
    from database.brain_document import BrainDocument

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
    from workflows.document_qa_workflow_nodes.retrieve_chunks_node import (
        RetrieveChunksNode,
    )

    node = RetrieveChunksNode()
    return node.retrieve(query, corpus="brain", k=limit)


def format_hybrid_result(
    rank: int, chunk: dict, *, show_content: bool, content_chars: int
) -> str:
    """Render one `hybrid_search` result dict for terminal display."""
    file_path = chunk.get("file_path") or "(no file_path)"
    header = f"[{rank}] score={chunk['score']:.4f}  {file_path}  via={chunk.get('via', 'semantic')}"
    detail = f"    title: {chunk.get('title') or '(none)'}"
    if chunk.get("section_title"):
        detail += f"  section: {chunk['section_title']}"
    lines = [header, detail]
    if show_content:
        content = chunk.get("content") or ""
        snippet = content[:content_chars].replace("\n", " ")
        ellipsis = "…" if len(content) > content_chars else ""
        lines.append(f"    content: {snippet}{ellipsis}")
    return "\n".join(lines)


def format_result(
    rank: int, doc, distance: float, *, show_content: bool, content_chars: int
) -> str:
    """Render one result row for terminal display."""
    header = f"[{rank}] distance={distance:.4f}  {doc.file_path}"
    detail = f"    title: {doc.title or '(none)'}"
    if doc.section:
        detail += f"  section: {doc.section}"
    lines = [header, detail]
    if show_content:
        content = doc.content or ""
        snippet = content[:content_chars].replace("\n", " ")
        ellipsis = "…" if len(content) > content_chars else ""
        lines.append(f"    content: {snippet}{ellipsis}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    """Entry point for the ad-hoc brain semantic-search CLI."""
    parser = argparse.ArgumentParser(
        description="Semantic search over brain_documents (raw retrieval, no LLM answer synthesis)."
    )
    parser.add_argument("query", help="Natural-language question to embed and search for")
    parser.add_argument(
        "--limit", type=int, default=5, help="Number of results to show (default: 5)"
    )
    parser.add_argument(
        "--show-content",
        action="store_true",
        help="Print a content snippet for each result",
    )
    parser.add_argument(
        "--content-chars",
        type=int,
        default=200,
        help="Snippet length in characters when --show-content is set (default: 200)",
    )
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help=(
            "Use RetrieveChunksNode's keyword+semantic fusion pipeline (the "
            "same ranking the production DOCUMENT_QA workflow produces) "
            "instead of raw cosine-distance semantic search."
        ),
    )
    args = parser.parse_args(argv)

    app_dir = Path(__file__).resolve().parent.parent / "app"
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))

    if args.hybrid:
        chunks = hybrid_search(args.query, limit=args.limit)
        if not chunks:
            print(
                "No results — is brain_documents populated? "
                "Run scripts/index_brain.py --rebuild first."
            )
            return
        for rank, chunk in enumerate(chunks, start=1):
            print(
                format_hybrid_result(
                    rank,
                    chunk,
                    show_content=args.show_content,
                    content_chars=args.content_chars,
                )
            )
            print()
        return

    from database.session import db_session

    session = next(db_session())

    exact_id = find_exact_id(args.query)
    if exact_id is not None:
        id_results = exact_id_lookup(exact_id, session, limit=args.limit)
        if not id_results:
            print(
                f"No exact match for ID '{exact_id}' — is brain_documents populated? "
                "Run scripts/index_brain.py --rebuild first."
            )
            return
        for rank, doc in enumerate(id_results, start=1):
            print(
                format_result(
                    rank,
                    doc,
                    0.0,
                    show_content=args.show_content,
                    content_chars=args.content_chars,
                )
            )
            print()
        return

    from services.embedding_service import EmbeddingService

    embedding_service = EmbeddingService()
    results = semantic_search(args.query, session, embedding_service, limit=args.limit)

    if not results:
        print(
            "No results — is brain_documents populated? "
            "Run scripts/index_brain.py --rebuild first."
        )
        return

    for rank, (doc, distance) in enumerate(results, start=1):
        print(
            format_result(
                rank,
                doc,
                distance,
                show_content=args.show_content,
                content_chars=args.content_chars,
            )
        )
        print()


if __name__ == "__main__":
    main()
