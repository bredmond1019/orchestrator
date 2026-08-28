"""Tests for the ``code`` corpus registration and its threading through `recall()`.

Covers OR.P task 4: the ``"code"`` entry in ``retrieval_engine._CORPUS_CONFIG``,
the keyword-only ``corpus`` parameter on ``brain.retrieval.recall``/
``hybrid_search``, and the ``--corpus`` CLI flag. The end-to-end fixture-repo
retrieval test (indexing a real fixture tree into a test database and
resolving a citation) is task 6's ``tests/brain/test_code_corpus_retrieval.py``
addition, not this one — this file is pure/mock-only, no DB, no embedding
backend.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from brain import retrieval_engine
from brain.code_chunking import chunk_source
from brain.retrieval import hybrid_search, recall
from database.brain_document import EMBEDDING_DIM
from database.code_chunk import CodeChunk

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "code"


def _vec(index: int, dim: int = EMBEDDING_DIM) -> list[float]:
    """A deterministic unit basis vector: 1.0 at `index`, 0.0 everywhere else.

    Two basis vectors for different indices are maximally cosine-distant
    (orthogonal), and a vector compared against itself is maximally close
    (distance 0) — exactly what a deterministic ranking test needs, with no
    live embedding backend involved.
    """
    vector = [0.0] * dim
    vector[index] = 1.0
    return vector

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


# ---------------------------------------------------------------------------
# End-to-end fixture-repo retrieval (OR.P task 6)
# ---------------------------------------------------------------------------


def _index_fixture_file(session, *, repo: str, filename: str, embeddings: dict):
    """Chunk one `tests/brain/fixtures/code/` file with the REAL chunker
    (`brain.code_chunking.chunk_source`) and insert one `CodeChunk` row per
    spec named in `embeddings`.

    `embeddings` maps a spec's `symbol_name` (or `None` for the whole-file
    fallback chunk) to the vector to store as that row's `embedding` — the
    test controls ranking deterministically this way, with no live
    embedding backend involved. A spec whose `symbol_name` is not a key in
    `embeddings` is skipped (not every chunk in a fixture file needs a row
    for every test).

    Returns the list of `(CodeChunkSpec, CodeChunk row)` pairs actually
    inserted, so a test can assert against the real, chunker-derived
    symbol/line-range values rather than a hand-copied literal.
    """
    text = (_FIXTURES_DIR / filename).read_text(encoding="utf-8")
    specs = chunk_source(text, file_path=filename)
    inserted = []
    for spec in specs:
        if spec.symbol_name not in embeddings:
            continue
        row = CodeChunk(
            repo=repo,
            file_path=filename,
            language=spec.language,
            symbol_name=spec.symbol_name,
            symbol_kind=spec.symbol_kind,
            start_line=spec.start_line,
            end_line=spec.end_line,
            content=spec.content,
            embedding=embeddings[spec.symbol_name],
            embedding_model="test-stub:v1",
            section=spec.section,
            indexed_at=datetime.now(),
        )
        session.add(row)
        inserted.append((spec, row))
    session.flush()
    return inserted


class TestEndToEndFixtureRepoRetrieval:
    """OR.P task 6: end-to-end retrieval over a fixture repo tree, backed by
    a REAL Postgres+pgvector database (the Docker-gated `pgvector_session`
    fixture) and a deterministic stub embedding backend.

    This stands in for the block's `gateable: false` acceptance criterion —
    "the code corpus is populated against the real fleet and answers a real
    'how does X work' question with a correct citation" — which needs a
    live Postgres with pgvector AND a live embedding backend, neither of
    which this repo's checks run (the same reason `eval-scan` is registered
    non-gating in `planning/harness.json`). This fixture proves the
    retrieval mechanics (chunking -> row -> corpus-scoped hybrid retrieval
    -> citation) are wired correctly end to end; it does NOT prove the live
    criterion. Indexing the real fleet and confirming a real answer remains
    an operator verification.
    """

    def test_top_hit_resolves_to_correct_symbol_and_line_range(self, pgvector_session):
        target_vector = _vec(0)
        other_vector = _vec(1)

        inserted = _index_fixture_file(
            pgvector_session,
            repo="fixture-repo-a",
            filename="sample.py",
            embeddings={"helper": target_vector, "Widget.render": other_vector},
        )
        helper_spec = next(spec for spec, _ in inserted if spec.symbol_name == "helper")

        with patch(
            "services.embedding_service.EmbeddingService.embed_text",
            return_value=target_vector,
        ):
            results = hybrid_search(
                "how does helper work",
                limit=5,
                corpus="code",
                filters={"repo": "fixture-repo-a"},
                session=pgvector_session,
            )

        assert results
        top = results[0]
        assert top["file_path"] == "sample.py"
        assert top["section"] == helper_spec.section
        assert f"L{helper_spec.start_line}-{helper_spec.end_line}" in top["section"]

    def test_cross_repo_scoping_is_asserted_on_returned_rows(self, pgvector_session):
        """Two repos each carry an equally close 'helper' chunk (same
        embedding vector, so ranking alone could not tell them apart);
        scoping is proven by inspecting the actual `file_path` on every
        returned row, not merely by a count.
        """
        shared_vector = _vec(2)

        _index_fixture_file(
            pgvector_session,
            repo="fixture-repo-a",
            filename="sample.py",
            embeddings={"helper": shared_vector},
        )
        _index_fixture_file(
            pgvector_session,
            repo="fixture-repo-b",
            filename="sample.rs",
            embeddings={"helper": shared_vector},
        )

        with patch(
            "services.embedding_service.EmbeddingService.embed_text",
            return_value=shared_vector,
        ):
            results = hybrid_search(
                "how does helper work",
                limit=10,
                corpus="code",
                filters={"repo": "fixture-repo-a"},
                session=pgvector_session,
            )

        assert results
        assert all(r["file_path"] == "sample.py" for r in results)
        assert not any(r["file_path"] == "sample.rs" for r in results)

    def test_whole_file_fallback_chunk_is_retrievable_end_to_end(self, pgvector_session):
        """A fallback chunk that indexes but never ranks is the same as a
        dropped file from the user's side — this proves it actually surfaces
        from a real scored retrieval, not merely that the chunker produces it
        (that half is task 3's `test_code_chunking.py`).
        """
        fallback_vector = _vec(3)

        inserted = _index_fixture_file(
            pgvector_session,
            repo="fixture-repo-fallback",
            filename="sample.txt",
            embeddings={None: fallback_vector},
        )
        fallback_spec, _ = inserted[0]
        assert fallback_spec.symbol_kind == "file"

        with patch(
            "services.embedding_service.EmbeddingService.embed_text",
            return_value=fallback_vector,
        ):
            results = hybrid_search(
                "what is in this plain text fixture",
                limit=5,
                corpus="code",
                filters={"repo": "fixture-repo-fallback"},
                session=pgvector_session,
            )

        assert results
        top = results[0]
        assert top["file_path"] == "sample.txt"
        assert top["section"] == fallback_spec.section
        assert "file" in top["section"]
