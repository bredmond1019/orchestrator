"""app/brain/eval/report.py — render a single `RetrievalRunReport` to a
self-contained, publishable Markdown report.

This module owns the disclosure boundary between the eval harness's private
run data (`app/brain/eval/models.py::RetrievalRunReport`, which ultimately
derives from `planning/retrieval-golden-set.yaml` — an operator's private
cross-repo planning corpus) and anything that might be shown to a stranger
or a prospect.

The disclosure rule is an ALLOW-LIST, not a denylist or a generic filter:
`_ALLOWED_METRIC_KEYS`, `_ALLOWED_CORPUS_FIELDS` and the field-by-field
rendering below name exactly what may reach the output. An allow-list fails
CLOSED when a field is added upstream to `RetrievalRunReport` (the new field
is simply never rendered until someone deliberately adds it here); a
denylist fails OPEN (a new field renders by default, leaking whatever it
holds). Rendering below never iterates the run model's `__dict__`,
`dataclasses.fields()`, `to_dict()`, or any other generic field-enumeration
mechanism — every value that reaches the returned string is read off a
named, specific attribute.

Fields that must NEVER appear in rendered output, directly or in a
debug/summary line: `RetrievalCase.query`, `RetrievalCase.expect_docs`,
`RetrievalCase.notes`, `CaseResult.matched_docs`, or any document title,
`doc_id`, file path, or repo name. None of those are read by this module at
all — `RetrievalRunReport.results` is only ever consulted for `case_id`
(used solely to bucket a COUNT by category, per `_category_of` below — the
case_id itself is never printed) and the metric fields already covered by
`_ALLOWED_METRIC_KEYS`.
"""

from dataclasses import dataclass
from pathlib import Path

from brain.eval import runner
from brain.eval.models import RetrievalRunReport

# --- The allow-list ---------------------------------------------------

# The exact set of `aggregate` (and `aggregate_stats`) keys this renderer
# knows how to label and define. `runner._aggregate` is the source of
# truth for what actually gets produced; this module never assumes a fixed
# set of keys is present — it renders whatever keys are ACTUALLY in
# `report.aggregate` (so an added or renamed metric survives, sorted for
# determinism), but only ever emits the numeric value + this canned
# definition/label for a KNOWN key. An unrecognized key still renders (its
# raw name and value) with a generic definition placeholder rather than
# being dropped or raising — see `_metric_definition` — because the point
# of this renderer is never to silently hide a metric that exists.
_ALLOWED_METRIC_KEYS: tuple[str, ...] = (
    "recall_at_5",
    "recall_at_10",
    "mrr",
    "groundedness",
    "groundedness_on_hits",
    "abstain_correctness",
)

# Human labels for the known metrics, in the canonical order above.
_METRIC_LABELS: dict[str, str] = {
    "recall_at_5": "Recall@5",
    "recall_at_10": "Recall@10",
    "mrr": "MRR",
    "groundedness": "Groundedness",
    "groundedness_on_hits": "Groundedness (on hits)",
    "abstain_correctness": "Abstain correctness",
}

# Definitions for the known metrics. `groundedness`'s definition carries the
# first mandatory honesty statement inline as well as in the dedicated
# honesty-statements section, since a reader skimming only the definitions
# table must not come away thinking it is an LLM-judged faithfulness score.
_METRIC_DEFINITIONS: dict[str, str] = {
    "recall_at_5": (
        "Fraction of positive cases (cases with an expected document) whose "
        "expected document appears in the top 5 retrieved results."
    ),
    "recall_at_10": (
        "Fraction of positive cases whose expected document appears in the "
        "top 10 retrieved results."
    ),
    "mrr": (
        "Mean reciprocal rank of the first expected-document hit across "
        "positive cases (0 when the expected document is not retrieved at "
        "all)."
    ),
    "groundedness": (
        "Lexical content-word overlap between the case query and the "
        "highest-ranked chunk of the expected document, averaged over "
        "positive cases. This is NOT an LLM-judged faithfulness score — "
        "there is no LLM-authored answer at retrieval-eval time, so the "
        "query text stands in as the claim being checked against the "
        "retrieved content."
    ),
    "groundedness_on_hits": (
        "The same lexical-overlap groundedness measure, restricted to "
        "positive cases that actually retrieved their expected document — "
        "separates 'retrieved nothing' from 'retrieved something "
        "ungrounded'."
    ),
    "abstain_correctness": (
        "Fraction of ALL cases (positive and negative) where the system's "
        "abstain decision matched the case's expected abstain label."
    ),
}

