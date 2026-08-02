"""Local conftest for tests/brain/ — pulls in the Docker-gated pgvector fixtures.

``pgvector_engine``/``pgvector_session`` live in ``tests/database/conftest.py``.
Pytest's conftest resolution is directory-scoped (fixtures defined under
``tests/database/`` are not visible to ``tests/brain/`` by default). Importing
the already-decorated fixture functions into this module's namespace is enough
for pytest to discover them here too — no ``pytest_plugins`` declaration
needed (and a non-rootdir conftest can't use one), and no duplicated
Testcontainers setup.
"""

import pytest

from tests.database.conftest import pgvector_engine, pgvector_session

__all__ = ["pgvector_engine", "pgvector_session", "enable_query_log"]


@pytest.fixture
def enable_query_log(monkeypatch):
    """Opt back into the OR.K1 retrieval query log for one test.

    The top-level `tests/conftest.py::_disable_query_log` autouse fixture
    forces `BRAIN_QUERY_LOG_ENABLED=0` for the whole suite; tests that
    assert on written `retrieval_queries` rows request this fixture to flip
    it back on.
    """
    monkeypatch.setenv("BRAIN_QUERY_LOG_ENABLED", "1")
