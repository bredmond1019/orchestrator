"""app/brain/eval/models.py — the eval harness's local, dependency-free models.

Small dataclasses (not pydantic — nothing here needs validation beyond what
`brain.eval.runner.load_cases` already does when parsing the golden-set
YAML) so `app/brain/eval/` stays a pure-stdlib package with no coupling to
`app/schemas/` request models or `app/evals/` (deleted by `OR.X2`).
"""

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class RetrievalCase:
    """One golden-set case (`planning/retrieval-golden-set.yaml`).

    Mirrors the YAML schema `tests/brain/test_golden_set_schema.py` enforces:
    `id`, `query`, `expect_docs` (file_path/doc_id set membership, not
    rank-sensitive), `expect_abstain`, optional `scope` (a D47 workspace/
    project filter), optional `notes` (provenance — not consumed by scoring).
    """

    case_id: str
    query: str
    expect_docs: tuple[str, ...]
    expect_abstain: bool
    scope: str | None = None
    notes: str = ""


@dataclass(frozen=True)
class CaseResult:  # pylint: disable=too-many-instance-attributes
    """`score_case`'s output for one `RetrievalCase` — see `scorer.score_case`."""

    case_id: str
    recall_at_5: float | None
    recall_at_10: float | None
    reciprocal_rank: float | None
    predicted_abstain: bool
    expected_abstain: bool
    abstain_correct: bool
    groundedness: float | None
    retrieval_confidence: float
    matched_docs: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalRunReport:
    """One `syn eval` run — per-case results plus the aggregate metrics.

    `aggregate` keys: `recall_at_5`, `recall_at_10`, `mrr`, `groundedness`
    (each the mean over *positive* cases — those with non-empty
    `expect_docs`; `None` averages nowhere near meaningless negative cases),
    `groundedness_on_hits` (the same mean restricted to cases that actually
    matched an expected document — added by `ticket-groundedness-baseline`
    to separate recall coupling from lexical support; see
    `runner._aggregate`), and `abstain_correctness` (the mean over *every*
    case — the abstain signal is meaningful for negatives and positives
    alike).

    `corpus` and `ranking_constants` (added by
    `ticket-retrieval-ranking-and-abstain` task 1) stamp the provenance of
    the run: the corpus fingerprint (chunk/file/edge counts and
    `max(indexed_at)`) and the live ranking constants that produced these
    numbers, so a later comparison can tell whether two runs are actually
    comparable instead of silently diffing a corpus change against a
    ranking change (the exact confusion that cost `OR.0.C` its result).
    Both are `None` when unavailable — i.e. never populated pre-task-1, so
    `load_report`/`compare_to_baseline` must keep working against the 14
    pre-existing run files that lack them.
    """

    generated_at: str
    case_count: int
    results: tuple[CaseResult, ...]
    aggregate: dict[str, float]
    corpus: dict | None = None
    ranking_constants: dict | None = None

    @staticmethod
    def now_iso() -> str:
        """ISO 8601 UTC timestamp, second precision — also the run's filename stem."""
        return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")

    def to_dict(self) -> dict:
        """Serialize to a plain, JSON-safe dict — the git-tracked run report shape."""
        return {
            "generated_at": self.generated_at,
            "case_count": self.case_count,
            "aggregate": self.aggregate,
            "corpus": self.corpus,
            "ranking_constants": self.ranking_constants,
            "results": [
                {
                    "case_id": r.case_id,
                    "recall_at_5": r.recall_at_5,
                    "recall_at_10": r.recall_at_10,
                    "reciprocal_rank": r.reciprocal_rank,
                    "predicted_abstain": r.predicted_abstain,
                    "expected_abstain": r.expected_abstain,
                    "abstain_correct": r.abstain_correct,
                    "groundedness": r.groundedness,
                    "retrieval_confidence": r.retrieval_confidence,
                    "matched_docs": list(r.matched_docs),
                }
                for r in self.results
            ],
        }
