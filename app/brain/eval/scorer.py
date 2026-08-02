"""app/brain/eval/scorer.py — deterministic per-case scoring (OR.K2 task 3).

Every metric is a pure function of `(case, results, confidence)` — no DB, no
network, no LLM. `results` is the ranked chunk list `brain.retrieval_engine
.retrieve()` returns (this harness calls it with `k=10` so both recall@5 and
recall@10 read off one ranked list, exactly as a caller comparing the two
cutoffs must — a second, k=5-only call would let Stage-1 candidate-set
non-determinism drift the two numbers apart).

Groundedness *lifts* `VerifyCitationsNode`'s lexical-overlap scoring
(`support_score`/`split_sentences`, block OR.L, `verify_citations_node.py`)
rather than re-deriving it — but as a literal copy, not an import: `app/brain/`
must import `app/workflows/` nowhere (this block's Acceptance Criteria,
grep-verified by `tests/brain/test_eval.py`), so the pure, dependency-free
functions below are mirrored byte-for-byte from that module instead of
reached into, the same discipline `tests/brain/test_golden_set_schema.py`
already applies to `ID_PATTERN`. If `VerifyCitationsNode`'s scoring changes,
update both copies deliberately.

There is no LLM-authored answer text at retrieval-eval time, so the case's
own `query` stands in for "the claim being checked" — groundedness here
reads as "how much of what the query is asking about is actually present in
the chunk this case's retrieval matched against the expected document",
which is exactly `support_score`'s contract (content-word overlap ratio)
applied one layer earlier than `OR.L` applies it (query vs. retrieved
content, instead of generated-answer vs. retrieved content).
"""

import re

# Mirrors DocumentQAEventSchema.confidence_threshold's default (block OR.L) —
# imported, not re-hardcoded, so a future calibration change to the schema
# default is picked up here automatically. `app/schemas/` is not
# `app/workflows/`, so this import doesn't touch the brain/workflows guard.
from schemas.document_qa_schema import DocumentQAEventSchema

from brain.eval.models import CaseResult, RetrievalCase

ABSTAIN_THRESHOLD: float = DocumentQAEventSchema.model_fields[  # pylint: disable=unsubscriptable-object
    "confidence_threshold"
].default

# --- Mirrored verbatim from workflows/document_qa_workflow_nodes/verify_citations_node.py ---
# (deliberately not imported — see module docstring; duplicate-code is
# expected and intentional here, not lint debt)
# pylint: disable=duplicate-code

_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "in", "on", "at", "to", "of", "and", "or", "for", "with", "that",
        "this", "these", "those", "it", "its", "as", "by", "from", "has",
        "have", "had", "not", "but", "if", "then", "so", "do", "does",
        "did", "you", "your", "we", "our", "they", "their", "he", "she",
        "his", "her", "i", "my", "me", "them", "than", "which", "who",
        "what", "when", "where", "how", "can", "will", "would", "could",
        "should", "into", "about", "also",
    }
)

