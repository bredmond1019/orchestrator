"""run_eval.py — Offline eval CLI for the Bastion Program Block OR.U eval harness.

Drives an ``evals.slice.EvalSlice`` end to end from the command line: loads
already-recorded domain data (e.g. the coding domain's SDLC run telemetry),
builds the slice, executes + persists it via ``evals.runner.run_slice``,
prints a by-domain/by-model pass-rate table, and optionally gates a change
(``evals.gate.gate_change``) or emits a routing config file.

This script runs from the CLI — it is NOT a workflow node and is NOT run by
Celery. Per the block's design principle (D33 / local D8): this is an
*offline* eval harness, not a runtime router — ``--emit-routing`` only ever
PRODUCES a routing config file; nothing in ``app/core/`` or
``app/workflows/`` reads it (enforcement is a separate, out-of-scope block).

Usage:
    python scripts/run_eval.py --slice coding [--models MODEL ...] [--dry-run]
    python scripts/run_eval.py --slice coding --gate [--baseline RUN_ID] [--min-delta F]
    python scripts/run_eval.py --slice coding --emit-routing PATH [--quality-floor F]

Args:
    --slice NAME          Registered eval slice to run (currently: "coding").
    --models MODEL ...    Models under test; defaults to the slice builder's
                          own default (the coding slice defaults to a single
                          "recorded" placeholder since it scores historical
                          telemetry rather than live per-model executions).
    --dry-run             List the slice's cases without executing or
                          persisting anything.
    --gate                After running, invoke the one-change
                          self-improvement gate (``evals.gate.gate_change``)
                          for each model under test and print its decision.
                          Exits 0 if every model's decision is "keep", 1 if
                          any is "revert".
    --baseline RUN_ID     Explicit baseline run id for --gate (else the
                          previous run in history is used).
    --min-delta F         Minimum pass-rate improvement required to keep a
                          candidate under --gate (default 0.0).
    --emit-routing PATH   Write a per-model routing config JSON (quality
                          retention vs. cost per model, plus the cheapest
                          model meeting --quality-floor) to PATH. Produce
                          only — nothing reads this file at runtime.
    --quality-floor F     Minimum pass-rate a model must meet to be eligible
                          for --emit-routing's cheapest-model selection
                          (default 0.0 — every model is eligible).
"""

import argparse
import json
import logging
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Slice registry: slice name -> (loader, builder).
#
# ``loader(session) -> list[dict]`` fetches already-recorded domain data (a
# live DB query — the only place this script touches the database beyond
# persisting eval results). ``builder(records, models=...) -> EvalSlice``
# turns that data into an offline, unit-testable ``EvalSlice`` (Task 4/5).
# Adding a new domain slice means registering its (loader, builder) pair
# here — no other CLI wiring is needed.
# ---------------------------------------------------------------------------

_SLICE_REGISTRY: dict[str, tuple[Callable[[Any], list[dict]], Callable[..., Any]]] = {}


def _register_slices() -> None:
    """Populate ``_SLICE_REGISTRY``. Deferred so imports stay lazy (see main())."""
    from evals.slices.coding import (  # pylint: disable=import-outside-toplevel
        build_coding_slice,
        load_coding_records,
    )

    _SLICE_REGISTRY["coding"] = (load_coding_records, build_coding_slice)


def _identity_executor(case: Any, model_name: str) -> Any:
    """Executor for record-scoring slices: the case's input *is* the output.

    The coding slice (Task 5) scores already-recorded telemetry rather than
    invoking a model, so the "execution" step is simply handing the record
    back — this is the executor the block contract's docstring
    (``evals.slices.coding``) says such slices should be paired with.
    """
    del model_name
    return case.input


def _load_slice(slice_name: str, session: Any, models: list[str] | None) -> Any:
    """Load domain records and build the named ``EvalSlice``."""
    loader, builder = _SLICE_REGISTRY[slice_name]
    records = loader(session)
    if models:
        return builder(records, models=models)
    return builder(records)


def _run_cost(run: Any) -> float:
    """Cost figure for a persisted run: measured ``total_cost`` if tracked,
    else the measured wall-clock duration as a proxy, else 0.0.

    Never fabricates a cost — only real, already-measured fields on the
    persisted ``EvalRun`` are used.
    """
    if run.total_cost is not None:
        return run.total_cost
    return run.total_duration_seconds or 0.0


def _format_table(runs: list[Any]) -> str:
    """Render a by-domain/by-model pass-rate table (plus cost/duration) for stdout."""
    header = (
        f"{'domain':<14} {'model':<24} {'pass_rate':>10} {'cases':>7} "
        f"{'cost':>10} {'duration_s':>10}"
    )
    lines = [header, "-" * len(header)]
    for run in runs:
        lines.append(
            f"{run.domain:<14} {run.model_name:<24} {run.pass_rate:>10.4f} "
            f"{run.case_count:>7} {_run_cost(run):>10.4f} "
            f"{(run.total_duration_seconds or 0.0):>10.4f}"
        )
    return "\n".join(lines)