_UNKNOWN_METRIC_DEFINITION = "(no definition recorded for this metric)"

# The corpus-fingerprint subfields that may be rendered as provenance —
# named explicitly so a future field added to `_fingerprint_corpus`'s
# return dict (`runner.py`) does not flow through by default.
_ALLOWED_CORPUS_FIELDS: tuple[tuple[str, str], ...] = (
    ("chunk_count", "Chunks indexed"),
    ("file_count", "Files indexed"),
    ("edge_count", "Structural edges"),
    ("max_indexed_at", "Newest document indexed at"),
)

# The mandatory honesty statements (block AC3/AC4). Free prose, deliberately
# not derived from any field on the run model.
_HONESTY_STATEMENTS: tuple[str, ...] = (
    "**Groundedness is lexical content-word overlap, not an LLM-judged "
    "faithfulness score.** There is no LLM-authored answer at "
    "retrieval-eval time — `groundedness` measures how much of the case "
    "query's content words appear in the top-matching retrieved chunk, "
    "nothing more.",
    "**These are retrieval-only metrics.** No faithfulness score, answer "
    "relevancy score, or answer correctness score exists in this harness — "
    "those are generation-side metrics this eval does not measure.",
)

# `case_id`'s first `-`-delimited segment -> the category taxonomy it
# encodes (mirrors `tests/brain/test_golden_set_schema.py::_PREFIX_TO_CATEGORY`
# and `RetrievalCase.category`'s docstring; not imported from the test
# module — deliberately duplicated, same discipline as `scorer.py`'s
# mirrored `VerifyCitationsNode` functions). `RetrievalCase.category` itself
# never reaches `RetrievalRunReport` (only `CaseResult.case_id` does), so
# category counts are read off this prefix convention rather than a stored
# category field.
_PREFIX_TO_CATEGORY: dict[str, str] = {
    "archive": "archive",
    "id": "identifier",
    "neg": "negative",
    "hijack": "hijack",
    "mined": "mined",
}

_UNKNOWN_CATEGORY = "uncategorized"


def _category_of(case_id: str) -> str:
    """The category a `case_id` encodes via its first `-`-delimited segment.

    Never raises on an unrecognized prefix — buckets it under
    `_UNKNOWN_CATEGORY` instead, so a future id naming convention change
    degrades to a visible "uncategorized" count rather than crashing the
    renderer.
    """
    prefix = case_id.split("-", 1)[0] if case_id else ""
    return _PREFIX_TO_CATEGORY.get(prefix, _UNKNOWN_CATEGORY)


@dataclass(frozen=True)
class _MetricRow:
    """One row of the summary metrics table — allow-listed fields only."""

    key: str
    label: str
    value: float
    ci_low: float | None
    ci_high: float | None


def _format_float(value: float) -> str:
    """Deterministic 4-decimal formatting for a metric value."""
    return f"{value:.4f}"


def _metric_label(key: str) -> str:
    """The human label for a metric key, falling back to the raw key."""
    return _METRIC_LABELS.get(key, key)


def _metric_definition(key: str) -> str:
    """The definition prose for a metric key, falling back to a generic
    placeholder for an unrecognized key rather than raising or omitting it.
    """
    return _METRIC_DEFINITIONS.get(key, _UNKNOWN_METRIC_DEFINITION)


