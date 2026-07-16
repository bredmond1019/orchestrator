"""Tests for app/memory/seams.py — DbSeamMixin + embed_text.

Covers:
- ``DbSeamMixin._session_scope`` yields a context manager wrapping the
  shared ``db_session`` generator factory.
- ``DbSeamMixin._embed`` delegates to the module-level ``embed_text``.
- ``embed_text`` delegates to ``EmbeddingService().embed_text``.
- The mixin's methods are shadowable per-instance (the property this whole
  refactor depends on: existing tests across the memory package monkeypatch
  ``node._session_scope``/``node._embed`` per instance, and an instance
  attribute must shadow the mixin method rather than the mixin winning).
"""

from unittest.mock import MagicMock, patch

from memory.seams import DbSeamMixin, embed_text


class TestEmbedText:
    """embed_text() wraps EmbeddingService().embed_text unchanged."""

    def test_delegates_to_embedding_service(self):
        fake_service = MagicMock()
        fake_service.embed_text.return_value = [0.1, 0.2, 0.3]
        with patch("memory.seams.EmbeddingService", return_value=fake_service):
            result = embed_text("hello world")

        fake_service.embed_text.assert_called_once_with("hello world")
        assert result == [0.1, 0.2, 0.3]


class _Consumer(DbSeamMixin):
    """Minimal class mixing in DbSeamMixin, standing in for a real node."""


class TestDbSeamMixinSessionScope:
    """DbSeamMixin._session_scope wraps the shared db_session factory."""

    def test_session_scope_wraps_db_session(self):
        consumer = _Consumer()
        fake_session = MagicMock()

        def _fake_db_session():
            yield fake_session

        with patch("memory.seams.db_session", _fake_db_session):
            with consumer._session_scope() as session:  # noqa: SLF001
                assert session is fake_session

    def test_session_scope_is_a_fresh_context_manager_each_call(self):
        consumer = _Consumer()

        def _fake_db_session():
            yield MagicMock()

        with patch("memory.seams.db_session", _fake_db_session):
            first = consumer._session_scope()  # noqa: SLF001
            second = consumer._session_scope()  # noqa: SLF001
            assert first is not second


class TestDbSeamMixinEmbed:
    """DbSeamMixin._embed delegates to the module-level embed_text."""

    def test_embed_delegates_to_embed_text(self):
        consumer = _Consumer()
        with patch("memory.seams.embed_text", return_value=[1.0, 2.0]) as mock_embed:
            result = consumer._embed("some fact")  # noqa: SLF001

        mock_embed.assert_called_once_with("some fact")
        assert result == [1.0, 2.0]


class TestPerInstanceShadowing:
    """A per-instance monkeypatch of _session_scope/_embed shadows the mixin.

    This is the property Task 1's design depends on: many existing tests do
    ``node._session_scope = <fake>`` / ``node._embed = <fake>`` on a single
    instance. Because DbSeamMixin provides these as ordinary methods (not
    e.g. properties or slots), an instance attribute of the same name wins
    per normal Python attribute lookup — the mixin method is never reached.
    """

    def test_instance_attribute_shadows_mixin_session_scope(self):
        consumer = _Consumer()
        sentinel = object()
        consumer._session_scope = lambda: sentinel  # noqa: SLF001
        assert consumer._session_scope() is sentinel  # noqa: SLF001

    def test_instance_attribute_shadows_mixin_embed(self):
        consumer = _Consumer()
        consumer._embed = lambda text: [9.9]  # noqa: SLF001
        assert consumer._embed("anything") == [9.9]  # noqa: SLF001
