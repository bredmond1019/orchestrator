"""Tests for the ``code`` corpus registration and its threading through `recall()`.

Covers OR.P task 4: the ``"code"`` entry in ``retrieval_engine._CORPUS_CONFIG``,
the keyword-only ``corpus`` parameter on ``brain.retrieval.recall``/
``hybrid_search``, and the ``--corpus`` CLI flag. The end-to-end fixture-repo
retrieval test (indexing a real fixture tree into a test database and
resolving a citation) is task 6's ``tests/brain/test_code_corpus_retrieval.py``
addition, not this one — this file is pure/mock-only, no DB, no embedding
backend.
"""

from unittest.mock import patch

from brain import retrieval_engine
from brain.retrieval import hybrid_search, recall
from database.code_chunk import CodeChunk

# ---------------------------------------------------------------------------
# _CORPUS_CONFIG["code"] registration
# ---------------------------------------------------------------------------


class TestCodeCorpusRegistration:
    def test_code_corpus_is_registered(self):
        assert "code" in retrieval_engine._CORPUS_CONFIG  # pylint: disable=protected-access

    def test_code_corpus_uses_code_chunk_model(self):
        config = retrieval_engine._CORPUS_CONFIG["code"]  # pylint: disable=protected-access
        assert config["model"] is CodeChunk

    def test_code_corpus_field_mapping(self):
        config = retrieval_engine._CORPUS_CONFIG["code"]  # pylint: disable=protected-access
        assert config["content_field"] == "content"
        assert config["section_title_field"] == "section"
        assert config["tsv_field"] == "content_tsv"

    def test_code_corpus_filter_fields_scope_by_repo_and_language(self):
        config = retrieval_engine._CORPUS_CONFIG["code"]  # pylint: disable=protected-access
        assert config["filter_fields"] == {"repo": "scalar", "language": "scalar"}

    def test_code_corpus_does_not_declare_supports_structural(self):
        """No related: edges exist over source; declaring this would send
        _structural_expand hunting brain_edges rows that can never exist."""
        config = retrieval_engine._CORPUS_CONFIG["code"]  # pylint: disable=protected-access
        assert "supports_structural" not in config

    def test_code_corpus_does_not_declare_default_status_exclude(self):
        """Code chunks have no status column."""
        config = retrieval_engine._CORPUS_CONFIG["code"]  # pylint: disable=protected-access
        assert "default_status_exclude" not in config

    def test_existing_corpora_are_unaffected(self):
        assert "content" in retrieval_engine._CORPUS_CONFIG  # pylint: disable=protected-access
        assert "brain" in retrieval_engine._CORPUS_CONFIG  # pylint: disable=protected-access


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_code_engine_chunk(**overrides) -> dict:
    """Build a retrieval_engine.retrieve()-shaped chunk for the "code" corpus.

    Mirrors what _row_to_candidate/_fuse_and_rank actually produce for a
    CodeChunk row: doc_id and title are None (CodeChunk has neither column),
    file_path is the source path, and section_title carries the pre-rendered
    citation from app.brain.code_chunking.
    """
    base = {
        "id": "chunk-uuid-1",
        "doc_id": None,
        "file_path": "app/brain/retrieval.py",
        "title": None,
        "section_title": "recall (function, L252-345)",
        "content": "def recall(...): ...",
        "source": "General",
        "score": 0.8,
        "via": "semantic",
    }
    base.update(overrides)
    return base


