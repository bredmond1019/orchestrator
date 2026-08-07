"""app/brain/eval/ — the retrieval evaluation harness (OR.K2 task 3).

Converts a retrieval change from an argument into a signed number: scores
the hand-authored golden set (`planning/retrieval-golden-set.yaml`, OR.K2
task 2) against the promoted retrieval core (`brain.retrieval_engine.retrieve`,
OR.K2 task 1) on recall@5, recall@10, MRR, abstain-correctness, and
groundedness.

This package imports nothing from `app/evals/` — that package was deleted by
`OR.X2` (its runner/gate were DB-bound to `eval_runs`/`eval_results` tables
engine-rs now owns). At most the *shape* of `app/evals/gate.py`'s
`gate_change` comparison is borrowed (a ~15-line signed-delta diff); nothing
is imported. See `tests/brain/test_eval.py::test_eval_package_imports_evals_nowhere`
for the grep-verified guard.

No LLM appears anywhere in this package's scoring path (CLAUDE.md standing
rule 2 is N/A here for that reason) — every metric is a deterministic
function of retrieved chunks and the golden-set expectations.
"""

from brain.eval.models import RetrievalCase, RetrievalRunReport
from brain.eval.runner import (
    compare_to_baseline,
    golden_set_fingerprint,
    load_cases,
    promote_run,
    resolve_baseline,
    run_eval,
    write_report,
)
from brain.eval.scorer import score_case

__all__ = [
    "RetrievalCase",
    "RetrievalRunReport",
    "compare_to_baseline",
    "golden_set_fingerprint",
    "load_cases",
    "promote_run",
    "resolve_baseline",
    "run_eval",
    "write_report",
    "score_case",
]
