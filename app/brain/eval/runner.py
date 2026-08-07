"""app/brain/eval/runner.py — load the golden set, run it, write the dated report.

Loads `planning/retrieval-golden-set.yaml` (OR.K2 task 2), runs every case
through the promoted retrieval core (`brain.retrieval_engine.retrieve`, OR.K2
task 1), scores each with `brain.eval.scorer.score_case`, and writes a
git-tracked JSON report to `planning/retrieval-eval-runs/<ISO8601>.json` — no
new DB tables (`eval_runs`/`eval_results` are engine-rs's, per D51; a second
aggregator here would be the anti-pattern that decision guards against).

`compare_to_baseline` is a small (~15-line), self-contained signed-delta
diff — at most shaped like `app/evals/gate.py`'s deleted `gate_change`
(OR.X2 removed that module entirely), never imported from it.
"""

import json
from pathlib import Path

import yaml
from database.brain_document import BrainDocument
from database.brain_edge import BrainEdge
from sqlalchemy import func

from brain import retrieval_engine
from brain.eval import scorer
from brain.eval.models import CaseResult, RetrievalCase, RetrievalRunReport
from brain.eval.scorer import score_case

# app/brain/eval/runner.py -> app/brain/eval -> app/brain -> app -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_GOLDEN_SET_PATH = _REPO_ROOT / "planning" / "retrieval-golden-set.yaml"
DEFAULT_RUNS_DIR = _REPO_ROOT / "planning" / "retrieval-eval-runs"


def load_cases(path: str | Path = DEFAULT_GOLDEN_SET_PATH) -> list[RetrievalCase]:
    """Parse the golden-set YAML at `path` into `RetrievalCase` objects."""
    with Path(path).open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)

    cases = []
    for raw in document["cases"]:
        # `source` and `category` are required — direct dict access raises
        # KeyError (a parse error) rather than silently defaulting, same
        # contract `id`/`query` already have above.
        source = raw["source"]
        category = raw["category"]
        source_query_id = raw.get("source_query_id")
        if source_query_id is not None and source != "mined":
            raise ValueError(
                f"case {raw.get('id', raw)!r} sets source_query_id but source is "
                f"{source!r}, not 'mined' — source_query_id is only meaningful for "
                "mined cases"
            )
        cases.append(
            RetrievalCase(
                case_id=raw["id"],
                query=raw["query"],
                expect_docs=tuple(raw.get("expect_docs") or ()),
                expect_abstain=bool(raw.get("expect_abstain", False)),
                source=source,
                category=category,
                source_query_id=source_query_id,
                scope=raw.get("scope"),
                notes=raw.get("notes", ""),
            )
        )
    return cases


def _aggregate(results: list[CaseResult]) -> dict[str, float]:
    """Mean per metric — positive-case metrics over non-`None` readings only,
    `abstain_correctness` over every case (see `models.RetrievalRunReport`).

    `groundedness_on_hits` is the same mean restricted to cases that actually
    matched an `expect_docs` document (`matched_docs` non-empty). It is
    **additive, not a redefinition**: `groundedness` still scores a
    recall-miss as 0.0 (`scorer._groundedness`'s documented contract), which
    means the headline number partly re-measures recall. Reading the two side
    by side separates "we retrieved nothing" from "we retrieved something
    ungrounded" without moving a shipped metric — see
    `planning/artifacts/groundedness-baseline-analysis.md`, where the
    2026-08-02 baseline decomposes as 0.3608 overall vs. 0.5576 on hits and
    all six misses turned out to be corpus-coverage gaps, not ranking
    failures. `compare_to_baseline` iterates the *baseline's* keys, so a
    pre-existing baseline file simply reports no delta for this key rather
    than breaking.
    """
    aggregate: dict[str, float] = {}

    aggregate["abstain_correctness"] = (
        sum(1.0 for r in results if r.abstain_correct) / len(results) if results else 0.0
    )

    metric_field = {
        "recall_at_5": "recall_at_5",
        "recall_at_10": "recall_at_10",
        "mrr": "reciprocal_rank",
        "groundedness": "groundedness",
    }
    for out_key, field_name in metric_field.items():
        values = [
            getattr(r, field_name) for r in results if getattr(r, field_name) is not None
        ]
        aggregate[out_key] = sum(values) / len(values) if values else 0.0

    on_hits = [
        r.groundedness
        for r in results
        if r.groundedness is not None and r.matched_docs
    ]
    aggregate["groundedness_on_hits"] = sum(on_hits) / len(on_hits) if on_hits else 0.0

    return aggregate


