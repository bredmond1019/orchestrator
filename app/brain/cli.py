"""app/brain/cli.py — the `syn` console-script dispatcher.

Registered as the `syn` console script (`[project.scripts]` in
`pyproject.toml`, `syn = "app.brain.cli:main"`), mirroring `createworkflow`.
Wires the OR.N1 read cores (`brain.retrieval.recall`, `brain.graph.walk`,
`brain.pulse.pulse`), the OR.N2 write/ops core (`brain.ops.embed_paths`,
`ingest_dir`, `prune_paths`, `refresh`, `stale`, `run_routine`), and the OR.K1 query-log read
(`queries` — raw `retrieval_queries` rows plus a read-time abstain rate; no aggregation table,
no rollup, no dashboard — plus `queries --prune`, the retention half over `ops.prune_queries`,
and `queries mine`, the OR.2.E surface over `brain.query_mining.mine_candidates` that proposes
reviewable golden-set candidates as a stdout-only YAML fragment — it never writes
`planning/retrieval-golden-set.yaml`) behind short, deterministic, agent-callable verbs (D52):
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
        description="Synapse Brain commands: recall, walk, pulse, mcp, embed, ingest, prune, "
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

    subparsers.add_parser(
        "mcp", help="Serve the Brain read path as an MCP server over stdio."
    )

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
        help="Prior run JSON to diff against; defaults to the promoted pin "
        "(planning/retrieval-eval-runs/baseline.json) when omitted. Exits "
        "non-zero on a significant regression.",
    )
    eval_parser.add_argument(
        "--no-baseline",
        action="store_true",
        help="Skip comparison entirely (including the default pin lookup); always exits 0.",
    )
    eval_parser.add_argument(
        "--strict",
        action="store_true",
        help="With --baseline: exit non-zero on ANY metric decrease (the old strict-sign "
        "tripwire), not only a statistically significant one.",
    )
    eval_parser.add_argument("--json", action="store_true", help="Emit machine-parseable JSON.")
    eval_parser.add_argument(
        "--no-write",
        action="store_true",
        help="Score and print the report but do not persist it under "
        "planning/retrieval-eval-runs/.",
    )
    eval_parser.add_argument(
        "--report",
        nargs="?",
        const="",
        default=None,
        metavar="PATH",
        help="Render a publishable Markdown report (scrubbed, allow-listed) for this "
        "run. With no PATH, writes to stdout; with a PATH, writes the file. Composes "
        "with every other eval flag, including --no-write.",
    )

    eval_subparsers = eval_parser.add_subparsers(dest="eval_subcommand")
    promote_parser = eval_subparsers.add_parser(
        "promote",
        help="Promote a run to the baseline pin "
        "(planning/retrieval-eval-runs/baseline.json).",
    )
    promote_parser.add_argument(
        "run", help="Path to a run JSON under planning/retrieval-eval-runs/."
    )
    promote_parser.add_argument(
        "--reason", required=True, help="Non-empty reason for the promotion (required)."
    )
    promote_parser.add_argument(
        "--force",
        action="store_true",
        help="Promote even if significantly worse than the current pin.",
    )
    promote_parser.add_argument("--json", action="store_true", help="Emit machine-parseable JSON.")

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

    queries_subparsers = queries_parser.add_subparsers(dest="queries_subcommand")
    mine_parser = queries_subparsers.add_parser(
        "mine",
        help="Propose reviewable golden-set candidates from real logged traffic. "
        "Never writes planning/retrieval-golden-set.yaml — emits a YAML fragment to stdout.",
    )
    mine_parser.add_argument(
        "--since",
        default=None,
        help="Window, e.g. '7d' or '24h' (default: no lower bound — every logged row).",
    )
    mine_parser.add_argument(
        "--min-count",
        type=int,
        default=None,
        help="Minimum times a query must be seen to be considered (default: 2).",
    )
    mine_parser.add_argument(
        "--include-singletons",
        action="store_true",
        help="Override --min-count to 1 — include queries seen only once.",
    )
    mine_parser.add_argument(
        "--limit", type=int, default=None, help="Max candidates to emit (default: no limit)."
    )
    mine_parser.add_argument("--json", action="store_true", help="Emit machine-parseable JSON.")

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


def _run_mcp(_args: argparse.Namespace) -> int:
    """Execute `syn mcp`: serve the Brain read path as an MCP server over stdio.

    Blocks until stdin closes, then returns 0.
    """
    import asyncio  # pylint: disable=import-outside-toplevel

    from brain.mcp import serve  # pylint: disable=import-outside-toplevel

    asyncio.run(serve())
    return 0


def _run_embed(args: argparse.Namespace) -> int:
    """Execute `syn embed` and print its result; return the exit code.

    Non-zero whenever `embed_paths`'s `success` is `False` — `index_brain`
    reported a parse/embed/DB failure — not just on a raised exception
    (OR.2.C task 3: previously `index_brain.main()`'s exit code never reached
    `syn embed`'s own).
    """
    from brain.ops import embed_paths  # pylint: disable=import-outside-toplevel

    try:
        result = embed_paths([args.file], force=args.force, brain_path=args.brain_path)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _emit_error(exc, as_json=args.json)

    if args.json:
        print(json.dumps(result))
    else:
        print(f"embedded: {args.file}")
        if not result["success"]:
            for err in result["errors"]:
                print(f"  {err}")

    return 0 if result["success"] else 1


def _run_ingest(args: argparse.Namespace) -> int:
    """Execute `syn ingest` and print its result; return the exit code.

    Non-zero whenever `ingest_dir`'s `success` is `False` (see `_run_embed`
    — `ingest_dir` has no `index_brain.main()` call site of its own; it
    forwards `embed_paths`'s result).
    """
    from brain.ops import ingest_dir  # pylint: disable=import-outside-toplevel

    try:
        result = ingest_dir(args.directory, force=args.force, brain_path=args.brain_path)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _emit_error(exc, as_json=args.json)

    if args.json:
        print(json.dumps(result))
    else:
        print(f"ingested: {len(result['ingested'])} file(s)")
        if not result["success"]:
            for err in result["errors"]:
                print(f"  {err}")

    return 0 if result["success"] else 1


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
        if not result["success"]:
            for err in result["errors"]:
                print(f"  {err}")

    return 0 if result["success"] else 1


def _run_refresh(args: argparse.Namespace) -> int:
    """Execute `syn refresh` and print its result; return the exit code.

    Non-zero whenever the `documents` half's `success` is `False` — see
    `_run_embed`. The `edges` half has no analogous failure mode reported
    here (`refresh_edges` raises on a real failure, caught by the `except`
    above like any other exception).
    """
    from brain.ops import refresh  # pylint: disable=import-outside-toplevel

    try:
        result = refresh(rebuild=args.rebuild, dry_run=args.dry_run, brain_path=args.brain_path)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _emit_error(exc, as_json=args.json)

    if args.json:
        print(json.dumps(result))
    else:
        print(f"refresh: {result}")
        if not result["documents"]["success"]:
            for err in result["documents"]["errors"]:
                print(f"  {err}")

    return 0 if result["documents"]["success"] else 1


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
    aggregate_stats = report_dict.get("aggregate_stats") or {}
    for metric, value in sorted(report_dict["aggregate"].items()):
        interval = aggregate_stats.get(metric)
        if interval and interval.get("lo") is not None and interval.get("hi") is not None:
            print(
                f"  {metric}: {value:.4f}  "
                f"[{interval['lo']:.3f}, {interval['hi']:.3f}]  n={interval['n']}"
            )
        else:
            print(f"  {metric}: {value:.4f}")


def _eval_exit_code(regressed: bool, verdict: dict, *, strict: bool) -> tuple[int, list[str]]:
    """The `syn eval --baseline` exit-code policy plus any warning lines to
    print.

    `--strict` restores the old strict-sign tripwire: exit 1 iff `regressed`
    (any metric strictly decreased), regardless of significance. Without
    `--strict`, exit 1 only when some metric's paired verdict classifies as
    `regressed-significant`; a `regressed-within-noise` metric prints a loud
    warning but exits 0 — `regressed` itself keeps its exact strict-sign
    semantics either way (see `compare_to_baseline`).
    """
    if strict:
        return (1 if regressed else 0), []

    significant = sorted(
        metric
        for metric, entry in verdict.items()
        if entry["classification"] == "regressed-significant"
    )
    within_noise = sorted(
        metric
        for metric, entry in verdict.items()
        if entry["classification"] == "regressed-within-noise"
    )

    warnings = []
    if within_noise:
        warnings.append(
            "WARNING: regressed-within-noise (not statistically significant, exit 0): "
            + ", ".join(within_noise)
        )

    return (1 if significant else 0), warnings


def _render_eval_result(
    args: argparse.Namespace,
    report_dict: dict,
    written_path: str | None,
    baseline_result: tuple[dict, dict] | None,
    warnings: list[str],
    *,
    baseline_label: str | None = None,
) -> None:
    """Print (JSON or human) the `syn eval` result — factored out of
    `_run_eval` purely to keep that function's local-variable count in
    check; carries no behavior beyond what `_run_eval` used to do inline.

    `baseline_label` names which run was compared against (an explicit
    `--baseline` path or the promoted pin's `run` field) — printed/emitted
    so `syn eval`'s default pin comparison names the run, not just the
    numbers.
    """
    deltas, verdict = baseline_result if baseline_result is not None else (None, None)

    if args.json:
        payload = dict(report_dict)
        payload["written_path"] = written_path
        if deltas is not None:
            payload["baseline_deltas"] = deltas
            payload["baseline_verdict"] = verdict
            payload["baseline_label"] = baseline_label
        print(json.dumps(payload))
        return

    _print_eval_report(report_dict)
    if deltas is not None:
        print(f"-- comparing against baseline: {baseline_label} --")
        print("-- baseline deltas (signed; negative = regression) --")
        for metric, delta in sorted(deltas.items()):
            entry = verdict.get(metric, {})
            confound_marker = ""
            if entry.get("confounded") is True:
                confound_marker = "  [CONFOUNDED: corpus changed]"
            elif entry.get("confounded") == "unknown":
                confound_marker = "  [confounded: unknown, missing corpus stamp]"
            print(f"  {metric}: {delta:+.4f}{confound_marker}")
        print("-- paired verdict --")
        for metric, entry in sorted(verdict.items()):
            ids_note = ""
            if entry["classification"] == "incomparable" and (
                entry.get("added_case_ids") or entry.get("removed_case_ids")
            ):
                ids_note = (
                    f"  (added={entry['added_case_ids']} removed={entry['removed_case_ids']})"
                )
            print(f"  {metric}: {entry['classification']} (pairable={entry['pairable']}){ids_note}")
        ranking_changed = next(iter(verdict.values()), {}).get("ranking_constants_changed")
        if ranking_changed:
            print(f"-- ranking constants changed: {', '.join(ranking_changed)} --")
    for warning in warnings:
        print(warning)
    if args.no_write:
        print("(--no-write: report not persisted)")


def _eval_baseline_comparison(
    args: argparse.Namespace, report_dict: dict
) -> tuple[int, tuple[dict, dict] | None, str | None, list[str]]:
    """Resolve which baseline (if any) `syn eval` compares against and run
    the comparison — factored out of `_run_eval` purely to keep its local
    count down; carries no behavior beyond what `_run_eval` used to do
    inline. Returns `(exit_code, baseline_result, baseline_label,
    warnings)`; `baseline_result` is `None` when `--no-baseline` was passed
    or no baseline (explicit or pinned) is available."""
    from brain.eval import compare_to_baseline  # pylint: disable=import-outside-toplevel
    from brain.eval.runner import (  # pylint: disable=import-outside-toplevel
        corpus_divergence_warning,
        resolve_baseline,
    )

    if args.no_baseline:
        return 0, None, None, []

    resolved = resolve_baseline(args.baseline)
    if resolved is None:
        return 0, None, None, []

    baseline, baseline_label = resolved
    deltas, regressed, verdict = compare_to_baseline(report_dict, baseline)
    exit_code, warnings = _eval_exit_code(regressed, verdict, strict=args.strict)
    if not args.baseline:
        # Comparing against the pin specifically (not an explicit
        # --baseline override) — proactively warn if the live corpus has
        # drifted from what the pin was measured against. Never a gate;
        # see `corpus_divergence_warning`.
        divergence = corpus_divergence_warning(report_dict.get("corpus"), baseline.get("corpus"))
        if divergence:
            warnings.append(divergence)

    return exit_code, (deltas, verdict), baseline_label, warnings


def _run_eval(args: argparse.Namespace) -> int:
    """Execute `syn eval` and print its result; return the exit code.

    Runs the golden set, writes a dated JSON report (unless `--no-write` is
    passed, in which case the report is scored and printed but not
    persisted), and prints per-case + aggregate metrics. Compares against a
    baseline unless `--no-baseline` is passed: an explicit `--baseline
    <path>` wins, otherwise the promoted pin
    (`planning/retrieval-eval-runs/baseline.json`) is used when one exists.
    Either way, prints a signed per-metric delta and a paired per-case
    verdict against that prior run (`brain.eval.compare_to_baseline`), and
    names which run was compared against. Exit code: 1 iff some metric's
    paired verdict is `regressed-significant`; a `regressed-within-noise`
    metric warns loudly but exits 0. `--strict` restores the old
    strict-sign tripwire (exit 1 on ANY metric decrease). `--no-baseline`
    always exits 0 regardless of metrics. `--no-write` gates persistence
    only and never affects the verdict or the exit code. `--report [PATH]`
    additionally renders a scrubbed, publishable Markdown report (task 4,
    `OR.ticket.publishable-eval-report`) — to stdout with no PATH, to the
    named file with one — independent of `--no-write` and of `--json`.
    """
    from brain.eval import (  # pylint: disable=import-outside-toplevel
        load_cases,
        run_eval,
        write_report,
    )
    from brain.eval.report import render_run  # pylint: disable=import-outside-toplevel
    from brain.eval.runner import DEFAULT_GOLDEN_SET_PATH  # pylint: disable=import-outside-toplevel

    golden_set_path = args.golden_set or DEFAULT_GOLDEN_SET_PATH

    try:
        cases = load_cases(golden_set_path)
        report = run_eval(cases)
        written_path = None if args.no_write else str(write_report(report))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _emit_error(exc, as_json=args.json)

    report_dict = report.to_dict()

    try:
        exit_code, baseline_result, baseline_label, warnings = _eval_baseline_comparison(
            args, report_dict
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _emit_error(exc, as_json=args.json)

    _render_eval_result(
        args, report_dict, written_path, baseline_result, warnings, baseline_label=baseline_label
    )

    report_path = getattr(args, "report", None)
    if report_path is not None:
        try:
            markdown = render_run(report)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return _emit_error(exc, as_json=args.json)
        if report_path == "":
            print(markdown)
        else:
            Path(report_path).write_text(markdown, encoding="utf-8")

    return exit_code


def _run_eval_promote(args: argparse.Namespace) -> int:
    """Execute `syn eval promote <run> --reason "..."`; return the exit code.

    Delegates the guards to `brain.eval.promote_run` (existence/tracked-dir,
    required stamps, `--reason` non-empty, `--force`-gated regression) and
    reports its `PromotionError` the same way every other `syn` command
    reports a typed user-facing error.
    """
    from brain.eval import promote_run  # pylint: disable=import-outside-toplevel
    from brain.eval.runner import PromotionError  # pylint: disable=import-outside-toplevel

    try:
        pointer = promote_run(args.run, reason=args.reason, force=args.force)
    except PromotionError as exc:
        return _emit_error(exc, as_json=args.json)

    if args.json:
        print(json.dumps(pointer))
    else:
        print(f"promoted {pointer['run']} -> planning/retrieval-eval-runs/baseline.json")
        print(f"  reason: {pointer['reason']}")
        print(f"  promoted_by: {pointer['promoted_by']}  promoted_at: {pointer['promoted_at']}")

    return 0


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
        "k": row.k,
        "corpus": row.corpus,
        "embedding_model": row.embedding_model,
        "filters": row.filters,
        "top_scores": row.top_scores,
    }


_MINE_FRAGMENT_HEADER = """\
# Mined golden-set candidates (`syn queries mine`) — REVIEW BEFORE PASTING.
#
# Deliberately unusable as emitted — do NOT "improve" this by pre-filling
# either field:
#   - `expect_docs` is EMPTY. The logged top hits are shown only in a
#     comment below each case, never pre-filled, so an unread paste fails
#     tests/brain/test_golden_set_schema.py::test_expect_docs_or_abstain_present_for_every_case
#   - every `id` reads "RENAME ME", so an unread paste also fails
#     test_id_prefix_agrees_with_category
#
# `confidently-wrong-suspect` candidates are a HEURISTIC, not a detector —
# you cannot tell "the top hit is wrong" from the log alone. This tool
# prioritizes a review list; it never judges, and it never writes
# planning/retrieval-golden-set.yaml. A human reviews each case, fills in
# `expect_docs` (or sets `expect_abstain: true`), renames the id, and pastes
# it into that file's `cases:` list by hand.
cases:
"""


def _mine_candidate_top_hits_comment(candidate) -> list[str]:
    """Render `candidate`'s logged top hits as YAML comment lines (never as
    pre-filled `expect_docs` — see `_MINE_FRAGMENT_HEADER`)."""
    from itertools import zip_longest  # pylint: disable=import-outside-toplevel

    lines = ["    # top hits (for review only — do NOT pre-fill expect_docs):"]
    doc_ids = candidate.top_doc_ids or []
    scores = candidate.top_scores or []
    if not doc_ids and not scores:
        lines.append("    #   (no top hits captured for this candidate)")
        return lines
    for doc_id, score in zip_longest(doc_ids, scores):
        if doc_id is None:
            continue
        score_text = f" (score={score:.4f})" if score is not None else ""
        lines.append(f"    #   - {doc_id}{score_text}")
    return lines


def _mine_candidate_to_case_dict(candidate) -> dict:
    """Render one `MinedCandidate` as a fail-loud golden-set case mapping.

    `expect_docs` deliberately empty, `id` deliberately `"RENAME ME"` — see
    `_MINE_FRAGMENT_HEADER`. `source`/`category` are the schema-v2 fields
    `OR.2.A` added expressly for this (`source: mined`, `category: mined`).
    """
    return {
        "id": "RENAME ME",
        "query": candidate.query,
        "expect_docs": [],
        "expect_abstain": False,
        "source": "mined",
        "category": "mined",
        "source_query_id": candidate.source_query_id,
        "notes": (
            f"mined candidate: class={candidate.class_} count={candidate.count} "
            f"avg_confidence={candidate.avg_confidence} last_seen="
            f"{candidate.last_seen.isoformat() if candidate.last_seen else None} — "
            f"{candidate.rationale}"
        ),
    }


def _render_mine_yaml(candidates: list) -> str:
    """Render `candidates` as one stdout-only YAML document: `{"cases": [...]}`.

    Parses under `brain.eval.load_cases` once a human fills `expect_docs`
    (or sets `expect_abstain: true`) and renames the `RENAME ME` id — as
    emitted it deliberately fails the golden-set schema test. Never touches
    `planning/retrieval-golden-set.yaml` — this is a pure string builder over
    already-mined `MinedCandidate`s.
    """
    import yaml  # pylint: disable=import-outside-toplevel

    blocks = [_MINE_FRAGMENT_HEADER.rstrip("\n")]
    for candidate in candidates:
        case_dict = _mine_candidate_to_case_dict(candidate)
        dumped = yaml.safe_dump(
            [case_dict], sort_keys=False, default_flow_style=False, allow_unicode=True
        )
        case_lines = [f"  # class={candidate.class_} — {candidate.rationale}"]
        for line in dumped.rstrip("\n").splitlines():
            indented = "  " + line
            case_lines.append(indented)
            if indented.strip().startswith("expect_docs:"):
                case_lines.extend(_mine_candidate_top_hits_comment(candidate))
        blocks.append("\n".join(case_lines))
    return "\n".join(blocks) + "\n"


def _mine_candidate_to_json_dict(candidate) -> dict:
    """Render one `MinedCandidate` for `syn queries mine --json` — ranked
    with its scoring rationale, so a reviewer can see why it was surfaced."""
    return {
        "query": candidate.query,
        "count": candidate.count,
        "avg_confidence": candidate.avg_confidence,
        "last_seen": candidate.last_seen.isoformat() if candidate.last_seen else None,
        "class": candidate.class_,
        "rationale": candidate.rationale,
        "source_query_id": candidate.source_query_id,
        "top_doc_ids": candidate.top_doc_ids,
        "top_scores": candidate.top_scores,
        "via_mix": candidate.via_mix,
        "abstained": candidate.abstained,
    }


def _run_queries_mine(args: argparse.Namespace) -> int:
    """Execute `syn queries mine` and print its result; return the exit code.

    Delegates the analysis to `brain.query_mining.mine_candidates` (SQL-side
    aggregation, the OR.K1 no-rollup guard, the three candidate classes) and
    renders it — either the fail-loud YAML fragment (`_render_mine_yaml`) or,
    with `--json`, a ranked payload carrying each candidate's rationale.
    Never opens `planning/retrieval-golden-set.yaml` for writing: that file
    is only ever read, to build the exclusion set. An empty result prints a
    friendly message and exits 0 — not a crash, not a non-zero exit.
    """
    from database.session import db_session  # pylint: disable=import-outside-toplevel

    from brain.query_mining import mine_candidates  # pylint: disable=import-outside-toplevel

    try:
        since = datetime.now() - _parse_since(args.since) if args.since else None
    except InvalidSinceWindowError as exc:
        return _emit_error(exc, as_json=args.json)

    min_count = args.min_count if args.min_count is not None else 2

    try:
        with next(db_session()) as session:  # type: ignore[arg-type]
            candidates = mine_candidates(
                session,
                min_count=min_count,
                include_singletons=args.include_singletons,
                since=since,
            )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return _emit_error(exc, as_json=args.json)

    if args.limit is not None:
        candidates = candidates[: args.limit]

    if not candidates:
        if args.json:
            print(json.dumps({"candidates": [], "count": 0}))
        else:
            print("No mining candidates — nothing in the log fit any of the three classes.")
        return 0

    if args.json:
        print(
            json.dumps(
                {
                    "candidates": [_mine_candidate_to_json_dict(c) for c in candidates],
                    "count": len(candidates),
                }
            )
        )
    else:
        print(_render_mine_yaml(candidates), end="")

    return 0


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
        "mcp": _run_mcp,
        "embed": _run_embed,
        "ingest": _run_ingest,
        "prune": _run_prune,
        "refresh": _run_refresh,
        "stale": _run_stale,
        "routine": _run_routine,
        "eval": _run_eval,
        "queries": _run_queries,
    }
    if args.command == "eval" and getattr(args, "eval_subcommand", None) == "promote":
        return _run_eval_promote(args)
    if args.command == "queries" and getattr(args, "queries_subcommand", None) == "mine":
        return _run_queries_mine(args)
    return dispatch[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
