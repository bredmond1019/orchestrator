"""app/brain/cli.py — the `syn` console-script dispatcher.

Registered as the `syn` console script (`[project.scripts]` in
`pyproject.toml`, `syn = "app.brain.cli:main"`), mirroring `createworkflow`.
Wires the OR.N1 read cores (`brain.retrieval.recall`, `brain.graph.walk`,
`brain.pulse.pulse`) and the OR.N2 write/ops core (`brain.ops.embed_paths`,
`ingest_dir`, `prune_paths`, `refresh`, `stale`, `run_routine`) behind short, deterministic,
agent-callable verbs (D52):
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
        prog="syn",
        description="Synapse Brain commands: recall, walk, pulse, embed, ingest, prune, "
        "refresh, stale, routine.",
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

    embed_parser = subparsers.add_parser(
        "embed", help="Re-embed a single file into brain_documents."
    )
    embed_parser.add_argument("file", help="Path to the markdown file to embed.")
    embed_parser.add_argument(
        "--force", action="store_true", help="Full re-embed (bypass incremental skip)."
    )
    embed_parser.add_argument("--brain-path", default=None, help="Brain repo root override.")
    embed_parser.add_argument("--json", action="store_true", help="Emit machine-parseable JSON.")

    ingest_parser = subparsers.add_parser(
        "ingest", help="Index on-disk markdown files under a directory."
    )
    ingest_parser.add_argument(
        "--dir", required=True, dest="directory", help="Directory to index."
    )
    ingest_parser.add_argument(
        "--force", action="store_true", help="Full re-embed (bypass incremental skip)."
    )
    ingest_parser.add_argument("--brain-path", default=None, help="Brain repo root override.")
    ingest_parser.add_argument("--json", action="store_true", help="Emit machine-parseable JSON.")

    prune_parser = subparsers.add_parser(
        "prune", help="Delete brain_documents rows for deleted/renamed-away paths."
    )
    prune_parser.add_argument("paths", nargs="+", help="File path(s) to prune.")
    prune_parser.add_argument(
        "--dry-run", action="store_true", help="Report what would be deleted without writing."
    )
    prune_parser.add_argument("--brain-path", default=None, help="Brain repo root override.")
    prune_parser.add_argument("--json", action="store_true", help="Emit machine-parseable JSON.")

    refresh_parser = subparsers.add_parser(
        "refresh", help="Refresh both brain_documents and brain_edges."
    )
    refresh_parser.add_argument(
        "--rebuild", action="store_true", help="Corpus-wide re-index from scratch."
    )
    refresh_parser.add_argument(
        "--dry-run", action="store_true", help="Index dry-run; skip edge reload."
    )
    refresh_parser.add_argument("--brain-path", default=None, help="Brain repo root override.")
    refresh_parser.add_argument("--json", action="store_true", help="Emit machine-parseable JSON.")

    stale_parser = subparsers.add_parser(
        "stale", help="Report corpus drift (content + structure axes)."
    )
    stale_parser.add_argument(
        "--assert-clean", action="store_true", help="Exit non-zero if any drift is found."
    )
    stale_parser.add_argument(
        "--deep",
        action="store_true",
        help="Run the deep corpus/index drift check (five axes + the ingested/ lane); "
        "exits non-zero on any drift.",
    )
    stale_parser.add_argument(
        "--repair",
        action="store_true",
        help="With --deep: repair the repairable drift axes using existing ops primitives.",
    )
    stale_parser.add_argument("--brain-path", default=None, help="Brain repo root override.")
    stale_parser.add_argument("--json", action="store_true", help="Emit machine-parseable JSON.")

    routine_parser = subparsers.add_parser(
        "routine", help="Run a named chore (OR.J cron convention)."
    )
    routine_parser.add_argument("name", help="Registered routine name (e.g. refresh, stale).")
    routine_parser.add_argument("--json", action="store_true", help="Emit machine-parseable JSON.")

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


def _run_embed(args: argparse.Namespace) -> int:
    """Execute `syn embed` and print its result; return the exit code."""
    from brain.ops import embed_paths  # pylint: disable=import-outside-toplevel

    try:
        result = embed_paths([args.file], force=args.force, brain_path=args.brain_path)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _emit_error(exc, as_json=args.json)

    if args.json:
        print(json.dumps(result))
    else:
        print(f"embedded: {args.file}")

    return 0


def _run_ingest(args: argparse.Namespace) -> int:
    """Execute `syn ingest` and print its result; return the exit code."""
    from brain.ops import ingest_dir  # pylint: disable=import-outside-toplevel

    try:
        result = ingest_dir(args.directory, force=args.force, brain_path=args.brain_path)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _emit_error(exc, as_json=args.json)

    if args.json:
        print(json.dumps(result))
    else:
        print(f"ingested: {len(result['ingested'])} file(s)")

    return 0


def _run_prune(args: argparse.Namespace) -> int:
    """Execute `syn prune` and print its result; return the exit code."""
    from brain.ops import prune_paths  # pylint: disable=import-outside-toplevel

    try:
        result = prune_paths(args.paths, dry_run=args.dry_run, brain_path=args.brain_path)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _emit_error(exc, as_json=args.json)

    if args.json:
        print(json.dumps(result))
    else:
        suffix = " (dry-run)" if result["dry_run"] else ""
        print(f"pruned: {len(result['pruned'])} path(s){suffix}")

    return 0


def _run_refresh(args: argparse.Namespace) -> int:
    """Execute `syn refresh` and print its result; return the exit code."""
    from brain.ops import refresh  # pylint: disable=import-outside-toplevel

    try:
        result = refresh(rebuild=args.rebuild, dry_run=args.dry_run, brain_path=args.brain_path)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _emit_error(exc, as_json=args.json)

    if args.json:
        print(json.dumps(result))
    else:
        print(f"refresh: {result}")

    return 0


def _run_stale(args: argparse.Namespace) -> int:
    """Execute `syn stale` and print its result; return the exit code.

    `--deep` runs the five-axis `reconcile.deep_stale` check instead (its own
    exit-code contract: non-zero on any drift, unconditionally — see
    `_run_stale_deep`). Without `--deep`, exits non-zero only when
    `--assert-clean` is passed and drift is found, so `OR.J`'s cron can fail
    on drift while an ad-hoc report stays exit 0.
    """
    if args.deep:
        return _run_stale_deep(args)

    from brain.ops import stale  # pylint: disable=import-outside-toplevel

    try:
        result = stale(brain_path=args.brain_path)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _emit_error(exc, as_json=args.json)

    if args.json:
        print(json.dumps(result))
    else:
        print(
            f"drift: {result['drift']}  changed: {len(result['changed_files'])}  "
            f"edges_stale: {result['edges_stale']}"
        )

    if args.assert_clean and result["drift"]:
        return 1

    return 0


def _print_deep_report(report: dict) -> None:
    """Human-mode renderer for a `reconcile.ReconcileReport.to_dict()` payload."""
    print(f"drift: {report['drift']}")
    print(f"  deleted_but_embedded: {len(report['deleted_but_embedded'])}")
    for file_path in report["deleted_but_embedded"]:
        print(f"    - {file_path}")
    print(f"  section_orphans: {len(report['section_orphans'])}")
    for file_path, section in report["section_orphans"]:
        print(f"    - {file_path} :: {section}")
    print(f"  orphaned_chunks: {len(report['orphaned_chunks'])}")
    print(f"  dangling_edges: {len(report['dangling_edges'])}")
    print(f"  model_mismatch: {len(report['model_mismatch'])}")
    print(f"  unstamped_count (informational): {report['unstamped_count']}")
    print(f"  ingested_count (informational): {report['ingested_count']}")


def _run_stale_deep(args: argparse.Namespace) -> int:
    """Execute `syn stale --deep [--repair]` and print its result; return the exit code.

    Runs `reconcile.deep_stale`; with `--repair`, dispatches
    `ops.repair_deep_stale` (existing primitives only) and re-reports the
    post-repair state. Exits 1 whenever the final report's `drift` is True,
    0 otherwise — unconditional, unlike plain `syn stale` (no `--assert-clean`
    gate here: a caller asking for `--deep` wants the drift signal by
    definition).
    """
    from brain.ops import repair_deep_stale  # pylint: disable=import-outside-toplevel
    from brain.reconcile import deep_stale  # pylint: disable=import-outside-toplevel

    try:
        report = deep_stale(brain_path=args.brain_path)
        if args.repair:
            result = repair_deep_stale(report, brain_path=args.brain_path)
            payload = result
            final_drift = result["after"]["drift"]
        else:
            payload = report.to_dict()
            final_drift = report.drift
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _emit_error(exc, as_json=args.json)

    if args.json:
        print(json.dumps(payload))
    elif args.repair:
        print("-- before --")
        _print_deep_report(payload["before"])
        print("-- actions --")
        for action in payload["actions"]:
            print(f"  {action}")
        print("-- after --")
        _print_deep_report(payload["after"])
    else:
        _print_deep_report(payload)

    return 1 if final_drift else 0


def _run_routine(args: argparse.Namespace) -> int:
    """Execute `syn routine <name>` and print its result; return the exit code."""
    from brain.ops import run_routine  # pylint: disable=import-outside-toplevel

    try:
        result = run_routine(args.name)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _emit_error(exc, as_json=args.json)

    if args.json:
        print(json.dumps(result))
    else:
        print(f"routine {args.name}: {result}")

    return 0


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
        "embed": _run_embed,
        "ingest": _run_ingest,
        "prune": _run_prune,
        "refresh": _run_refresh,
        "stale": _run_stale,
        "routine": _run_routine,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
