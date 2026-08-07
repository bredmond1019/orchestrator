"""app/brain/query_mining.py — OR.2.E read-time query-log mining core.

Turns the write-only `retrieval_queries` log (`app/brain/query_log.py`) into
reviewable golden-set candidates. This module holds the analysis core only —
`app/brain/cli.py`'s `syn queries mine` renders it (mirrors the
`reconcile.py` holds-logic / `cli.py` only-renders split already used for
`deep_stale()`). No CLI concerns live here.

**Why a read-time SQL aggregation does not violate the OR.K1 no-rollup
guard.** `app/database/retrieval_query.py:8-15` is explicit: no aggregation
table, no rollup job, no dashboard — the moment one is needed, that
capability belongs in engine-rs (the D51 guard). `mine_candidates` below
computes `GROUP BY query`, `COUNT(*)`, `AVG(retrieval_confidence)`, and
`MAX(created_at)` **at read time, on every call, over the live table** — it
writes nothing back and stores no result. That is exactly the shape
`abstain_rate` (`app/brain/cli.py::_run_queries`) already uses for a
read-time statistic. What the guard forbids is a *stored* rollup: a table or
column that caches this aggregation so a future read can skip recomputing
it. This module never does that — every candidate list is derived fresh
from `retrieval_queries` and discarded the moment the process exits.

**The tool prioritizes a review list; it never judges, and it never
writes.** In particular:

- It never opens `planning/retrieval-golden-set.yaml` for writing — only for
  reading, to build the exclusion set (a query already in the golden set is
  not a candidate).
- The `confidently-wrong-suspect` class is a **heuristic, not a detector**.
  You cannot tell "the top hit is wrong" from the log alone — high
  confidence with a small `top_scores[0] - top_scores[1]` gap and/or a
  keyword-dominated `via_mix` is *suggestive*, never conclusive. Overstating
  this is precisely how the tool would poison the golden set it is meant to
  feed. Every caller-facing surface (this module's candidates and whatever
  `syn queries mine` renders from them) must keep saying so.
- Which `abstained` rows are real gaps (`expect_abstain: true` material)
  versus retrieval failures on something present (a positive-case material)
  is **never decided here** — the human reviewing the emitted list decides.
"""

import statistics
from dataclasses import dataclass
from datetime import datetime

from database.retrieval_query import RetrievalQuery
from sqlalchemy import func
from sqlalchemy.orm import Session

DEFAULT_MIN_COUNT = 2

CLASS_ABSTAINED = "abstained"
CLASS_LOW_CONFIDENCE_ANSWERED = "low-confidence-answered"
CLASS_CONFIDENTLY_WRONG_SUSPECT = "confidently-wrong-suspect"

# Heuristic constants for `CLASS_CONFIDENTLY_WRONG_SUSPECT` — deliberately not
# configurable via CLI flags (the spec's "deferred deliberately" list already
# excludes constant-column-shaped knobs; these are the same shape). Both are
# heuristic thresholds, not calibrated detectors — see the module docstring.
_SCORE_GAP_SUSPECT_THRESHOLD = 0.05
_KEYWORD_DOMINANCE_THRESHOLD = 0.5

CONFIDENTLY_WRONG_SUSPECT_CAVEAT = (
    "heuristic, not a detector — a small top-score gap and/or a "
    "keyword-dominated via_mix is suggestive that the top hit may be wrong, "
    "never proof; the log alone cannot confirm it"
)


@dataclass(frozen=True)
class MinedCandidate:  # pylint: disable=too-many-instance-attributes
    """One mined golden-set candidate — a distinct logged query text plus
    the read-time stats and heuristic classification that surfaced it.

    `source_query_id` is the `retrieval_queries.id` of the most recently
    logged row for this query text (the representative row `top_scores`,
    `via_mix`, and `abstained` are read from). `rationale` is a short,
    human-readable string explaining why this candidate was classified the
    way it was — never a substitute for the caller reading `class_` itself.
    """

    query: str
    count: int
    avg_confidence: float | None
    last_seen: datetime | None
    class_: str
    rationale: str
    source_query_id: str | None
    top_doc_ids: list
    top_scores: list
    via_mix: dict
    abstained: bool


