"""VerifyCitationsNode — deterministic citation verification (block OR.L).

Runs between ``AnswerNode`` and ``UpdateSessionMemoryNode`` on the answered
branch only (the abstain branch never reaches this node — it bypasses
straight from ``AbstainNode`` to ``UpdateSessionMemoryNode``). Checks each
section title ``AnswerNode`` claims to have cited against the chunks
``RetrieveChunksNode`` actually retrieved:

1. **Existence** — the cited title must match a retrieved chunk's
   ``section_title`` (normalized: case/``#``-prefix/whitespace-insensitive).
2. **Claim support** — a pure lexical content-word overlap ratio between the
   answer text and the matched chunk's ``content`` (``support_score``),
   against a documented module-level threshold.

A citation failing either check lands in ``unverified_citations``; a
citation passing both lands in ``verified_citations``. When *every* citation
fails (including the zero-citations-over-non-empty-context case), the
envelope is **withheld**: it flips to the same abstain shape ``AbstainNode``
produces (design decision 5's unified envelope), with
``withheld_reason="citations_unverified"``, rather than shipping an
ungrounded answer.

``corroborated`` is true iff verified citations span >= 2 distinct
``file_path``s (two-source preference, design decision 4). When the event is
``high_stakes`` and the answer is *not* withheld but also not corroborated,
``escalate_to_human`` is set (the answer still ships, flagged) — a
"prefer", not a "require".

No LLM judging happens here — this node is a pure, deterministic function of
its inputs (out of scope per the block: LLM-judged semantic contradiction is
bastion's fuzzy follow-on).
"""

import re

from core.nodes.base import Node
from core.task import TaskContext

# Content-word overlap ratio a cited chunk must clear to count as "support"
# for the answer's claim. Chosen conservatively: a genuinely grounded
# sentence typically shares a third or more of its non-stopword vocabulary
# with the section it was drawn from, while an unrelated chunk shares
# near-zero. Documented here per design decision 3.
SUPPORT_THRESHOLD: float = 0.3

WITHHELD_MESSAGE = "I don't have verified support for that in my documents."

# Small stopword list for the content-word overlap calculation — excludes
# function words so the ratio reflects topical overlap, not grammar.
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
    """Lowercase content-word set for ``text`` (stopwords + short tokens dropped)."""
    words = (w.lower() for w in _WORD_RE.findall(text or ""))
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _normalize_title(title: str | None) -> str:
    """Normalize a section title for existence comparison.

    Case-insensitive, strips leading ``#`` markdown-heading markers and
    surrounding whitespace, and collapses internal whitespace runs.
    """
    if not title:
        return ""
    stripped = title.strip().lstrip("#").strip()
    return re.sub(r"\s+", " ", stripped).lower()


def split_sentences(text: str) -> list[str]:
    """Split ``text`` into sentences on ``.``/``!``/``?`` boundaries.

    Pure, whitespace-tolerant splitter — good enough for the content-word
    overlap calculation (no NLP dependency needed for this deterministic
    check).
    """
    if not text or not text.strip():
        return []
    return [s for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s]


def support_score(answer_sentences: list[str], chunk_content: str) -> float:
    """Content-word overlap ratio between ``answer_sentences`` and ``chunk_content``.

    Pure function: ``|answer_words ∩ chunk_words| / |answer_words|``, over
    content words only (stopwords and short tokens excluded). Returns 0.0
    when the answer contributes no content words at all (nothing to check
    support for). Monotonic in shared vocabulary — an answer entirely
    supported by the chunk approaches 1.0; a wholly unrelated chunk yields
    (near) 0.0.
    """
    answer_words: set[str] = set()
    for sentence in answer_sentences:
        answer_words |= _content_words(sentence)
    if not answer_words:
        return 0.0
    chunk_words = _content_words(chunk_content)
    overlap = len(answer_words & chunk_words)
    return overlap / len(answer_words)