def _metric_rows(report: RetrievalRunReport) -> list[_MetricRow]:
    """Build one `_MetricRow` per key actually present in `report.aggregate`,
    sorted alphabetically for deterministic rendering (never filesystem or
    dict-insertion order). Confidence intervals are read from
    `report.aggregate_stats` (a SIBLING top-level field, `None` on the 14
    pre-existing run files) and render as `None`/`None` (rendered "n/a")
    when unavailable for this run, or for this specific metric.
    """
    stats = report.aggregate_stats or {}
    rows: list[_MetricRow] = []
    for key in sorted(report.aggregate.keys()):
        value = report.aggregate[key]
        metric_stats = stats.get(key) if isinstance(stats, dict) else None
        ci_low = metric_stats.get("lo") if isinstance(metric_stats, dict) else None
        ci_high = metric_stats.get("hi") if isinstance(metric_stats, dict) else None
        rows.append(
            _MetricRow(
                key=key,
                label=_metric_label(key),
                value=value,
                ci_low=ci_low,
                ci_high=ci_high,
            )
        )
    return rows


def _render_summary_table(rows: list[_MetricRow]) -> str:
    """The summary metrics table: one row per metric, value + 95% CI."""
    lines = [
        "| Metric | Value | 95% CI |",
        "| --- | --- | --- |",
    ]
    for row in rows:
        if row.ci_low is not None and row.ci_high is not None:
            ci_text = f"[{_format_float(row.ci_low)}, {_format_float(row.ci_high)}]"
        else:
            ci_text = "n/a"
        lines.append(f"| {row.label} | {_format_float(row.value)} | {ci_text} |")
    return "\n".join(lines)


def _render_definitions(rows: list[_MetricRow]) -> str:
    """The metric-definitions section, keyed off the same rows the summary
    table renders — so a metric can never appear in one section and not the
    other.
    """
    lines = []
    for row in rows:
        lines.append(f"- **{row.label}** (`{row.key}`): {_metric_definition(row.key)}")
    return "\n".join(lines)


def _render_honesty_statements() -> str:
    """The two mandatory honesty statements, each its own paragraph."""
    return "\n\n".join(_HONESTY_STATEMENTS)


def _render_corpus_fingerprint(report: RetrievalRunReport) -> str:
    """The corpus-provenance section. `report.corpus` is `None` on
    pre-existing run files (never populated before the block that added
    it) — renders "unavailable" rather than raising.
    """
    corpus = report.corpus
    if not corpus:
        return "Corpus fingerprint unavailable for this run (predates provenance stamping)."
    lines = ["| Field | Value |", "| --- | --- |"]
    for field_name, label in _ALLOWED_CORPUS_FIELDS:
        value = corpus.get(field_name)
        lines.append(f"| {label} | {value if value is not None else 'n/a'} |")
    return "\n".join(lines)


def _render_case_counts(report: RetrievalRunReport) -> str:
    """Case counts by category — counts only, never the cases or their
    ids. Categories with zero cases in this run are omitted rather than
    rendered as a zero row (nothing to disclose about a category this run
    didn't exercise).
    """
    counts: dict[str, int] = {}
    for result in report.results:
        category = _category_of(result.case_id)
        counts[category] = counts.get(category, 0) + 1
    lines = ["| Category | Count |", "| --- | --- |"]
    for category in sorted(counts):
        lines.append(f"| {category} | {counts[category]} |")
    lines.append(f"| **Total** | **{report.case_count}** |")
    return "\n".join(lines)


# --- Run history (task 2) ----------------------------------------------

# `case_id`/annotation prose is free text, deliberately not derived from
# any field on the run model — same discipline as `_HONESTY_STATEMENTS`.
# Keyed off the run's own filename (its `generated_at` stamp, since
# `write_report` names the file after it) so adding a future annotation is
# a data edit here, never a string hunt through the renderer.
#
# The 2026-08-06 entry annotates the FIRST run whose `recall_at_10` shows
# the drop (`2026-08-06T13-56-48Z.json`, 0.9412 -> 0.8824 against the
# immediately preceding run) with the CORRECTED cause: a keyword-weight
# change, per commit `aa47bf81` — not the digest-crowding hypothesis the
# `brain-retrieval-digest-crowding` carryover was originally opened under.
_RUN_ANNOTATIONS: dict[str, str] = {
    "2026-08-06T13-56-48Z.json": (
        "Regression: recall@10 dropped from the prior run (0.9412 -> "
        "0.8824). Corrected cause: a keyword-weight change, per commit "
        "`aa47bf81` — NOT the digest-crowding hypothesis originally "
        "suspected under carryover `brain-retrieval-digest-crowding`."
    ),
}