def _load_golden_set_queries(golden_set_path=None) -> set[str]:
    """Return the set of verbatim `query` strings already in the golden set.

    Reads `planning/retrieval-golden-set.yaml` via `brain.eval.load_cases`
    (the same parser the eval harness uses) — imported lazily to avoid a
    hard import-time dependency from `app/brain/query_mining.py` on
    `app/brain/eval/`. Never opens the file for writing.
    """
    from brain.eval import load_cases  # pylint: disable=import-outside-toplevel
    from brain.eval.runner import DEFAULT_GOLDEN_SET_PATH  # pylint: disable=import-outside-toplevel

    path = golden_set_path or DEFAULT_GOLDEN_SET_PATH
    cases = load_cases(path)
    return {case.query for case in cases}


def _bottom_quartile_threshold(values: list[float]) -> float | None:
    """Return the bottom-quartile (Q1) boundary of `values`, or `None` if
    `values` is empty. Falls back to the single value (len == 1) or the
    minimum (fewer than 4 points — too few for `statistics.quantiles` to be
    meaningful) rather than raising."""
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    if len(values) < 4:
        return min(values)
    return statistics.quantiles(values, n=4, method="inclusive")[0]


def _classify(
    *,
    abstained: bool,
    avg_confidence: float | None,
    low_confidence_threshold: float | None,
    top_scores: list | None,
    via_mix: dict | None,
) -> tuple[str, str] | None:
    """Classify one candidate group into one of the three classes, or
    return `None` if it fits none of them (excluded from the candidate
    list). Returns `(class_, rationale)`."""
    if abstained:
        return (
            CLASS_ABSTAINED,
            "abstained=true — human decides: a genuine gap (expect_abstain "
            "case) or a retrieval failure on something present (positive case)",
        )

    if (
        avg_confidence is not None
        and low_confidence_threshold is not None
        and avg_confidence <= low_confidence_threshold
    ):
        return (
            CLASS_LOW_CONFIDENCE_ANSWERED,
            f"avg_confidence={avg_confidence:.4f} is in the bottom quartile "
            f"(<= {low_confidence_threshold:.4f}) of non-abstained candidates — "
            "a near-miss where a ranking change would show up first",
        )

    suspect_signals = []
    has_two_scores = (
        top_scores
        and len(top_scores) >= 2
        and top_scores[0] is not None
        and top_scores[1] is not None
    )
    if has_two_scores:
        gap = top_scores[0] - top_scores[1]
        if gap <= _SCORE_GAP_SUSPECT_THRESHOLD:
            suspect_signals.append(f"top-score gap {gap:.4f} <= {_SCORE_GAP_SUSPECT_THRESHOLD}")
    if via_mix:
        total = sum(via_mix.values())
        keyword_count = via_mix.get("keyword", 0)
        if total and (keyword_count / total) >= _KEYWORD_DOMINANCE_THRESHOLD:
            suspect_signals.append(
                f"via_mix keyword-dominated ({keyword_count}/{total})"
            )

    if suspect_signals:
        return (
            CLASS_CONFIDENTLY_WRONG_SUSPECT,
            f"{CONFIDENTLY_WRONG_SUSPECT_CAVEAT}; signals: " + "; ".join(suspect_signals),
        )

    return None


