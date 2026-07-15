"""refresh_brain.py — one-shot wrapper running both brain freshness paths.

Stopgap until Block J (`OR.J`) wires this into a cron / `bastion brain reindex`.
Runs `index_brain.py` (the `brain_documents` content corpus) and then
`mev emit-graph | load_brain_edges.py` (the `brain_edges` structural graph
consumed by `RetrieveChunksNode`'s structural-expansion stage), in that order,
so the two never drift out of sync again. They are otherwise two independent
scripts with no shared entry point — confirmed 2026-07-15: `brain_edges` sat
at 0 rows through an actively re-indexed `brain_documents` corpus because
nothing ever ran the edge loader after the initial migration.

This script runs from the CLI — it is NOT a workflow node and is NOT run by
Celery. Requires the `mev` CLI on `PATH` for the edge-refresh step.

Usage:
    python scripts/refresh_brain.py [--brain-path PATH] [--rebuild] [--dry-run]

Args:
    --brain-path PATH    Path to the brain repo root (the directory holding
                         brain.toml). Defaults to the nearest ancestor of this
                         script that contains brain.toml. Forwarded to both steps.
    --rebuild            Forwarded to index_brain.py: drop all non-diagnostic
                         rows and re-index from scratch. brain_edges has no
                         rebuild distinction — every run is a full reload.
    --dry-run            Forwarded to index_brain.py only. brain_edges has no
                         dry-run mode, so the edge-refresh step is skipped
                         entirely when set (nothing would be written either way).
"""

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger(__name__)

SCRIPTS_DIR = Path(__file__).resolve().parent
APP_DIR = SCRIPTS_DIR.parent / "app"
for _path in (SCRIPTS_DIR, APP_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


def refresh_edges(brain_path: Path) -> int:
    """Run `mev emit-graph --json <brain_path>` and load the payload into brain_edges.

    Args:
        brain_path: Path to the brain repo root to crawl.

    Returns:
        The number of edge rows loaded.
    """
    from load_brain_edges import load_edges  # local import: scripts/ only on sys.path at call time

    result = subprocess.run(
        ["mev", "emit-graph", "--json", str(brain_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    from database.session import db_session  # local import: app/ only on sys.path at call time

    with next(db_session()) as session:  # type: ignore[arg-type]
        return load_edges(payload, session)


def main(argv: list[str] | None = None) -> None:
    """Entry point: run index_brain.py, then refresh brain_edges, in sequence."""
    import index_brain  # local import: scripts/ only on sys.path at call time

    parser = argparse.ArgumentParser(
        description="Refresh both brain freshness paths: brain_documents "
        "(index_brain.py) and brain_edges (mev emit-graph | load_brain_edges.py)."
    )
    parser.add_argument(
        "--brain-path",
        default=None,
        metavar="PATH",
        help="Path to the brain repo root (default: nearest ancestor with brain.toml)",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Forwarded to index_brain.py: delete all non-diagnostic rows and re-index "
        "from scratch",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Forwarded to index_brain.py only; skips the brain_edges refresh step entirely",
    )
    args = parser.parse_args(argv)

    index_argv = []
    if args.brain_path:
        index_argv += ["--brain-path", args.brain_path]
    if args.rebuild:
        index_argv.append("--rebuild")
    if args.dry_run:
        index_argv.append("--dry-run")

    logger.info("=== Step 1/2: refreshing brain_documents (index_brain.py) ===")
    index_brain.main(index_argv)

    if args.dry_run:
        logger.info(
            "=== Step 2/2: skipped brain_edges refresh (--dry-run has no edge-loader equivalent) ==="
        )
        return

    logger.info("=== Step 2/2: refreshing brain_edges (mev emit-graph | load_brain_edges.py) ===")
    brain_path = Path(args.brain_path) if args.brain_path else index_brain._DEFAULT_BRAIN_PATH
    count = refresh_edges(brain_path)
    logger.info("Loaded %d edge row(s) from emit-graph payload", count)


if __name__ == "__main__":
    main()
