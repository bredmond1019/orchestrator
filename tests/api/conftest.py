"""Local conftest for tests/api/ — pulls in the Docker-gated pgvector fixtures.

``pgvector_engine``/``pgvector_session`` live in ``tests/database/conftest.py``.
Pytest's conftest resolution is directory-scoped (fixtures defined under
``tests/database/`` are not visible to ``tests/api/`` by default). Importing
the already-decorated fixture functions into this module's namespace is enough
for pytest to discover them here too — no ``pytest_plugins`` declaration
needed (and a non-rootdir conftest can't use one), and no duplicated
Testcontainers setup. Mirrors ``tests/brain/conftest.py``.
"""

from tests.database.conftest import pgvector_engine, pgvector_session

__all__ = ["pgvector_engine", "pgvector_session"]