def _fingerprint_corpus(session=None) -> dict:
    """The brain corpus's shape at run time — chunk count, distinct file
    count, edge count, and the newest `indexed_at` — read from the same
    session the run uses.

    This is the provenance stamp that makes a run's numbers attributable:
    two runs whose fingerprints differ were measured against different
    corpora and are not directly comparable (see `OR.0.C`'s post-mortem in
    `planning/artifacts/rag-diagnosis-2026-08-07.md`).
    """
    with retrieval_engine._session_scope(session) as db:  # pylint: disable=protected-access
        chunk_count = (
            db.query(func.count(BrainDocument.id)).scalar() or 0  # pylint: disable=not-callable
        )
        file_count = (
            db.query(func.count(func.distinct(BrainDocument.file_path)))  # pylint: disable=not-callable
            .scalar()
            or 0
        )
        edge_count = (
            db.query(func.count(BrainEdge.id)).scalar() or 0  # pylint: disable=not-callable
        )
        max_indexed_at = db.query(
            func.max(BrainDocument.indexed_at)  # pylint: disable=not-callable
        ).scalar()

    return {
        "chunk_count": chunk_count,
        "file_count": file_count,
        "edge_count": edge_count,
        "max_indexed_at": max_indexed_at.isoformat() if max_indexed_at else None,
    }


def _live_ranking_constants() -> dict:
    """The ranking levers that actually ran, read from the live modules at
    call time (never hardcoded) so the stamp cannot silently drift from
    what produced the report it's attached to."""
    return {
        "kw_weight": retrieval_engine._KW_WEIGHT,  # pylint: disable=protected-access
        "max_per_file": retrieval_engine._MAX_PER_FILE,  # pylint: disable=protected-access
        "section_title_weight": (
            retrieval_engine._SECTION_TITLE_WEIGHT  # pylint: disable=protected-access
        ),
        "doc_decay_factor": retrieval_engine._DOC_DECAY_FACTOR,  # pylint: disable=protected-access
        "abstain_threshold": scorer.ABSTAIN_THRESHOLD,
    }


def run_eval(
    cases: list[RetrievalCase],
    *,
    corpus: str = "brain",
    k: int = 10,
    session=None,
    embedder=None,
) -> RetrievalRunReport:
    """Run every case through `retrieval_engine.retrieve` and score it.

    Args:
        cases: The golden-set cases (`load_cases`).
        corpus: Corpus to query (default `"brain"` — the golden set's cases
            are all brain-corpus queries).
        k: Results to request per query. `10` by default so recall@5 and
            recall@10 both read off the same ranked list (see scorer.py).
        session: Optional SQLAlchemy session (or session-factory) threaded
            through `retrieve()` — forwarded as-is, `None` preserves default
            per-call session behavior.
        embedder: Optional embedder object forwarded to `retrieve()`; `None`
            constructs a fresh `EmbeddingService()` per call (its default).

    Returns:
        A `RetrievalRunReport` with per-case results and aggregate metrics.
    """
    results: list[CaseResult] = []
    for case in cases:
        filters = {"project": case.scope} if case.scope else None
        chunks = retrieval_engine.retrieve(
            case.query,
            corpus=corpus,
            k=k,
            filters=filters,
            session=session,
            embedder=embedder,
            surface="eval",
        )
        # retrieval_confidence mirrors production's k=5 dispatch
        # (RetrieveChunksNode always requests k=5) even though this runner
        # requests k=10 for the recall@10 metric.
        confidence = retrieval_engine.compute_retrieval_confidence(chunks[:5])
        results.append(score_case(case, chunks, confidence))

    return RetrievalRunReport(
        generated_at=RetrievalRunReport.now_iso(),
        case_count=len(cases),
        results=tuple(results),
        aggregate=_aggregate(results),
        corpus=_fingerprint_corpus(session),
        ranking_constants=_live_ranking_constants(),
    )


def write_report(report: RetrievalRunReport, out_dir: str | Path = DEFAULT_RUNS_DIR) -> Path:
    """Write `report` to `<out_dir>/<generated_at>.json`; return the written path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{report.generated_at}.json"
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(report.to_dict(), handle, indent=2, sort_keys=True)
        handle.write("\n")
    return out_path


def load_report(path: str | Path) -> dict:
    """Load a previously-written run report JSON (e.g. a `--baseline` file)."""
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def compare_to_baseline(current: dict, baseline: dict) -> tuple[dict[str, float], bool]:
    """Signed per-metric delta of `current`'s aggregate vs. `baseline`'s.

    Returns `(deltas, regressed)` — `deltas[metric] = current - baseline`
    (positive is improvement, every metric here is higher-is-better) and
    `regressed` is True iff any metric strictly decreased. Shaped like the
    deleted `app/evals/gate.py::gate_change` comparison; not imported from
    it (OR.X2 removed that module).
    """
    current_agg = current["aggregate"]
    baseline_agg = baseline["aggregate"]
    deltas = {
        metric: current_agg.get(metric, 0.0) - baseline_agg.get(metric, 0.0)
        for metric in baseline_agg
    }
    regressed = any(delta < 0 for delta in deltas.values())
    return deltas, regressed