def _build_routing_config(eval_slice: Any, runs: list[Any], quality_floor: float) -> dict:
    """Build the per-model routing config: quality (pass-rate) vs. cost per
    model, plus the cheapest model meeting ``quality_floor``.

    PRODUCE ONLY: this dict is written to a file by ``--emit-routing`` and
    read by nobody else in this codebase — wiring it into runtime node
    config is a separate, out-of-scope block per the block contract.
    """
    models: dict[str, dict[str, float]] = {
        run.model_name: {"quality": run.pass_rate, "cost": _run_cost(run)} for run in runs
    }
    eligible = {name: v for name, v in models.items() if v["quality"] >= quality_floor}
    selected = min(eligible, key=lambda name: eligible[name]["cost"]) if eligible else None

    return {
        "slice": eval_slice.name,
        "domain": eval_slice.domain,
        "quality_floor": quality_floor,
        "models": models,
        "selected_model": selected,
    }


def main(argv: list[str] | None = None) -> int:
    """Entry point for the offline eval CLI. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        description="Run an offline eval slice, print a pass-rate table, and "
        "optionally gate a change or emit a routing config."
    )
    parser.add_argument(
        "--slice",
        required=True,
        help="Registered eval slice to run (e.g. 'coding').",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=None,
        metavar="MODEL",
        help="Models under test (default: the slice builder's own default).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the slice's cases without executing or persisting anything.",
    )
    parser.add_argument(
        "--gate",
        action="store_true",
        help="Invoke the one-change self-improvement gate for each model under "
        "test after running; exits 0 on keep, 1 if any model reverts.",
    )
    parser.add_argument(
        "--baseline",
        dest="baseline_run_id",
        default=None,
        metavar="RUN_ID",
        help="Explicit baseline run id for --gate (else the previous run in "
        "history is used).",
    )
    parser.add_argument(
        "--min-delta",
        type=float,
        default=0.0,
        metavar="F",
        help="Minimum pass-rate improvement required to keep a candidate "
        "under --gate (default: 0.0).",
    )
    parser.add_argument(
        "--emit-routing",
        dest="emit_routing_path",
        default=None,
        metavar="PATH",
        help="Write a per-model routing config JSON to PATH. Produce only — "
        "nothing in app/ reads this file.",
    )
    parser.add_argument(
        "--quality-floor",
        type=float,
        default=0.0,
        metavar="F",
        help="Minimum pass-rate a model must meet to be eligible for "
        "--emit-routing's cheapest-model selection (default: 0.0).",
    )
    args = parser.parse_args(argv)

    # Set up sys.path for imports from app/ (mirrors scripts/index_brain.py).
    app_dir = Path(__file__).resolve().parent.parent / "app"
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))

    _register_slices()
    if args.slice not in _SLICE_REGISTRY:
        raise SystemExit(
            f"Error: unknown --slice {args.slice!r}; registered slices: "
            f"{sorted(_SLICE_REGISTRY)}"
        )

    baseline_run_id: uuid.UUID | None = None
    if args.baseline_run_id:
        baseline_run_id = uuid.UUID(args.baseline_run_id)

    # db_session is lazily imported so --dry-run's callers can patch it at
    # its source module path (mirrors scripts/index_brain.py's pattern).
    from database.session import db_session  # pylint: disable=import-outside-toplevel

    with next(db_session()) as session:  # type: ignore[arg-type]
        eval_slice = _load_slice(args.slice, session, args.models)

        if args.dry_run:
            logger.info(
                "Dry run — %d case(s) in slice %s (domain=%s); no execution or persistence.",
                len(eval_slice.cases),
                eval_slice.name,
                eval_slice.domain,
            )
            for case in eval_slice.cases:
                logger.info("  %s", case.case_id)
            return 0

        from evals.runner import run_slice  # pylint: disable=import-outside-toplevel

        runs = run_slice(eval_slice, session, _identity_executor)

        print(_format_table(runs))

        exit_code = 0

        if args.gate:
            from evals.gate import gate_change  # pylint: disable=import-outside-toplevel

            for run in runs:
                decision = gate_change(
                    session,
                    eval_slice.name,
                    run.model_name,
                    baseline_run_id=baseline_run_id,
                    min_delta=args.min_delta,
                )
                print(f"[gate] {run.model_name}: {decision.decision} — {decision.reason}")
                if decision.decision != "keep":
                    exit_code = 1

        if args.emit_routing_path:
            routing = _build_routing_config(eval_slice, runs, args.quality_floor)
            Path(args.emit_routing_path).write_text(
                json.dumps(routing, indent=2), encoding="utf-8"
            )
            logger.info("Wrote routing config to %s", args.emit_routing_path)

        return exit_code


if __name__ == "__main__":
    sys.exit(main())
