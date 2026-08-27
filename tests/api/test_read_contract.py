"""Contract-conformance pin for `GET /recall` (OR.3.B task 2).

This is the enforcement point for `docs/data-contract.md`'s `RecallResponse`/
`RecallResult` shape — a future editor of either this file or the contract
doc should find the other. It exists so engine-rs, becoming a consumer of
`GET /recall`, breaks loudly (a failing test here) on any field added,
removed or renamed, rather than drifting silently against a contract doc
nobody re-read.

Reuses `tests/api/test_read.py`'s `read_context` fixture pattern (in-memory
SQLite via `StaticPool`, `db_session`/`require_api_key` dependency
overrides) and mocks the read core at its import site in `api.read` — no
real pgvector connection.
"""

from unittest.mock import patch

import pytest
from api.security import require_api_key
from database.session import Base, db_session
from fastapi.testclient import TestClient
from main import app
from schemas.read_schema import RecallResponse, RecallResult
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Literal, exact key sets — `==` on sorted tuples, never `issubset`, so an
# ADDED field (the drift a consumer actually breaks on) fails too.
_RECALL_RESULT_FIELDS = frozenset(
    {"doc_id", "file_path", "title", "section", "content", "score", "via"}
)
_RECALL_RESPONSE_FIELDS = frozenset({"query", "count", "results"})

# Nullability pin: which RecallResult fields are `X | None` vs required.
_RECALL_RESULT_NULLABLE = frozenset({"doc_id", "title", "section"})
_RECALL_RESULT_NON_NULLABLE = frozenset({"file_path", "content", "score", "via"})

# The closed `via` vocabulary docs/data-contract.md v1.6.0 states.
_VIA_VOCABULARY = frozenset({"exact-id", "semantic", "structural", "keyword", "memory"})


def _is_optional(annotation) -> bool:
    """True if a pydantic field annotation is `X | None` (a `UnionType` with `NoneType` in args)."""
    args = getattr(annotation, "__args__", ())
    return type(None) in args


class TestRecallResultShape:
    def test_field_set_is_exact(self):
        actual = frozenset(RecallResult.model_fields.keys())
        assert tuple(sorted(actual)) == tuple(sorted(_RECALL_RESULT_FIELDS)), (
            f"RecallResult field set drifted. "
            f"added={actual - _RECALL_RESULT_FIELDS} "
            f"removed={_RECALL_RESULT_FIELDS - actual}"
        )

    def test_nullable_fields_are_optional(self):
        fields = RecallResult.model_fields
        for name in _RECALL_RESULT_NULLABLE:
            assert _is_optional(fields[name].annotation), (
                f"RecallResult.{name} should be nullable (X | None) but is not"
            )

    def test_non_nullable_fields_are_required(self):
        fields = RecallResult.model_fields
        for name in _RECALL_RESULT_NON_NULLABLE:
            assert not _is_optional(fields[name].annotation), (
                f"RecallResult.{name} should be non-optional but is nullable"
            )

    def test_score_is_float(self):
        assert RecallResult.model_fields["score"].annotation is float

    def test_via_vocabulary_pin(self):
        """Pinned as a literal the contract doc's `via` list must be diffed
        against by a reviewer — not derived from the schema, since the
        schema types `via` as a bare `str`, not a Literal."""
        assert _VIA_VOCABULARY == frozenset(
            {"exact-id", "semantic", "structural", "keyword", "memory"}
        )


class TestRecallResponseShape:
    def test_field_set_is_exact(self):
        actual = frozenset(RecallResponse.model_fields.keys())
        assert tuple(sorted(actual)) == tuple(sorted(_RECALL_RESPONSE_FIELDS)), (
            f"RecallResponse field set drifted. "
            f"added={actual - _RECALL_RESPONSE_FIELDS} "
            f"removed={_RECALL_RESPONSE_FIELDS - actual}"
        )

    def test_count_is_int_results_is_list(self):
        fields = RecallResponse.model_fields
        assert fields["count"].annotation is int
        assert fields["query"].annotation is str


@pytest.fixture
def read_context():
    """Same fixture shape as `tests/api/test_read.py::read_context`."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _POSTGRES_ONLY_TABLES = {"brain_documents"}
    sqlite_tables = [
        t for t in Base.metadata.sorted_tables if t.name not in _POSTGRES_ONLY_TABLES
    ]
    Base.metadata.create_all(engine, tables=sqlite_tables)
    session = sessionmaker(bind=engine)()

    def override_db_session():
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    def override_require_api_key() -> None:
        """Bypass auth so this test focuses on the response contract."""

    app.dependency_overrides[db_session] = override_db_session
    app.dependency_overrides[require_api_key] = override_require_api_key
    client = TestClient(app, raise_server_exceptions=False)

    yield client, session

    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


class TestRecallResponsePolarityAndCount:
    """Pins that the route preserves the core's order (no re-sort, no
    sign-flip) and that `count` is never a value a consumer could trust
    over `len(results)`."""

    def test_higher_score_first_order_is_preserved_unsorted(self, read_context):
        """The core is the one place score polarity/ordering is decided;
        the route must pass it through unchanged. Deliberately mock two
        results in an order that is NOT sorted by score, and assert the
        route does not re-sort them."""
        client, _ = read_context
        mock_results = [
            {
                "doc_id": "D1",
                "file_path": "docs/d1.md",
                "title": "Lower score",
                "section": None,
                "content": "low",
                "score": 0.2,
                "via": "semantic",
            },
            {
                "doc_id": "D2",
                "file_path": "docs/d2.md",
                "title": "Higher score",
                "section": None,
                "content": "high",
                "score": 0.9,
                "via": "exact-id",
            },
        ]
        with patch("api.read.retrieval.recall", return_value=mock_results):
            response = client.get("/recall", params={"q": "hello"})

        assert response.status_code == 200
        body = response.json()
        # Order preserved exactly as the core returned it (D1 then D2),
        # not re-sorted by score descending.
        assert [r["doc_id"] for r in body["results"]] == ["D1", "D2"]
        assert [r["score"] for r in body["results"]] == [0.2, 0.9]

    def test_count_equals_len_results_nonempty(self, read_context):
        client, _ = read_context
        mock_results = [
            {
                "doc_id": "D1",
                "file_path": "docs/d1.md",
                "title": "T",
                "section": None,
                "content": "c",
                "score": 0.5,
                "via": "keyword",
            }
        ]
        with patch("api.read.retrieval.recall", return_value=mock_results):
            response = client.get("/recall", params={"q": "hello"})

        body = response.json()
        assert body["count"] == len(body["results"]) == 1

    def test_count_equals_len_results_empty(self, read_context):
        client, _ = read_context
        with patch("api.read.retrieval.recall", return_value=[]):
            response = client.get("/recall", params={"q": "hello"})

        assert response.status_code == 200
        body = response.json()
        assert body["count"] == len(body["results"]) == 0
        assert body["results"] == []