def _fake_brain_engine_chunk(**overrides) -> dict:
    base = {
        "id": "chunk-uuid-2",
        "doc_id": "D99",
        "file_path": "docs/decisions/D99-example.md",
        "title": "D99 — Parity Check",
        "section_title": "",
        "content": "Parity check content.",
        "source": "General",
        "score": 0.9,
        "via": "semantic",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# hybrid_search / recall — corpus threading
# ---------------------------------------------------------------------------


class TestCorpusThreading:
    def test_hybrid_search_default_corpus_is_brain(self):
        with patch("brain.retrieval_engine.retrieve", return_value=[]) as mock_retrieve:
            hybrid_search("q", limit=3)

        assert mock_retrieve.call_args.kwargs["corpus"] == "brain"

    def test_hybrid_search_forwards_code_corpus(self):
        with patch("brain.retrieval_engine.retrieve", return_value=[]) as mock_retrieve:
            hybrid_search("q", limit=3, corpus="code")

        assert mock_retrieve.call_args.kwargs["corpus"] == "code"

    def test_recall_hybrid_forwards_corpus_to_hybrid_search(self):
        with patch("brain.retrieval_engine.retrieve", return_value=[]) as mock_retrieve:
            recall("q", hybrid=True, corpus="code")

        assert mock_retrieve.call_args.kwargs["corpus"] == "code"

    def test_recall_default_corpus_is_brain(self):
        with patch("brain.retrieval_engine.retrieve", return_value=[]) as mock_retrieve:
            recall("q", hybrid=True)

        assert mock_retrieve.call_args.kwargs["corpus"] == "brain"


# ---------------------------------------------------------------------------
# Code-chunk normalization — title/doc_id derived, no new key
# ---------------------------------------------------------------------------


class TestCodeChunkNormalization:
    def test_code_chunk_gets_synthetic_doc_id(self):
        chunk = _fake_code_engine_chunk()
        with patch("brain.retrieval_engine.retrieve", return_value=[chunk]):
            results = hybrid_search("q", corpus="code")

        assert results[0]["doc_id"] == "code:chunk-uuid-1"

    def test_code_chunk_title_derived_from_section(self):
        chunk = _fake_code_engine_chunk(section_title="recall (function, L252-345)")
        with patch("brain.retrieval_engine.retrieve", return_value=[chunk]):
            results = hybrid_search("q", corpus="code")

        assert results[0]["title"] == "recall"

    def test_fallback_chunk_title_is_file_basename(self):
        chunk = _fake_code_engine_chunk(section_title="sample.txt (file, L1-42)")
        with patch("brain.retrieval_engine.retrieve", return_value=[chunk]):
            results = hybrid_search("q", corpus="code")

        assert results[0]["title"] == "sample.txt"

    def test_code_chunk_section_carries_full_citation(self):
        chunk = _fake_code_engine_chunk(section_title="recall (function, L252-345)")
        with patch("brain.retrieval_engine.retrieve", return_value=[chunk]):
            results = hybrid_search("q", corpus="code")

        assert results[0]["section"] == "recall (function, L252-345)"

    def test_brain_chunk_normalization_unaffected(self):
        """A brain-corpus chunk's doc_id/title come from the row, not the
        code-corpus derivation path — this pins that the new branch in
        _normalize_engine_chunk is gated on corpus=="code" and doc_id is None."""
        chunk = _fake_brain_engine_chunk()
        with patch("brain.retrieval_engine.retrieve", return_value=[chunk]):
            results = hybrid_search("q", corpus="brain")

        assert results[0]["doc_id"] == "D99"
        assert results[0]["title"] == "D99 — Parity Check"


# ---------------------------------------------------------------------------
# Shape parity — the load-bearing OR.3.B contract-pin guard
# ---------------------------------------------------------------------------


class TestShapeParity:
    def test_code_and_brain_results_have_identical_key_sets(self):
        """recall(corpus="code") must return the SAME normalized result dict
        shape as recall(corpus="brain") — no added keys — so the OR.3.B
        RecallResponse/RecallResult contract pin still passes unchanged.
        A subset assertion could not catch an added key; only an exact
        sorted-tuple equality can.
        """
        code_chunk = _fake_code_engine_chunk()
        brain_chunk = _fake_brain_engine_chunk()

        with patch("brain.retrieval_engine.retrieve", return_value=[code_chunk]):
            code_results = recall("q", hybrid=True, corpus="code")
        with patch("brain.retrieval_engine.retrieve", return_value=[brain_chunk]):
            brain_results = recall("q", hybrid=True, corpus="brain")

        assert len(code_results) == 1
        assert len(brain_results) == 1
        assert tuple(sorted(code_results[0].keys())) == tuple(sorted(brain_results[0].keys()))

    def test_no_start_line_key_leaks_into_the_normalized_dict(self):
        """The out-of-scope guard: citations ride file_path + section only."""
        chunk = _fake_code_engine_chunk()
        with patch("brain.retrieval_engine.retrieve", return_value=[chunk]):
            results = hybrid_search("q", corpus="code")

        assert "start_line" not in results[0]
        assert "end_line" not in results[0]


# ---------------------------------------------------------------------------
# CLI --corpus flag
# ---------------------------------------------------------------------------


class TestCliCorpusFlag:
    def test_recall_subparser_accepts_corpus_flag(self):
        from brain.cli import _build_parser  # pylint: disable=import-outside-toplevel

        parser = _build_parser()
        args = parser.parse_args(["recall", "how does X work", "--corpus", "code"])
        assert args.corpus == "code"

    def test_recall_subparser_defaults_corpus_to_brain(self):
        from brain.cli import _build_parser  # pylint: disable=import-outside-toplevel

        parser = _build_parser()
        args = parser.parse_args(["recall", "q"])
        assert args.corpus == "brain"

    def test_recall_subparser_rejects_unknown_corpus(self):
        from brain.cli import _build_parser  # pylint: disable=import-outside-toplevel

        parser = _build_parser()
        try:
            parser.parse_args(["recall", "q", "--corpus", "nonsense"])
            raise AssertionError("expected SystemExit for an invalid --corpus choice")
        except SystemExit:
            pass

    def test_run_recall_threads_corpus_to_recall(self):
        from brain.cli import _run_recall  # pylint: disable=import-outside-toplevel

        args = type(
            "Args",
            (),
            {
                "query": "how does X work",
                "limit": 5,
                "hybrid": True,
                "workspace": None,
                "corpus": "code",
                "json": True,
            },
        )()

        with patch("brain.retrieval.recall", return_value=[]) as mock_recall:
            _run_recall(args)

        assert mock_recall.call_args.kwargs["corpus"] == "code"
