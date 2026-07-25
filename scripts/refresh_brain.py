"""refresh_brain.py — thin shim over app.brain.ops.refresh.

Superseded by `syn refresh` / `app.brain.ops.refresh` (OR.N2), which now hold
the one implementation shared by this script, the `syn` CLI, and
`syn routine refresh`. This module is kept as a stopgap-turned-compat entry
point: `python scripts/refresh_brain.py` still runs both brain freshness
paths in one invocation — the `brain_documents` content corpus
(`index_brain.py`) and the `brain_edges` structural graph
(`mev emit-graph | load_brain_edges.py`) — but the sequencing and edge-reload
logic now live in `app/brain/ops.py`.

Background: confirmed 2026-07-15, `brain_edges` sat at 0 rows through an
actively re-indexed `brain_documents` corpus because nothing ever ran the
edge loader after the initial migration. That is the failure this script
(and now `syn refresh`) closes.

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
import logging
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

# Re-exported for backward compatibility: tests/callers importing
# `refresh_brain.refresh_edges` / `refresh_brain.refresh` still resolve to the
# one implementation in app/brain/ops.py.
from brain.ops import (  # noqa: E402,F401  pylint: disable=wrong-import-position,unused-import
    refresh,
    refresh_edges,
)


def main(argv: list[str] | None = None) -> None:
    """Entry point: delegate to `app.brain.ops.refresh` for both freshness steps."""
    parser = argparse.ArgumentParser(
        description="Refresh both brain freshness paths: brain_documents "
        "(index_brain.py) and brain_edges (mev emit-graph | load_brain_edges.py). "
        "Thin shim over app.brain.ops.refresh — see also `syn refresh`."
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

    logger.info("=== Step 1/2: refreshing brain_documents (index_brain.py) ===")
    result = refresh(rebuild=args.rebuild, dry_run=args.dry_run, brain_path=args.brain_path)

    if args.dry_run:
        logger.info(
            "=== Step 2/2: skipped brain_edges refresh "
            "(--dry-run has no edge-loader equivalent) ==="
        )
        return

    logger.info("=== Step 2/2: refreshing brain_edges (mev emit-graph | load_brain_edges.py) ===")
    logger.info("Loaded %d edge row(s) from emit-graph payload", result["edges"]["loaded"])


if __name__ == "__main__":
    main()
