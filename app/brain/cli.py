"""app/brain/cli.py — the `syn` console-script dispatcher.

Registered as the `syn` console script (`[project.scripts]` in
`pyproject.toml`, `syn = "app.brain.cli:main"`), mirroring `createworkflow`.
Wires the OR.N1 read cores (`brain.retrieval.recall`, `brain.graph.walk`,
`brain.pulse.pulse`), the OR.N2 write/ops core (`brain.ops.embed_paths`,
`ingest_dir`, `prune_paths`, `refresh`, `stale`, `run_routine`), and the OR.K1 query-log read
(`queries` — raw `retrieval_queries` rows plus a read-time abstain rate; no aggregation table,
no rollup, no dashboard — plus `queries --prune`, the retention half over `ops.prune_queries`)
behind short, deterministic, agent-callable verbs (D52):
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
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent.parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))


def _build_parser() -> argparse.ArgumentParser:  # pylint: disable=too-many-statements
    """Construct the `syn` argparse dispatcher (recall, walk, pulse, ..., queries)."""
    parser = argparse.ArgumentParser(
        prog="syn",
        description="Synapse Brain commands: recall, walk, pulse, embed, ingest, prune, "
        "refresh, stale, routine, eval, queries.",
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

    eval_parser = subparsers.add_parser(
        "eval", help="Score the retrieval golden set (OR.K2) and report metrics."
    )
    eval_parser.add_argument(
        "--set",
        dest="golden_set",
        default=None,
        help="Golden-set YAML path (default: planning/retrieval-golden-set.yaml).",
    )
    eval_parser.add_argument(
        "--baseline",
        default=None,
        help="Prior run JSON to diff against; exits non-zero on any metric regression.",
    )
    eval_parser.add_argument("--json", action="store_true", help="Emit machine-parseable JSON.")

    queries_parser = subparsers.add_parser(
        "queries",
        help="Read raw retrieval_queries rows logged by the OR.K1 fire-and-forget query log.",
    )
    queries_parser.add_argument(
        "--since",
        default=None,
        help="Window, e.g. '7d' or '24h' (default: no lower bound — every logged row).",
    )
    queries_parser.add_argument(
        "--abstained", action="store_true", help="Only rows where abstained=true."
    )
    queries_parser.add_argument(
        "--prune",
        action="store_true",
        help="Retention mode: delete rows older than the keep window instead of reading.",
    )
    queries_parser.add_argument(
        "--keep-days",
        type=int,
        default=None,
        help="Retention window in days for --prune "
        "(default: $BRAIN_QUERY_LOG_KEEP_DAYS, else 90).",
    )
    queries_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --prune: report what would be deleted and delete nothing.",
    )
    queries_parser.add_argument("--json", action="store_true", help="Emit machine-parseable JSON.")

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

    results = recall(
        args.query,
        limit=args.limit,
        hybrid=args.hybrid,
        workspace=args.workspace,
        surface="cli",
    )

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


def _print_eval_report(report_dict: dict) -> None:
    """Human-mode renderer for a `RetrievalRunReport.to_dict()` payload."""
    for case in report_dict["results"]:
        print(
            f"[{case['case_id']}] recall@5={case['recall_at_5']} "
            f"recall@10={case['recall_at_10']} rr={case['reciprocal_rank']} "
            f"abstain_correct={case['abstain_correct']} "
            f"groundedness={case['groundedness']}"
        )
    print("-- aggregate --")
    for metric, value in sorted(report_dict["aggregate"].items()):
        print(f"  {metric}: {value:.4f}")


def _run_eval(args: argparse.Namespace) -> int:
    """Execute `syn eval` and print its result; return the exit code.

    Runs the golden set, writes a dated JSON report, and prints per-case +
    aggregate metrics. With `--baseline <path>`, also prints a signed
    per-metric delta against that prior run and returns non-zero on any
    regression (`brain.eval.compare_to_baseline`).
    """
    from brain.eval import (  # pylint: disable=import-outside-toplevel
        compare_to_baseline,
        load_cases,
        run_eval,
        write_report,
    )
    from brain.eval.runner import (  # pylint: disable=import-outside-toplevel
        DEFAULT_GOLDEN_SET_PATH,
        load_report,
    )

    golden_set_path = args.golden_set or DEFAULT_GOLDEN_SET_PATH

    try:
        cases = load_cases(golden_set_path)
        report = run_eval(cases)
        write_report(report)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _emit_error(exc, as_json=args.json)

    report_dict = report.to_dict()
    exit_code = 0

    deltas = None
    if args.baseline:
        try:
            baseline = load_report(args.baseline)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return _emit_error(exc, as_json=args.json)
        deltas, regressed = compare_to_baseline(report_dict, baseline)
        exit_code = 1 if regressed else 0

    if args.json:
        payload = dict(report_dict)
        if deltas is not None:
            payload["baseline_deltas"] = deltas
        print(json.dumps(payload))
    else:
        _print_eval_report(report_dict)
        if deltas is not None:
            print("-- baseline deltas (signed; negative = regression) --")
            for metric, delta in sorted(deltas.items()):
                print(f"  {metric}: {delta:+.4f}")

    return exit_code


_SINCE_RE = re.compile(r"^(\d+)([dh])$")


class InvalidSinceWindowError(ValueError):
    """Raised when `--since` doesn't match the `<N>d` / `<N>h` window syntax."""


