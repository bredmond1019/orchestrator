"""load_brain_edges.py — mev `emit-graph` JSON -> `brain_edges` table loader.

Reads a `mev emit-graph` payload (see `../mev/docs/cli.md` "Output shape") and
loads its `edges[]` into the `brain_edges` table, resolving each edge's raw
`to_ref` against the payload's `nodes[]` list.

This script runs from the CLI — it is NOT a workflow node and is NOT run by
Celery. Persistence is injected via `database.session.db_session` (CLAUDE.md
rule 7 — no hardcoded connection), mirroring `scripts/index_brain.py`.

Usage:
    mev emit-graph ~/Dev/agentic-portfolio | python scripts/load_brain_edges.py
    python scripts/load_brain_edges.py --input graph.json

Args:
    --input PATH    Path to an emit-graph JSON payload. Defaults to reading
                    the payload from stdin.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

_REQUIRED_KEYS: tuple[str, ...] = ("version", "nodes", "edges")


def validate_payload(payload: dict) -> None:
    """Validate the top-level shape of an emit-graph payload.

    Checks only structural shape (required keys present, `nodes`/`edges` are
    lists) — it does not validate `version` against a specific value, so a
    future schema-version bump on mev's side does not break this loader.

    Args:
        payload: The parsed emit-graph JSON document.

    Raises:
        ValueError: If a required top-level key is missing, or if `nodes`/
            `edges` are not lists.
    """
    missing = [key for key in _REQUIRED_KEYS if key not in payload]
    if missing:
        raise ValueError(f"emit-graph payload missing required key(s): {missing}")
    if not isinstance(payload["nodes"], list):
        raise ValueError("emit-graph payload 'nodes' must be a list")
    if not isinstance(payload["edges"], list):
        raise ValueError("emit-graph payload 'edges' must be a list")


def build_node_maps(nodes: list[dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    """Build the two resolution maps used to resolve `edges[].to_ref` entries.

    Args:
        nodes: The payload's `nodes[]` list — each a
            `{id, scope, doc_id, rel}` dict.

    Returns:
        A `(id_map, doc_id_map)` pair: `id_map` keys nodes by their canonical
        `scope:doc_id` id; `doc_id_map` keys nodes by their bare `doc_id`. If
        two nodes share a bare `doc_id` across different scopes, the later
        node (in payload walk order) wins in `doc_id_map` — a documented
        last-write-wins choice, not a silent one, since bare-ref collisions
        across scopes are expected to be rare and `id_map` remains
        unambiguous for already-scoped refs.
    """
    id_map: dict[str, dict] = {}
    doc_id_map: dict[str, dict] = {}
    for node in nodes:
        node_id = node.get("id")
        doc_id = node.get("doc_id")
        if node_id:
            id_map[node_id] = node
        if doc_id:
            doc_id_map[doc_id] = node
    return id_map, doc_id_map


def resolve_ref(
    to_ref: str, id_map: dict[str, dict], doc_id_map: dict[str, dict]
) -> dict | None:
    """Resolve a raw `edges[].to_ref` entry against the node maps.

    An already-scoped ref (contains `:`) matches by canonical id; a bare ref
    matches by `doc_id`. Never raises — an unresolvable ref returns `None`
    so the caller can store the edge as dangling instead of dropping it.

    Args:
        to_ref: The raw authored `related:` entry (bare `doc_id` or
            already-scoped `scope:doc_id`).
        id_map: Canonical-id -> node map from `build_node_maps`.
        doc_id_map: Bare-doc_id -> node map from `build_node_maps`.

    Returns:
        The matching node dict, or `None` if `to_ref` resolves to nothing.
    """
    if ":" in to_ref:
        return id_map.get(to_ref)
    return doc_id_map.get(to_ref)


def build_edge_rows(payload: dict) -> list[dict]:
    """Resolve every `edges[]` entry in an emit-graph payload into a row dict.

    Each returned dict matches the `BrainEdge` column set and is ready to
    pass as `BrainEdge(**row)`.

    An edge whose `from` does not resolve against `nodes[]` is skipped (and
    logged) — `source_doc_id` is a required column and there is no
    document-shaped data to fall back on. An edge whose `to_ref` does not
    resolve is *kept* with `target_node_id`/`target_doc_id` left `None`
    (dangling) — per the ingestion contract, unresolved refs are never
    dropped or treated as an error.

    Args:
        payload: The parsed, already-validated emit-graph JSON document.

    Returns:
        One row dict per resolvable-source edge.
    """
    id_map, doc_id_map = build_node_maps(payload["nodes"])
    rows: list[dict] = []
    for edge in payload["edges"]:
        from_id = edge.get("from")
        to_ref = edge.get("to_ref")
        kind = edge.get("kind", "related")

        source_node = id_map.get(from_id)
        if source_node is None:
            logger.warning("Skipping edge with unresolvable source node: %s", from_id)
            continue

        target_node = resolve_ref(to_ref, id_map, doc_id_map) if to_ref else None

        rows.append(
            {
                "source_node_id": from_id,
                "source_doc_id": source_node.get("doc_id"),
                "to_ref": to_ref,
                "target_node_id": target_node.get("id") if target_node else None,
                "target_doc_id": target_node.get("doc_id") if target_node else None,
                "kind": kind,
                "scope": source_node.get("scope"),
            }
        )
    return rows


def load_edges(payload: dict, session) -> int:
    """Load an emit-graph payload's edges into `brain_edges`, idempotently.

    Validates the payload, resolves every edge into a row, then clears the
    table and reinserts the resolved rows inside the caller's session/
    transaction. Clear-then-reload (rather than a per-row upsert) makes a
    re-run over an unchanged payload produce an identical row set instead of
    duplicates, trading a moment of empty-table visibility mid-transaction
    for a much simpler idempotency story — acceptable because `brain_edges`
    is a read-only derived index, never a source of truth.

    Args:
        payload: The parsed emit-graph JSON document.
        session: An open SQLAlchemy session (injected by the caller via
            `database.session.db_session` — never constructed here).

    Returns:
        The number of edge rows loaded.
    """
    from database.brain_edge import BrainEdge  # local import: app/ only on sys.path at call time

    validate_payload(payload)
    rows = build_edge_rows(payload)

    session.query(BrainEdge).delete(synchronize_session=False)
    for row in rows:
        session.add(BrainEdge(**row))
    session.commit()
    return len(rows)


def _read_payload(input_path: str | None) -> dict:
    """Read and parse the emit-graph JSON payload from a file or stdin."""
    if input_path:
        text = Path(input_path).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    return json.loads(text)


def main(argv: list[str] | None = None) -> None:
    """Entry point for the `brain_edges` loader."""
    parser = argparse.ArgumentParser(
        description="Load a mev emit-graph JSON payload into the brain_edges table."
    )
    parser.add_argument(
        "--input",
        default=None,
        metavar="PATH",
        help="Path to an emit-graph JSON payload (default: read from stdin)",
    )
    args = parser.parse_args(argv)

    # Set up sys.path for imports from app/ (mirrors scripts/index_brain.py).
    app_dir = Path(__file__).resolve().parent.parent / "app"
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))

    from database.session import db_session

    payload = _read_payload(args.input)

    with next(db_session()) as session:  # type: ignore[arg-type]
        count = load_edges(payload, session)

    logger.info("Loaded %d edge row(s) from emit-graph payload", count)


if __name__ == "__main__":
    main()
