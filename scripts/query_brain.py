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
import sys
from pathlib import Path


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
    args = parser.parse_args(argv)

    app_dir = Path(__file__).resolve().parent.parent / "app"
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))

    from database.session import db_session
    from services.embedding_service import EmbeddingService

    embedding_service = EmbeddingService()
    session = next(db_session())
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