def _parse_since(since: str) -> timedelta:
    """Parse a `'7d'` / `'24h'`-style window string into a `timedelta`.

    Raises `InvalidSinceWindowError` (typed, caught by `_emit_error` like
    every other `syn` command error) for anything else.
    """
    match = _SINCE_RE.match(since.strip())
    if not match:
        raise InvalidSinceWindowError(
            f"invalid --since window {since!r}: expected '<N>d' or '<N>h' (e.g. '7d', '24h')"
        )
    amount, unit = int(match.group(1)), match.group(2)
    return timedelta(days=amount) if unit == "d" else timedelta(hours=amount)


def _row_to_dict(row) -> dict:
    """Render one `RetrievalQuery` row as a JSON/print-friendly dict."""
    return {
        "id": str(row.id),
        "query": row.query,
        "surface": row.surface,
        "workspace_id": row.workspace_id,
        "hybrid": row.hybrid,
        "via_mix": row.via_mix,
        "result_count": row.result_count,
        "top_score": row.top_score,
        "retrieval_confidence": row.retrieval_confidence,
        "abstained": row.abstained,
        "top_doc_ids": row.top_doc_ids,
        "latency_ms": row.latency_ms,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _run_queries_prune(args: argparse.Namespace) -> int:
    """Execute `syn queries --prune` and print its result; return the exit code.

    Retention, not reading: delegates wholesale to `brain.ops.prune_queries`
    (the single implementation the `queries_prune` cron routine also calls)
    and renders its `{"deleted", "kept", "cutoff", "keep_days", "dry_run"}`
    summary. Exit 0 on success including a zero-deletion no-op; non-zero
    only on an actual error.
    """
    from brain.ops import prune_queries  # pylint: disable=import-outside-toplevel

    try:
        result = prune_queries(args.keep_days, dry_run=args.dry_run)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _emit_error(exc, as_json=args.json)

    if args.json:
        print(json.dumps(result))
    else:
        verb = "would delete" if result["dry_run"] else "deleted"
        print(
            f"queries prune: {verb} {result['deleted']} row(s) older than "
            f"{result['cutoff']} (keep_days={result['keep_days']}); "
            f"{result['kept']} kept."
        )

    return 0


def _run_queries(args: argparse.Namespace) -> int:
    """Execute `syn queries` and print its result; return the exit code.

    Dispatches to `_run_queries_prune` in `--prune` (retention) mode;
    otherwise reads raw `retrieval_queries` rows (no aggregation table, no rollup,
    no dashboard — `GenericRepository.get_all()` plus in-process
    filtering/sorting) and, in `--json` mode, includes a read-time
    `abstain_rate` computed over the returned window — never a stored
    number.
    """
    if args.prune:
        return _run_queries_prune(args)

    from database.repository import GenericRepository  # pylint: disable=import-outside-toplevel
    from database.retrieval_query import RetrievalQuery  # pylint: disable=import-outside-toplevel
    from database.session import db_session  # pylint: disable=import-outside-toplevel

    try:
        # `created_at` (RetrievalQuery model) defaults to naive `datetime.now()`, so the
        # cutoff is computed the same naive way rather than tz-aware — comparing naive to
        # aware would raise.
        cutoff = datetime.now() - _parse_since(args.since) if args.since else None
    except InvalidSinceWindowError as exc:
        return _emit_error(exc, as_json=args.json)

    with next(db_session()) as session:  # type: ignore[arg-type]
        rows = GenericRepository(session=session, model=RetrievalQuery).get_all()

        if cutoff is not None:
            rows = [row for row in rows if row.created_at is not None and row.created_at >= cutoff]
        if args.abstained:
            rows = [row for row in rows if row.abstained]
        rows.sort(key=lambda row: row.created_at or datetime.min, reverse=True)

        rendered = [_row_to_dict(row) for row in rows]

    if args.json:
        # Read-time only — never a stored rollup (the zero-aggregation rule, OR.K1).
        total = len(rendered)
        abstained_count = sum(1 for row in rendered if row["abstained"])
        abstain_rate = abstained_count / total if total else 0.0
        print(json.dumps({"queries": rendered, "count": total, "abstain_rate": abstain_rate}))
    else:
        if not rendered:
            print("No logged queries.")
        for row in rendered:
            print(
                f"[{row['created_at']}] ({row['surface']}) {row['query']!r} "
                f"via_mix={row['via_mix']} confidence={row['retrieval_confidence']} "
                f"abstained={row['abstained']}"
            )

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


def _validate_queries_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Enforce `syn queries --prune`'s mutual exclusion with the read filters.

    `--since` and `--abstained` are combinable with each other, so this is
    not expressible as one `add_mutually_exclusive_group`. `parser.error`
    keeps it an argparse-native failure (usage to stderr, exit 2), the same
    shape any other bad `syn` invocation produces.
    """
    if args.command != "queries":
        return
    if args.prune and (args.since is not None or args.abstained):
        parser.error("--prune cannot be combined with the read filters --since/--abstained")
    if not args.prune and (args.keep_days is not None or args.dry_run):
        parser.error("--keep-days/--dry-run are only valid with --prune")


def main(argv: list[str] | None = None) -> int:
    """Parse `argv` and dispatch to the `recall` / `walk` / `pulse` subcommand.

    Returns 0 on success; non-zero on a typed `--workspace` resolution error
    or an unhealthy `pulse` verdict. Never raises for user-facing errors and
    never prompts interactively.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    _validate_queries_args(parser, args)

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
        "eval": _run_eval,
        "queries": _run_queries,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