def mine_candidates(  # pylint: disable=too-many-locals
    session: Session,
    *,
    min_count: int = DEFAULT_MIN_COUNT,
    include_singletons: bool = False,
    since: datetime | None = None,
    golden_set_path=None,
    golden_set_queries: set[str] | None = None,
) -> list[MinedCandidate]:
    """Return read-time-mined golden-set candidates from `retrieval_queries`.

    Applies ALL of these filters together:

    - excludes `surface == "eval"` rows (harness traffic, never real usage)
    - excludes any query text appearing verbatim in the golden set
      (`golden_set_queries`, or loaded from `golden_set_path` /
      `DEFAULT_GOLDEN_SET_PATH` if not given — covers both cases in the
      golden set already and the ~2603 historical rows `OR.2.A`'s `surface`
      tagging deliberately does not retroactively attribute)
    - excludes queries seen fewer than `min_count` times (default 2, since
      the log holds only ~20 genuinely-human distinct queries) unless
      `include_singletons` is set

    Aggregation (`GROUP BY query`, `COUNT`, `AVG`, `MAX(created_at)`) is
    SQL-side — this function never calls `GenericRepository.get_all()` or
    otherwise fetches the whole table. A second, still-filtered query reads
    only the rows for queries that survive the frequency/golden-set filter,
    to pick each candidate's most recent row (`top_scores`, `via_mix`,
    `abstained`) for classification.

    Returns one `MinedCandidate` per query that lands in one of the three
    classes (`CLASS_ABSTAINED`, `CLASS_LOW_CONFIDENCE_ANSWERED`,
    `CLASS_CONFIDENTLY_WRONG_SUSPECT`); a query matching none of them is
    silently excluded — this tool prioritizes a review list, not an
    exhaustive one. An empty (or fully filtered) log returns `[]`, never
    raises.
    """
    excluded_queries = (
        golden_set_queries
        if golden_set_queries is not None
        else _load_golden_set_queries(golden_set_path)
    )

    effective_min_count = 1 if include_singletons else min_count

    aggregate_query = session.query(
        RetrievalQuery.query,
        func.count(RetrievalQuery.id).label("count"),  # pylint: disable=not-callable
        func.avg(RetrievalQuery.retrieval_confidence).label("avg_confidence"),  # pylint: disable=not-callable
        func.max(RetrievalQuery.created_at).label("last_seen"),  # pylint: disable=not-callable
    ).filter(RetrievalQuery.surface != "eval")

    if since is not None:
        aggregate_query = aggregate_query.filter(RetrievalQuery.created_at >= since)

    aggregate_query = aggregate_query.group_by(RetrievalQuery.query).having(
        func.count(RetrievalQuery.id) >= effective_min_count  # pylint: disable=not-callable
    )

    groups = {
        row.query: {
            "count": row.count,
            "avg_confidence": row.avg_confidence,
            "last_seen": row.last_seen,
        }
        for row in aggregate_query.all()
        if row.query not in excluded_queries
    }

    if not groups:
        return []

    representative_rows_query = (
        session.query(RetrievalQuery)
        .filter(RetrievalQuery.surface != "eval")
        .filter(RetrievalQuery.query.in_(groups.keys()))
        .order_by(RetrievalQuery.created_at.asc())
    )
    if since is not None:
        representative_rows_query = representative_rows_query.filter(
            RetrievalQuery.created_at >= since
        )

    representatives: dict[str, RetrievalQuery] = {}
    for row in representative_rows_query.all():
        # Later rows overwrite earlier ones (ascending order), so the last
        # write wins — the most recent logged row per query text.
        representatives[row.query] = row

    non_abstained_confidences = [
        info["avg_confidence"]
        for query_text, info in groups.items()
        if info["avg_confidence"] is not None
        and not getattr(representatives.get(query_text), "abstained", False)
    ]
    low_confidence_threshold = _bottom_quartile_threshold(non_abstained_confidences)

    candidates: list[MinedCandidate] = []
    for query_text, info in groups.items():
        representative = representatives.get(query_text)
        abstained = bool(getattr(representative, "abstained", False))
        top_scores = list(getattr(representative, "top_scores", None) or [])
        via_mix = dict(getattr(representative, "via_mix", None) or {})
        top_doc_ids = list(getattr(representative, "top_doc_ids", None) or [])

        classification = _classify(
            abstained=abstained,
            avg_confidence=info["avg_confidence"],
            low_confidence_threshold=low_confidence_threshold,
            top_scores=top_scores,
            via_mix=via_mix,
        )
        if classification is None:
            continue
        class_, rationale = classification

        candidates.append(
            MinedCandidate(
                query=query_text,
                count=info["count"],
                avg_confidence=info["avg_confidence"],
                last_seen=info["last_seen"],
                class_=class_,
                rationale=rationale,
                source_query_id=str(representative.id) if representative is not None else None,
                top_doc_ids=top_doc_ids,
                top_scores=top_scores,
                via_mix=via_mix,
                abstained=abstained,
            )
        )

    candidates.sort(key=lambda c: (c.count, c.last_seen or datetime.min), reverse=True)
    return candidates