def _list_run_files(runs_dir: Path) -> list[Path]:
    """Every run JSON in `runs_dir`, excluding the baseline pointer file.

    `baseline.json` (`runner.DEFAULT_BASELINE_POINTER`) is a promotion
    pointer, not a run — including it would double-count a run and corrupt
    every delta. Non-JSON entries (`index.md`, `.gitkeep`, and the
    `snapshots/`/`query-log/` subdirectories) are excluded for free by the
    `*.json` glob, which is non-recursive and directory-blind.
    """
    baseline_name = runner.DEFAULT_BASELINE_POINTER.name
    return sorted(path for path in runs_dir.glob("*.json") if path.name != baseline_name)


def _load_runs(runs_dir: Path) -> list[dict]:
    """Load every run file in `runs_dir`, sorted chronologically by each
    run's own `generated_at` field (never filesystem order — glob order is
    not guaranteed, and mtimes can be rewritten by a checkout).

    A file that fails to load (unreadable, or does not parse as JSON) is
    skipped rather than raised — the loader must not raise on any file
    currently in the directory, since the corpus is a heterogeneous mix of
    14 pre-existing files that predate several fields.
    """
    runs: list[dict] = []
    for path in _list_run_files(runs_dir):
        try:
            run = runner.load_report(path)
        except (OSError, ValueError):
            continue
        run = dict(run)
        run["_filename"] = path.name
        runs.append(run)
    runs.sort(key=lambda r: r.get("generated_at") or r.get("_filename", ""))
    return runs


def _history_metric_keys(runs: list[dict]) -> tuple[str, ...]:
    """The union of `aggregate` keys across every loaded run, sorted
    alphabetically (never insertion or filesystem order) so an added or
    renamed metric widens the table instead of silently vanishing.
    """
    keys: set[str] = set()
    for run in runs:
        keys.update((run.get("aggregate") or {}).keys())
    return tuple(sorted(keys))


@dataclass(frozen=True)
class _HistoryCell:
    """One (metric, run) cell: the value and its delta from the prior run.

    Both are `None` when the metric is absent from this run, or (for
    `delta`) absent from the immediately preceding run, or this is the
    first run in the table — every `None` case renders "n/a", never 0.0
    (0.0 is a real, meaningful delta value and must not be confused with
    "no data").
    """

    value: float | None
    delta: float | None


@dataclass(frozen=True)
class _HistoryRow:
    """One run's row in the history table."""

    generated_at: str
    cells: dict[str, _HistoryCell]
    annotation: str | None


def _history_rows(runs: list[dict], metric_keys: tuple[str, ...]) -> list[_HistoryRow]:
    """Build one `_HistoryRow` per run, in the given (already-sorted)
    order, with a delta computed against the immediately preceding run for
    each metric independently.
    """
    rows: list[_HistoryRow] = []
    previous_aggregate: dict[str, float] | None = None
    for run in runs:
        aggregate = run.get("aggregate") or {}
        cells: dict[str, _HistoryCell] = {}
        for key in metric_keys:
            value = aggregate.get(key)
            prev_value = previous_aggregate.get(key) if previous_aggregate else None
            delta = value - prev_value if value is not None and prev_value is not None else None
            cells[key] = _HistoryCell(value=value, delta=delta)
        filename = run.get("_filename", "")
        rows.append(
            _HistoryRow(
                generated_at=run.get("generated_at") or filename,
                cells=cells,
                annotation=_RUN_ANNOTATIONS.get(filename),
            )
        )
        previous_aggregate = aggregate
    return rows


