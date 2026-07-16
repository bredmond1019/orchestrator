"""Tests for RetrieveChunksNode's authored_at ranking decay (block OR.M Task 5).

Covers the decay math applied in ``_fuse_and_rank``:
- An older "brain" doc ranks below an equally-similar newer one.
- ``apply_decay=False`` reproduces pre-decay ranking exactly, regardless of
  ``authored_at``.
- A candidate with ``authored_at=None`` (pre-backfill rows, or corpora/via
  values that never carry the field) is never decayed.

Pure unit tests against ``_fuse_and_rank`` — no DB, no network. Mirrors the
``_make_candidate`` helper pattern from ``tests/workflows/test_retrieve_chunks_node.py``.
"""

import uuid
from datetime import datetime, timedelta

from workflows.document_qa_workflow_nodes.retrieve_chunks_node import (
    RetrieveChunksNode,
)


def _make_candidate(
    dist: float = 0.1,
    is_section_title: bool = False,
    content: str = "some content",
    section_title: str | None = "Intro",
    candidate_id: uuid.UUID | None = None,
    file_path: str | None = None,
    authored_at: datetime | None = None,
) -> dict:
    """Build a candidate dict as returned by ``_semantic_search`` (brain corpus)."""
    return {
        "id": candidate_id or uuid.uuid4(),
        "content": content,
        "section_title": section_title,
        "is_section_title": is_section_title,
        "distance": dist,
        "file_path": file_path,
        "authored_at": authored_at,
    }


class TestDecayOrdering:
    """A decayed (older) fact/doc ranks below a fresh one of equal similarity."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def test_older_doc_ranks_below_equally_similar_newer_doc(self):
        now = datetime.now()
        old_doc = _make_candidate(
            dist=0.2, authored_at=now - timedelta(weeks=26), file_path="docs/old.md"
        )
        new_doc = _make_candidate(
            dist=0.2, authored_at=now - timedelta(weeks=0), file_path="docs/new.md"
        )

        results = self.node._fuse_and_rank(
            [old_doc, new_doc], set(), k=2, threshold=0.0, apply_decay=True
        )

        assert results[0]["file_path"] == "docs/new.md"
        assert results[1]["file_path"] == "docs/old.md"
        assert results[0]["score"] > results[1]["score"]

    def test_decay_reduces_score_relative_to_undecayed(self):
        now = datetime.now()
        old_doc = _make_candidate(
            dist=0.2, authored_at=now - timedelta(weeks=26), file_path="docs/old.md"
        )

        decayed = self.node._fuse_and_rank(
            [old_doc], set(), k=1, threshold=0.0, apply_decay=True
        )
        undecayed = self.node._fuse_and_rank(
            [old_doc], set(), k=1, threshold=0.0, apply_decay=False
        )

        assert decayed[0]["score"] < undecayed[0]["score"]


class TestApplyDecayOptOut:
    """apply_decay=False reproduces pre-decay ranking exactly."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def test_apply_decay_false_matches_no_authored_at_score(self):
        now = datetime.now()
        old_with_date = _make_candidate(
            dist=0.2, authored_at=now - timedelta(weeks=52), file_path="docs/a.md"
        )
        no_date = _make_candidate(dist=0.2, authored_at=None, file_path="docs/b.md")

        opted_out = self.node._fuse_and_rank(
            [old_with_date], set(), k=1, threshold=0.0, apply_decay=False
        )
        undated = self.node._fuse_and_rank(
            [no_date], set(), k=1, threshold=0.0, apply_decay=True
        )

        # Same distance/weights, one opted out of decay and one has no date to
        # decay against — both must reproduce the identical undecayed score.
        assert opted_out[0]["score"] == undated[0]["score"]

    def test_apply_decay_false_ignores_authored_at_ordering(self):
        now = datetime.now()
        old_doc = _make_candidate(
            dist=0.3, authored_at=now - timedelta(weeks=100), file_path="docs/old.md"
        )
        new_doc = _make_candidate(
            dist=0.3, authored_at=now, file_path="docs/new.md"
        )

        results = self.node._fuse_and_rank(
            [old_doc, new_doc], set(), k=2, threshold=0.0, apply_decay=False
        )

        # Identical distance and no keyword boost -> identical score, order
        # preserved from input (stable sort) rather than by authored_at.
        assert results[0]["score"] == results[1]["score"]


class TestAuthoredAtNoneUndecayed:
    """A candidate with authored_at=None is never decayed, even when apply_decay=True."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def test_none_authored_at_score_unaffected_by_apply_decay(self):
        candidate = _make_candidate(dist=0.25, authored_at=None)

        with_decay = self.node._fuse_and_rank(
            [candidate], set(), k=1, threshold=0.0, apply_decay=True
        )
        without_decay = self.node._fuse_and_rank(
            [candidate], set(), k=1, threshold=0.0, apply_decay=False
        )

        assert with_decay[0]["score"] == without_decay[0]["score"] == 0.75

    def test_content_corpus_candidates_missing_authored_at_key_are_undecayed(self):
        """Candidates without an 'authored_at' key at all (e.g. content corpus,
        memory candidates) must not raise and must not be decayed."""
        candidate = {
            "id": uuid.uuid4(),
            "content": "c",
            "section_title": None,
            "is_section_title": False,
            "distance": 0.4,
            "file_path": None,
        }

        results = self.node._fuse_and_rank(
            [candidate], set(), k=1, threshold=0.0, apply_decay=True
        )

        assert results[0]["score"] == 0.6