_WORD_RE = re.compile(r"[a-zA-Z']+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _content_words(text: str) -> set[str]:
    """Lowercase content-word set for `text` (stopwords + short tokens dropped)."""
    words = (w.lower() for w in _WORD_RE.findall(text or ""))
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def split_sentences(text: str) -> list[str]:
    """Split `text` into sentences on `.`/`!`/`?` boundaries (mirrored)."""
    if not text or not text.strip():
        return []
    return [s for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s]


def support_score(answer_sentences: list[str], chunk_content: str) -> float:
    """Content-word overlap ratio between `answer_sentences` and `chunk_content`
    (mirrored — see `VerifyCitationsNode.support_score` for the full contract).
    """
    answer_words: set[str] = set()
    for sentence in answer_sentences:
        answer_words |= _content_words(sentence)
    if not answer_words:
        return 0.0
    chunk_words = _content_words(chunk_content)
    overlap = len(answer_words & chunk_words)
    return overlap / len(answer_words)


def _matched_docs(case: RetrievalCase, results: list[dict]) -> list[str]:
    """Return the subset of `results` (in rank order) matching `case.expect_docs`.

    Set membership on `doc_id` OR `file_path` — not rank-sensitive, per the
    golden-set's documented scoring contract (`retrieval-golden-set.yaml`'s
    file header).
    """
    if not case.expect_docs:
        return []
    expected = set(case.expect_docs)
    matched = []
    for chunk in results:
        if chunk.get("doc_id") in expected or chunk.get("file_path") in expected:
            matched.append(chunk.get("doc_id") or chunk.get("file_path"))
    return matched


def _recall_at_k(case: RetrievalCase, results: list[dict], k: int) -> float | None:
    """1.0 if any of `case.expect_docs` appears in the top `k` of `results`.

    `None` for a case with no `expect_docs` (a pure-negative case) — recall
    is undefined, not zero, when there is nothing to recall; averaging it
    into the aggregate would silently penalize the negative-case count
    chosen for abstain coverage instead of measuring retrieval quality.
    """
    if not case.expect_docs:
        return None
    return 1.0 if _matched_docs(case, results[:k]) else 0.0


def _reciprocal_rank(case: RetrievalCase, results: list[dict]) -> float | None:
    """1/rank of the first `expect_docs` hit in `results` (1-indexed); 0.0 if absent.

    `None` for a case with no `expect_docs`, mirroring `_recall_at_k`.
    """
    if not case.expect_docs:
        return None
    expected = set(case.expect_docs)
    for rank, chunk in enumerate(results, start=1):
        if chunk.get("doc_id") in expected or chunk.get("file_path") in expected:
            return 1.0 / rank
    return 0.0


def _groundedness(case: RetrievalCase, results: list[dict]) -> float | None:
    """Lexical support (`VerifyCitationsNode.support_score`) of the query against
    the highest-ranked chunk matching `case.expect_docs`.

    `None` for a case with no `expect_docs` (nothing to check groundedness
    against). 0.0 when `expect_docs` is non-empty but nothing matched
    (recall already failed; groundedness of a non-hit is meaningless-but-
    scored-as-worst rather than silently excluded).

    KNOWN STRUCTURAL BIASES — measured by `ticket-groundedness-baseline`
    against the 2026-08-02 baseline (0.3608) and written up in full at
    `planning/artifacts/groundedness-baseline-analysis.md`. These are
    documented rather than fixed: this is a *shipped* metric with a stored
    baseline, and every one of them makes the number pessimistic-but-honest
    rather than wrong. Read it as a **band, not a target** — an all-green
    corpus reads ~0.55-0.65 overall / ~0.85 on hits, not ~1.0.

    1. *Recall coupling.* A miss scores 0.0, so `groundedness` partly
       re-measures recall. Read `groundedness_on_hits` (added by that
       ticket, `runner._aggregate`) alongside it: 0.3608 -> 0.5576 on the
       baseline, and all six of those misses were corpus-coverage gaps.
    2. *First-matching-chunk sampling.* Support is measured against the
       **highest-ranked** chunk of the expected document, not its best
       one. Scoring the best matching chunk instead would read 0.8530 vs.
       0.6561 on the same baseline — the single largest term. Deliberate:
       the top-ranked chunk is what a caller would actually be shown.
    3. *Identifier-destroying tokenizer.* `_WORD_RE` (`[a-zA-Z']+`) plus
       the `len > 2` filter deletes `D20` -> `d`, `OR.K2` -> `or`/`k`,
       `is_section_title` -> `is`/`section`/`title`. Denominators can
       collapse to one word (`"What is decision D20 about?"` -> `{decision}`),
       so an identifier-anchored case can score a meaningless 1.0. An
       identifier-preserving tokenizer was measured and *lowers* the
       aggregate (0.3608 -> 0.3382) — it is a fidelity defect, not the
       cause of the low number, and fixing it would fork the mirror below
       and force a baseline reset for a strictly-worse-looking number.
       Left open deliberately (ledger `A3`).
    4. *Lexical floor.* A correct semantic match need not repeat the
       query's words. ~0.15 of the deficit from 1.0 is irreducible.
    """
    if not case.expect_docs:
        return None
    expected = set(case.expect_docs)
    for chunk in results:
        if chunk.get("doc_id") in expected or chunk.get("file_path") in expected:
            return support_score(split_sentences(case.query), chunk.get("content", ""))
    return 0.0


def score_case(case: RetrievalCase, results: list[dict], confidence: float) -> CaseResult:
    """Score one `RetrievalCase` against its retrieved `results` and `confidence`.

    Args:
        case: The golden-set case.
        results: The ranked chunk list `retrieval_engine.retrieve()` returned
            for `case.query` (recommend `k>=10` so recall@5/recall@10 both
            read off one list — see module docstring).
        confidence: The `retrieval_confidence` signal
            (`retrieval_engine.compute_retrieval_confidence`) for this query.

    Returns:
        A `CaseResult` — recall@5, recall@10, reciprocal rank, abstain
        prediction/correctness, and groundedness for this one case.
    """
    predicted_abstain = confidence < ABSTAIN_THRESHOLD
    matched = _matched_docs(case, results)
    return CaseResult(
        case_id=case.case_id,
        recall_at_5=_recall_at_k(case, results, 5),
        recall_at_10=_recall_at_k(case, results, 10),
        reciprocal_rank=_reciprocal_rank(case, results),
        predicted_abstain=predicted_abstain,
        expected_abstain=case.expect_abstain,
        abstain_correct=predicted_abstain == case.expect_abstain,
        groundedness=_groundedness(case, results),
        retrieval_confidence=confidence,
        matched_docs=tuple(matched),
    )
