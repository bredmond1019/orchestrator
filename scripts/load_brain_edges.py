"""load_brain_edges.py — mev `emit-graph` JSON -> `brain_edges` table loader.

Reads a `mev emit-graph` v2 payload (see `../mev/docs/cli.md` "Output shape")
and loads its `edges[]` into the `brain_edges` table, reading each edge's
already-resolved `target_node_id`/`target_doc_id` fields directly — mev's
`resolve_edge()` is the single source of truth for edge resolution; this
loader no longer re-resolves `to_ref` itself.

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
_EXPECTED_VERSION = "2"


def validate_payload(payload: dict) -> None:
    """Validate the top-level shape of an emit-graph payload.

    Checks structural shape (required keys present, `nodes`/`edges` are
    lists) and that `version` is the exact schema this loader depends on.
    The loader reads mev's already-resolved `target_node_id`/`target_doc_id`
    edge fields directly (introduced in v2) rather than resolving them
    itself, so a pre-v2 payload — which carries no target fields — would
    otherwise silently load every edge as dangling.

    Args:
        payload: The parsed emit-graph JSON document.

    Raises:
        ValueError: If a required top-level key is missing, if `nodes`/
            `edges` are not lists, or if `version` is not `"2"`.
    """
    missing = [key for key in _REQUIRED_KEYS if key not in payload]
    if missing:
        raise ValueError(f"emit-graph payload missing required key(s): {missing}")
    if not isinstance(payload["nodes"], list):
        raise ValueError("emit-graph payload 'nodes' must be a list")
    if not isinstance(payload["edges"], list):
        raise ValueError("emit-graph payload 'edges' must be a list")
    if payload["version"] != _EXPECTED_VERSION:
        raise ValueError(
            f"emit-graph payload has version {payload['version']!r}; "
            f"this loader requires version {_EXPECTED_VERSION!r} "
            "(resolved target_node_id/target_doc_id edge fields)"
        )


def build_edge_rows(payload: dict) -> list[dict]:
    """Convert every `edges[]` entry in an emit-graph payload into a row dict.

    Each returned dict matches the `BrainEdge` column set and is ready to
    pass as `BrainEdge(**row)`.

    An edge whose `from` does not resolve against `nodes[]` is skipped (and
    logged) — `source_doc_id` is a required column and there is no
    document-shaped data to fall back on. An edge's `target_node_id`/
    `target_doc_id` are read straight off the payload (mev's `emit-graph` v2
    already resolved them via its own `resolve_edge()`); an edge with a
    `null` target is *kept* with those columns `None` (dangling or leaf) —
    per the ingestion contract, unresolved refs are never dropped.

    Args:
        payload: The parsed, already-validated emit-graph JSON document.

    Returns:
        One row dict per resolvable-source edge.
    """
    source_nodes = {node["id"]: node for node in payload["nodes"] if node.get("id")}
    rows: list[dict] = []
    for edge in payload["edges"]:
        from_id = edge.get("from")
        kind = edge.get("kind", "related")

        source_node = source_nodes.get(from_id)
        if source_node is None:
            logger.warning("Skipping edge with unresolvable source node: %s", from_id)
            continue

        rows.append(
            {
                "source_node_id": from_id,
                "source_doc_id": source_node.get("doc_id"),
                "to_ref": edge.get("to_ref"),
                "target_node_id": edge.get("target_node_id"),
                "target_doc_id": edge.get("target_doc_id"),
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