class VerifyCitationsNode(Node):
    """Deterministic node that verifies AnswerNode's citations against the retrieved chunks."""

    @staticmethod
    def _get_answer_fields(answer_output) -> tuple[str, list[str]]:
        """Extract ``(answer_text, cited_sections)`` from either shape AnswerNode stores.

        ``AnswerNode`` stores ``result.output`` directly, which may be the
        ``OutputType`` pydantic model instance (real run) or a plain dict
        (tests seeding per standing rule 9).
        """
        if hasattr(answer_output, "answer"):
            return answer_output.answer, list(answer_output.cited_sections or [])
        return (
            answer_output.get("answer", ""),
            list(answer_output.get("cited_sections", [])),
        )

    @staticmethod
    def _classify_citations(
        cited_sections: list[str], answer_text: str, chunks: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        """Split ``cited_sections`` into ``(verified, unverified)`` citation dicts.

        A citation is verified when its title matches a retrieved chunk
        (normalized comparison) AND the answer text clears
        ``SUPPORT_THRESHOLD`` lexical overlap against that chunk's content.
        """
        chunks_by_title = {
            _normalize_title(chunk.get("section_title")): chunk for chunk in chunks
        }
        answer_sentences = split_sentences(answer_text)

        verified: list[dict] = []
        unverified: list[dict] = []
        for cited in cited_sections:
            match = chunks_by_title.get(_normalize_title(cited))
            if match is None:
                unverified.append({"section_title": cited, "reason": "not_found"})
                continue
            score = support_score(answer_sentences, match.get("content", ""))
            if score >= SUPPORT_THRESHOLD:
                verified.append(
                    {
                        "section_title": cited,
                        "file_path": match.get("file_path"),
                        "support_score": score,
                    }
                )
            else:
                unverified.append(
                    {"section_title": cited, "reason": "unsupported", "support_score": score}
                )
        return verified, unverified

    @staticmethod
    def _build_envelope(  # pylint: disable=too-many-arguments
        *,
        answer_text: str,
        cited_sections: list[str],
        verified_citations: list[dict],
        unverified_citations: list[dict],
        context_confidence: float,
        has_chunks: bool,
        high_stakes: bool,
    ) -> dict:
        """Build the unified answer envelope (design decision 5), withheld or answered."""
        if not verified_citations and has_chunks:
            return {
                "answer": WITHHELD_MESSAGE,
                "cited_sections": [],
                "verified_citations": [],
                "unverified_citations": unverified_citations,
                "context_confidence": context_confidence,
                "abstained": True,
                "corroborated": False,
                "escalate_to_human": True,
                "withheld_reason": "citations_unverified",
            }

        distinct_files = {
            v["file_path"] for v in verified_citations if v.get("file_path")
        }
        corroborated = len(distinct_files) >= 2
        return {
            "answer": answer_text,
            "cited_sections": cited_sections,
            "verified_citations": verified_citations,
            "unverified_citations": unverified_citations,
            "context_confidence": context_confidence,
            "abstained": False,
            "corroborated": corroborated,
            "escalate_to_human": bool(high_stakes and not corroborated),
            "withheld_reason": None,
        }

    def process(self, task_context: TaskContext) -> TaskContext:
        """Verify citations and write the final (answered-or-withheld) envelope.

        Reads:
          - ``AnswerNode`` output: ``answer``, ``cited_sections``.
          - ``RetrieveChunksNode`` output: ``chunks``, ``retrieval_confidence``.
          - ``task_context.event.high_stakes``.

        Writes:
          - ``VerifyCitationsNode`` result: the unified answer envelope
            (design decision 5).
        """
        answer_output = task_context.get_node_output("AnswerNode")["result"]
        answer_text, cited_sections = self._get_answer_fields(answer_output)

        retrieve_result = task_context.get_node_output("RetrieveChunksNode")["result"]
        chunks: list[dict] = retrieve_result.get("chunks", [])

        verified_citations, unverified_citations = self._classify_citations(
            cited_sections, answer_text, chunks
        )
        result = self._build_envelope(
            answer_text=answer_text,
            cited_sections=cited_sections,
            verified_citations=verified_citations,
            unverified_citations=unverified_citations,
            context_confidence=retrieve_result.get("retrieval_confidence", 0.0),
            has_chunks=bool(chunks),
            high_stakes=getattr(task_context.event, "high_stakes", False),
        )

        task_context.update_node(node_name=self.node_name, result=result)
        return task_context
