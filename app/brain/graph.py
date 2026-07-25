"""app/brain/graph.py — the Brain's walk read core (brain_edges BFS).

Extracted independently of `RetrieveChunksNode._resolve_neighbor_doc_ids`
(OR.N1 task 2): the `syn walk` console command needs the same `brain_edges`
neighbor-resolution query shape (`source_doc_id IN <frontier> AND
target_doc_id IS NOT NULL`) that `_structural_expand` uses to widen a
semantic candidate set, but as a standalone, depth-N BFS over the graph
rather than a single-hop candidate-widening step. This module deliberately
does not import or modify `retrieve_chunks_node.py` — that keeps DOCUMENT_QA
ranking byte-identical while this module evolves independently.
"""


def walk(doc_id: str, *, depth: int = 1, session=None) -> dict:
    """BFS-traverse `brain_edges` from `doc_id` out to `depth` hops.

    At each level, resolved (non-dangling) neighbors of the current frontier
    are fetched via `BrainEdge.target_doc_id` where
    `source_doc_id IN <frontier> AND target_doc_id IS NOT NULL` — the same
    filter shape as `RetrieveChunksNode._resolve_neighbor_doc_ids`, authored
    independently here. Neighbors are resolved against `brain_documents` for
    `file_path`/`title` display, deduped against already-visited doc_ids
    (so cycles never revisit a node), and returned as a JSON-serializable
    structure.

    Args:
        doc_id: The root document id to traverse from.
        depth: Maximum number of hops to traverse (default 1).
        session: An open SQLAlchemy session (injected; opened via
            `database.session.db_session` when omitted).

    Returns:
        A dict of the shape:
        `{"root": doc_id, "depth": depth, "levels": [[neighbor_doc_id, ...], ...],
        "nodes": {doc_id: {"doc_id", "file_path", "title"}, ...}}`.
        `levels` has one entry per hop that produced at least one new
        neighbor (traversal stops early once a hop adds nothing new, so a
        doc with no edges returns `levels: []` rather than an error).
    """
    # local import: app/ only on sys.path at call time
    from database.brain_document import BrainDocument  # pylint: disable=import-outside-toplevel
    from database.brain_edge import BrainEdge  # pylint: disable=import-outside-toplevel

    if session is None:
        from database.session import (  # pylint: disable=import-outside-toplevel
            db_session as _db_session,
        )

        session = next(_db_session())

    visited = {doc_id}
    frontier = {doc_id}
    levels: list[list[str]] = []
    nodes: dict[str, dict] = {}

    for _ in range(depth):
        if not frontier:
            break

        edge_rows = (
            session.query(BrainEdge.target_doc_id)
            .filter(BrainEdge.source_doc_id.in_(frontier))
            .filter(BrainEdge.target_doc_id.isnot(None))
            .all()
        )
        neighbor_doc_ids = {
            row.target_doc_id for row in edge_rows if row.target_doc_id not in visited
        }

        if not neighbor_doc_ids:
            break

        docs = (
            session.query(BrainDocument).filter(BrainDocument.doc_id.in_(neighbor_doc_ids)).all()
        )
        docs_by_id = {doc.doc_id: doc for doc in docs}

        level_ids = sorted(neighbor_doc_ids)
        levels.append(level_ids)
        for neighbor_id in level_ids:
            doc = docs_by_id.get(neighbor_id)
            nodes[neighbor_id] = {
                "doc_id": neighbor_id,
                "file_path": getattr(doc, "file_path", None),
                "title": getattr(doc, "title", None),
            }

        visited |= neighbor_doc_ids
        frontier = neighbor_doc_ids

    return {
        "root": doc_id,
        "depth": depth,
        "levels": levels,
        "nodes": nodes,
    }
