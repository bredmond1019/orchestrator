"""app/brain/cli.py — the `syn` console-script dispatcher (recall, walk, pulse).

Registered as the `syn` console script (`[project.scripts]` in
`pyproject.toml`, `syn = "app.brain.cli:main"`), mirroring `createworkflow`.
Wires the three OR.N1 read cores (`brain.retrieval.recall`, `brain.graph.walk`,
`brain.pulse.pulse`) behind short, deterministic, agent-callable verbs (D52):
`--json` on every command emits a machine-parseable payload and nothing else
on stdout, exit codes are deterministic (0 success; non-zero on an unhealthy
`pulse` verdict or a typed `--workspace` resolution error), and there are no
interactive prompts anywhere. Mirrors `scripts/query_brain.py`'s `sys.path`
shim so imports resolve identically whether `syn` is invoked as the console
script or as `python -m app.brain.cli`.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent.parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))


def _build_parser() -> argparse.ArgumentParser:
    """Construct the `syn` argparse dispatcher (recall, walk, pulse)."""
    parser = argparse.ArgumentParser(
        prog="syn", description="Synapse Brain read commands: recall, walk, pulse."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    recall_parser = subparsers.add_parser("recall", help="Search the brain corpus.")
    recall_parser.add_argument("query", help="Natural-language question or a bare structured ID.")
    recall_parser.add_argument("--limit", type=int, default=5, help="Max results to return.")
    recall_parser.add_argument(
        "--hybrid", action="store_true", help="Use RetrieveChunksNode keyword+semantic fusion."
    )
    recall_parser.add_argument(
        "--workspace", default=None, help="Optional workspace name to scope results."
    )
    recall_parser.add_argument("--json", action="store_true", help="Emit machine-parseable JSON.")

    walk_parser = subparsers.add_parser("walk", help="BFS-traverse brain_edges from a doc.")
    walk_parser.add_argument("doc_id", help="Root document id to traverse from.")
    walk_parser.add_argument("--depth", type=int, default=1, help="Max hops to traverse.")
    walk_parser.add_argument(
        "--workspace", default=None, help="Optional workspace name (reserved; unused by walk)."
    )
    walk_parser.add_argument("--json", action="store_true", help="Emit machine-parseable JSON.")

    pulse_parser = subparsers.add_parser("pulse", help="Report brain corpus/substrate health.")
    pulse_parser.add_argument("--json", action="store_true", help="Emit machine-parseable JSON.")

    return parser


def _resolve_workspace(workspace: str | None) -> None:
    """Validate `workspace` against the registry when supplied.

    Raises the typed `workspace_resolver` errors on an unknown/malformed
    name; is a no-op when `workspace` is None (the default, byte-for-byte
    unchanged behavior path).
    """
    if workspace is None:
        return

    from services.workspace_resolver import (  # pylint: disable=import-outside-toplevel
        load_registry,
        resolve_workspace_root,
    )

    registry = load_registry()
    resolve_workspace_root(None, workspace, registry)


def _run_recall(args: argparse.Namespace) -> int:
    """Execute `syn recall` and print its result; return the exit code."""
    from brain.retrieval import recall  # pylint: disable=import-outside-toplevel

    try:
        _resolve_workspace(args.workspace)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _emit_error(exc, as_json=args.json)

    results = recall(args.query, limit=args.limit, hybrid=args.hybrid, workspace=args.workspace)

    if args.json:
        print(json.dumps(results))
    else:
        if not results:
            print("No results.")
        for rank, item in enumerate(results, start=1):
            print(f"[{rank}] {item.get('doc_id') or item.get('file_path')} — {item.get('title')}")

    return 0


def _run_walk(args: argparse.Namespace) -> int:
    """Execute `syn walk` and print its result; return the exit code."""
    from brain.graph import walk  # pylint: disable=import-outside-toplevel

    try:
        _resolve_workspace(args.workspace)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _emit_error(exc, as_json=args.json)

    result = walk(args.doc_id, depth=args.depth)

    if args.json:
        print(json.dumps(result))
    else:
        print(f"root: {result['root']} (depth={result['depth']})")
        for hop, level in enumerate(result["levels"], start=1):
            print(f"  hop {hop}: {', '.join(level) if level else '(none)'}")

    return 0


def _run_pulse(args: argparse.Namespace) -> int:
    """Execute `syn pulse` and print its result; return the exit code (non-zero if unhealthy)."""
    from brain.pulse import pulse  # pylint: disable=import-outside-toplevel

    report = pulse()

    if args.json:
        print(json.dumps(report.to_dict()))
    else:
        print(f"healthy: {report.healthy}")
        print(f"pgvector_reachable: {report.pgvector_reachable}")
        print(f"embedding_reachable: {report.embedding_reachable}")
        print(f"brain_documents_count: {report.brain_documents_count}")
        print(f"brain_edges_count: {report.brain_edges_count}")
        print(f"edges_empty_but_related_exists: {report.edges_empty_but_related_exists}")
        for error in report.errors:
            print(f"error: {error}")

    return 0 if report.healthy else 1


def _emit_error(exc: Exception, *, as_json: bool) -> int:
    """Render a typed error and return a non-zero exit code (never a prompt/traceback)."""
    message = str(exc)
    if as_json:
        print(json.dumps({"error": message}))
    else:
        print(f"error: {message}", file=sys.stderr)
    logging.warning("syn: command failed: %s", message)
    return 1


def main(argv: list[str] | None = None) -> int:
    """Parse `argv` and dispatch to the `recall` / `walk` / `pulse` subcommand.

    Returns 0 on success; non-zero on a typed `--workspace` resolution error
    or an unhealthy `pulse` verdict. Never raises for user-facing errors and
    never prompts interactively.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    dispatch = {
        "recall": _run_recall,
        "walk": _run_walk,
        "pulse": _run_pulse,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
