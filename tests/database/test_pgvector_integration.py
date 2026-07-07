"""Live pgvector integration suite.

Runs against the real ``pgvector/pgvector:pg16`` container provided by
``tests/database/conftest.py`` (Docker-gated, session-scoped). Proves what the
in-memory SQLite suite cannot: real cosine-distance nearest-neighbor ordering
via the ``embedding <=> query`` operator, a round trip through the PG-only
``brain_documents`` ARRAY columns, and the DB-level ``vector`` column
dimension via ``pg_attribute`` introspection (not the ORM attribute).

Select with ``pytest -m integration``; excluded from the default run via
``pytest -m "not integration"``.
"""

import math
import uuid

import pytest
from database.brain_document import EMBEDDING_DIM as BRAIN_EMBEDDING_DIM
from database.brain_document import BrainDocument
from database.content_chunk import EMBEDDING_DIM, ContentChunk
from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text
from sqlalchemy.exc import DBAPIError, DataError

pytestmark = pytest.mark.integration


def _angled_vector(theta: float, dim: int = EMBEDDING_DIM) -> list[float]:
    """Build a 2D-plane unit vector (axes 0/1, rest zero) at angle ``theta``.

    Cosine distance to the axis-0 unit vector grows monotonically with
    ``theta`` (``1 - cos(theta)``), so a set of vectors at increasing angles
    has a known, unambiguous nearest-neighbor ordering.
    """
    vec = [0.0] * dim
    vec[0] = math.cos(theta)
    vec[1] = math.sin(theta)
    return vec


class TestNearestNeighborOrdering:
    """``ORDER BY embedding <=> :query`` returns rows in true cosine-distance order."""

    def test_orders_by_cosine_distance(self, pgvector_session):
        doc_id = uuid.uuid4()
        query_vec = _angled_vector(0.0)

        close = ContentChunk(
            doc_id=doc_id, position=0, content="close", embedding=_angled_vector(0.1)
        )
        mid = ContentChunk(
            doc_id=doc_id, position=1, content="mid", embedding=_angled_vector(0.6)
        )
        far = ContentChunk(
            doc_id=doc_id, position=2, content="far", embedding=_angled_vector(1.3)
        )

        # Inserted out of expected order to prove the ORDER BY drives the
        # result, not insertion order.
        pgvector_session.add_all([far, mid, close])
        pgvector_session.flush()

        stmt = text(
            "SELECT content FROM content_chunks WHERE doc_id = :doc_id "
            "ORDER BY embedding <=> :query LIMIT 3"
        ).bindparams(
            bindparam("doc_id"),
            bindparam("query", type_=Vector(EMBEDDING_DIM)),
        )
        rows = pgvector_session.execute(
            stmt, {"doc_id": doc_id, "query": query_vec}
        ).fetchall()

        assert [row.content for row in rows] == ["close", "mid", "far"]

    def test_empty_result_query_returns_empty_list(self, pgvector_session):
        missing_doc_id = uuid.uuid4()
        query_vec = _angled_vector(0.0)

        stmt = text(
            "SELECT content FROM content_chunks WHERE doc_id = :doc_id "
            "ORDER BY embedding <=> :query LIMIT 5"
        ).bindparams(
            bindparam("doc_id"),
            bindparam("query", type_=Vector(EMBEDDING_DIM)),
        )
        rows = pgvector_session.execute(
            stmt, {"doc_id": missing_doc_id, "query": query_vec}
        ).fetchall()

        assert rows == []


class TestDimensionMismatchRejected:
    """pgvector rejects an insert whose embedding dimension doesn't match the column."""

    def test_dimension_mismatch_insert_rejected(self, pgvector_session):
        stmt = text(
            "INSERT INTO content_chunks (id, doc_id, position, content, embedding) "
            "VALUES (:id, :doc_id, 0, 'bad', :embedding)"
        ).bindparams(
            bindparam("id"),
            bindparam("doc_id"),
            bindparam("embedding", type_=Vector(EMBEDDING_DIM - 1)),
        )

        with pytest.raises((DataError, DBAPIError)):
            pgvector_session.execute(
                stmt,
                {
                    "id": uuid.uuid4(),
                    "doc_id": uuid.uuid4(),
                    "embedding": [0.1] * (EMBEDDING_DIM - 1),
                },
            )
            pgvector_session.flush()


class TestBrainDocumentRoundTrip:
    """``brain_documents`` ARRAY/PG-typed columns round-trip through the real schema."""

    def test_round_trip_preserves_pg_only_fields(self, pgvector_session):
        doc = BrainDocument(
            file_path="docs/decisions/d99-example.md",
            doc_type="decision",
            section="## Context",
            content="Some decision content.",
            embedding=[0.02] * BRAIN_EMBEDDING_DIM,
            workflow_patterns=["WhatsApp order tracking", "Email triage"],
            layer=["engine", "brain"],
            keywords=["pgvector", "integration"],
            related=["d20-shared-data-contract"],
        )
        pgvector_session.add(doc)
        pgvector_session.flush()
        pgvector_session.expire(doc)

        fetched = pgvector_session.get(BrainDocument, doc.id)

        assert fetched is not None
        assert fetched.file_path == "docs/decisions/d99-example.md"
        assert fetched.doc_type == "decision"
        assert fetched.workflow_patterns == ["WhatsApp order tracking", "Email triage"]
        assert fetched.layer == ["engine", "brain"]
        assert fetched.keywords == ["pgvector", "integration"]
        assert fetched.related == ["d20-shared-data-contract"]
        assert len(fetched.embedding) == BRAIN_EMBEDDING_DIM


class TestVectorColumnIntrospection:
    """The DB-level column type is a real ``vector(N)``, verified via ``pg_attribute``."""

    def test_content_chunks_embedding_is_vector_1024(self, pgvector_session):
        row = pgvector_session.execute(
            text(
                "SELECT format_type(atttypid, atttypmod) AS col_type "
                "FROM pg_attribute "
                "WHERE attrelid = 'content_chunks'::regclass AND attname = 'embedding'"
            )
        ).one()
        assert row.col_type == f"vector({EMBEDDING_DIM})"

    def test_brain_documents_embedding_is_vector_1024(self, pgvector_session):
        row = pgvector_session.execute(
            text(
                "SELECT format_type(atttypid, atttypmod) AS col_type "
                "FROM pg_attribute "
                "WHERE attrelid = 'brain_documents'::regclass AND attname = 'embedding'"
            )
        ).one()
        assert row.col_type == f"vector({BRAIN_EMBEDDING_DIM})"
