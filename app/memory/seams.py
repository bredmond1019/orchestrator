"""Shared DB-session and embedding seams for the ``app/memory/`` package.

Every memory-package write/read path (``EpisodeWriteService``,
``UpsertMemoryNode``, ``MemoryLoaderNode``, ``ConsolidationWriteNode``,
``LoadMemoryContextNode``) previously copy-pasted the same two seams:

- ``_session_scope()`` — ``contextmanager(db_session)()``, wrapping the
  shared ``db_session`` generator factory (CLAUDE.md standing rule 7:
  persistence only via the shared session seam, never ad hoc).
- ``_embed(text)`` — ``EmbeddingService().embed_text(text)``.

This module centralizes both as a single implementation, kept in
``app/memory/`` (not ``app/core/``) to avoid a core-tier dependency from the
memory package.

``DbSeamMixin`` is a **mixin**, not a helper composed in — existing tests
monkeypatch ``node._session_scope`` (and ``node._embed``) **per-instance**;
an instance attribute shadows a mixin method, so those tests survive
untouched. Composition (e.g. a ``self._seams = DbSeamMixin()`` attribute)
would break every one of them, since the patched name would no longer be the
one the class body calls.
"""

from contextlib import contextmanager

from database.session import db_session
from services.embedding_service import EmbeddingService


def embed_text(text: str) -> list[float]:
    """Embed ``text`` via the configured ``EmbeddingService``.

    Module-level so any caller — a ``DbSeamMixin`` subclass's ``_embed``, or
    a node with no other reason to mix in the DB seam — can reuse the same
    single implementation.
    """
    return EmbeddingService().embed_text(text)


class DbSeamMixin:
    """Mixin providing the mockable ``_session_scope``/``_embed`` seams.

    Mix in wherever the file currently copy-pastes
    ``contextmanager(db_session)()`` and/or ``EmbeddingService().embed_text``.
    Both methods are isolated so tests can monkeypatch them per-instance to
    avoid touching a live database or a live embedding provider.
    """

    def _session_scope(self):
        """Return a context manager yielding a SQLAlchemy session.

        Isolated so tests can monkeypatch it to yield a real (e.g. in-memory
        SQLite) session without touching the deployment database.
        """
        return contextmanager(db_session)()

    def _embed(self, text: str) -> list[float]:
        """Embed ``text`` via the configured ``EmbeddingService``.

        Isolated so tests can monkeypatch it and avoid a live embedding
        provider call. Delegates to the module-level ``embed_text`` so the
        actual embedding call has exactly one implementation.
        """
        return embed_text(text)
