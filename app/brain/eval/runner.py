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

from brain import retrieval_engine
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
        cases.append(
            RetrievalCase(
                case_id=raw["id"],
                query=raw["query"],
                expect_docs=tuple(raw.get("expect_docs") or ()),
                expect_abstain=bool(raw.get("expect_abstain", False)),
                scope=raw.get("scope"),
                notes=raw.get("notes", ""),
            )
        )
    return cases


def _aggregate(results: list[CaseResult]) -> dict[str, float]:
    """Mean per metric — positive-case metrics over non-`None` readings only,
    `abstain_correctness` over every case (see `models.RetrievalRunReport`)."""
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

    return aggregate


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