def _format_delta(delta: float | None) -> str:
    """Signed, deterministic 4-decimal delta formatting; "n/a" when absent."""
    if delta is None:
        return "n/a"
    sign = "+" if delta >= 0 else ""
    return f"{sign}{_format_float(delta)}"


def _render_history_table(rows: list[_HistoryRow], metric_keys: tuple[str, ...]) -> str:
    """The chronological run-history table: one row per run, a value column
    and a delta column per metric, plus a free-text annotation column.
    Empty when there is no run history to show.
    """
    if not rows:
        return "No run history available."
    header = ["Run"]
    for key in metric_keys:
        label = _metric_label(key)
        header.append(label)
        header.append(f"{label} Δ")
    header.append("Notes")
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * len(header)) + " |",
    ]
    for row in rows:
        cells = [f"`{row.generated_at}`"]
        for key in metric_keys:
            cell = row.cells[key]
            cells.append(_format_float(cell.value) if cell.value is not None else "n/a")
            cells.append(_format_delta(cell.delta))
        cells.append(row.annotation or "")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _render_baseline_section(runs_dir: Path) -> str:
    """The promoted-baseline pin, read from `baseline.json` under
    `runs_dir` — never asserted. States plainly when no run has ever been
    promoted, rather than implying a pin that does not exist (the ticket
    was authored when the baseline lived only in prose; `runner.promote_run`
    / `DEFAULT_BASELINE_POINTER` have since made it a real, readable
    artifact).

    Deliberately reads only `run` and `promoted_at` off the pointer — the
    pointer's free-text `reason` field is operator-authored prose and is
    outside this renderer's allow-list, same discipline as everywhere else
    in this module.
    """
    pointer_path = runs_dir / runner.DEFAULT_BASELINE_POINTER.name
    try:
        pointer = runner.load_baseline_pointer(pointer_path)
    except (OSError, ValueError):
        pointer = None
    if pointer is None:
        return "No run has been promoted to the baseline pin."
    run_name = pointer.get("run", "unknown")
    promoted_at = pointer.get("promoted_at", "unknown")
    return f"Run `{run_name}` is pinned as the baseline (promoted {promoted_at})."


def render_run(report: RetrievalRunReport, runs_dir: str | Path | None = None) -> str:
    """Render one `RetrievalRunReport` to a self-contained Markdown report.

    Only ever reads the allow-listed fields documented at module level —
    `report.aggregate`, `report.aggregate_stats`, `report.generated_at`,
    `report.case_count`, `report.corpus` (specific subfields only), and
    `result.case_id` on each `report.results` entry (for category bucketing
    only, never printed itself). No other field of `RetrievalRunReport`,
    `CaseResult`, or `RetrievalCase` is read.

    The run-history and baseline sections are sourced separately, from the
    run JSON files already written under `runs_dir` (default
    `runner.DEFAULT_RUNS_DIR`) — never from `report` itself, so a report
    rendered with `--no-write` (before the current run has been persisted)
    still gets a history section covering every PRIOR run on disk.
    """
    rows = _metric_rows(report)
    runs_dir_path = Path(runs_dir) if runs_dir is not None else runner.DEFAULT_RUNS_DIR
    history_runs = _load_runs(runs_dir_path)
    metric_keys = _history_metric_keys(history_runs)
    history_rows = _history_rows(history_runs, metric_keys)
    sections = [
        "# Retrieval Evaluation Report",
        "",
        f"Run: `{report.generated_at}`  \nCases evaluated: {report.case_count}",
        "",
        "## Summary metrics",
        "",
        _render_summary_table(rows),
        "",
        "## What these numbers mean",
        "",
        _render_honesty_statements(),
        "",
        "## Metric definitions",
        "",
        _render_definitions(rows),
        "",
        "## Corpus fingerprint",
        "",
        _render_corpus_fingerprint(report),
        "",
        "## Case counts by category",
        "",
        _render_case_counts(report),
        "",
        "## Run history",
        "",
        _render_history_table(history_rows, metric_keys),
        "",
        "## Baseline",
        "",
        _render_baseline_section(runs_dir_path),
        "",
    ]
    return "\n".join(sections)
