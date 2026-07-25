"""query_brain.py — manual semantic-search smoke test for `brain_documents`.

Embeds a natural-language query via the configured `EmbeddingService` (local
Ollama `mxbai-embed-large` by default — see `app/services/embedding_service.py`)
and returns the nearest `brain_documents` rows by cosine distance. This is a
raw-retrieval check only: no keyword fusion, no structural graph expansion, no
LLM answer synthesis. It exists so a human can eyeball retrieval quality right
after `scripts/index_brain.py --rebuild` without standing up the API/Celery
stack and driving the full `DOCUMENT_QA` workflow (see `docs/brain-rag.md` for
that fuller pipeline).

This script is a thin caller over the extracted `app/brain/retrieval.py` read
core (OR.N1, CLAUDE.md rule 10 — extract on the second consumer): the
exact-id / semantic / hybrid search functions live there and are re-exported
here so `main()` and existing callers/tests keep working unchanged. Only the
`main()` CLI and the `format_*` display helpers (not part of the read core)
stay in this script.

Usage:
    python scripts/query_brain.py "What is the Bastion program?"
    python scripts/query_brain.py "some question" --limit 10 --show-content
"""

import argparse
import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from brain.retrieval import (  # noqa: E402
    ID_PATTERN,  # noqa: F401 - re-exported for callers importing from this module
    exact_id_lookup,
    find_exact_id,
    hybrid_search,
    semantic_search,
)


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
