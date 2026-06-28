"""Unit tests for EmbeddingService (provider-agnostic embedding)."""

from unittest.mock import MagicMock, patch

import pytest

from services.embedding_service import EmbeddingService


# ---------------------------------------------------------------------------
# Voyage provider
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_voyage_client():
    with patch("services.embedding_service.voyageai.Client") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def voyage_service(mock_voyage_client, monkeypatch):
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    return EmbeddingService(provider="voyage", dims=3)


class TestVoyageEmbedText:
    def test_returns_first_embedding(self, voyage_service, mock_voyage_client):
        mock_voyage_client.embed.return_value = MagicMock(embeddings=[[0.1, 0.2, 0.3]])
        result = voyage_service.embed_text("hello")
        assert result == [0.1, 0.2, 0.3]

    def test_calls_embed_with_single_item_list(self, voyage_service, mock_voyage_client):
        mock_voyage_client.embed.return_value = MagicMock(embeddings=[[0.0, 0.0, 0.0]])
        voyage_service.embed_text("test")
        mock_voyage_client.embed.assert_called_once_with(["test"], model="voyage-2")


class TestVoyageEmbedBatch:
    def test_returns_list_of_float_lists(self, voyage_service, mock_voyage_client):
        mock_voyage_client.embed.return_value = MagicMock(
            embeddings=[[0.1, 0.2, 0.5], [0.3, 0.4, 0.6]]
        )
        result = voyage_service.embed_batch(["a", "b"])
        assert len(result) == 2
        assert result[0] == [0.1, 0.2, 0.5]

    def test_delegates_full_list_to_client(self, voyage_service, mock_voyage_client):
        mock_voyage_client.embed.return_value = MagicMock(
            embeddings=[[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
        )
        voyage_service.embed_batch(["x", "y"])
        mock_voyage_client.embed.assert_called_once_with(["x", "y"], model="voyage-2")

    def test_custom_model_passed_to_client(self, mock_voyage_client, monkeypatch):
        monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
        svc = EmbeddingService(provider="voyage", model="voyage-large-2", dims=1)
        mock_voyage_client.embed.return_value = MagicMock(embeddings=[[1.0]])
        svc.embed_text("seam")
        mock_voyage_client.embed.assert_called_once_with(["seam"], model="voyage-large-2")


# ---------------------------------------------------------------------------
# Ollama provider (default)
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_httpx_post():
    with patch("services.embedding_service.httpx.post") as mock_post:
        yield mock_post


def _ollama_response(embeddings):
    resp = MagicMock()
    resp.json.return_value = {"embeddings": embeddings}
    resp.raise_for_status.return_value = None
    return resp


class TestOllamaProvider:
    def test_default_provider_is_ollama(self, monkeypatch):
        monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
        svc = EmbeddingService(dims=3)
        # No VOYAGE_API_KEY needed and no voyage client constructed.
        assert svc._provider == "ollama"
        assert svc._model == "mxbai-embed-large"

    def test_embed_batch_posts_to_native_endpoint(self, mock_httpx_post, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
        mock_httpx_post.return_value = _ollama_response([[0.1, 0.2], [0.3, 0.4]])
        svc = EmbeddingService(provider="ollama", dims=2)
        result = svc.embed_batch(["a", "b"])
        assert result == [[0.1, 0.2], [0.3, 0.4]]
        args, kwargs = mock_httpx_post.call_args
        assert args[0] == "http://localhost:11434/api/embed"
        assert kwargs["json"] == {"model": "mxbai-embed-large", "input": ["a", "b"]}

    def test_embed_text_returns_first_vector(self, mock_httpx_post):
        mock_httpx_post.return_value = _ollama_response([[1.0, 2.0, 3.0]])
        svc = EmbeddingService(provider="ollama", dims=3)
        assert svc.embed_text("hi") == [1.0, 2.0, 3.0]

    def test_openai_compat_v1_url_is_normalised(self, mock_httpx_post, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        mock_httpx_post.return_value = _ollama_response([[0.0]])
        svc = EmbeddingService(provider="ollama", dims=1)
        svc.embed_text("x")
        assert mock_httpx_post.call_args[0][0] == "http://localhost:11434/api/embed"

    def test_missing_embeddings_key_raises(self, mock_httpx_post):
        resp = MagicMock()
        resp.json.return_value = {"error": "model not found"}
        resp.raise_for_status.return_value = None
        mock_httpx_post.return_value = resp
        svc = EmbeddingService(provider="ollama", dims=3)
        with pytest.raises(RuntimeError, match="missing 'embeddings'"):
            svc.embed_text("boom")


# ---------------------------------------------------------------------------
# Provider-agnostic behaviour
# ---------------------------------------------------------------------------
class TestProviderSelectionAndGuards:
    def test_unknown_provider_raises(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "bogus")
        with pytest.raises(ValueError, match="Unknown EMBEDDING_PROVIDER"):
            EmbeddingService()

    def test_env_selects_provider(self, mock_httpx_post, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
        monkeypatch.setenv("EMBEDDING_MODEL", "custom-embed")
        mock_httpx_post.return_value = _ollama_response([[0.0, 0.1]])
        svc = EmbeddingService(dims=2)
        svc.embed_text("x")
        assert mock_httpx_post.call_args[1]["json"]["model"] == "custom-embed"

    def test_empty_batch_short_circuits(self, mock_httpx_post):
        svc = EmbeddingService(provider="ollama", dims=3)
        assert svc.embed_batch([]) == []
        mock_httpx_post.assert_not_called()

    def test_dimension_mismatch_raises(self, mock_httpx_post):
        mock_httpx_post.return_value = _ollama_response([[0.1, 0.2]])  # 2-dim
        svc = EmbeddingService(provider="ollama", dims=1024)
        with pytest.raises(RuntimeError, match="expected 1024"):
            svc.embed_text("wrong width")

    def test_count_mismatch_raises(self, mock_httpx_post):
        mock_httpx_post.return_value = _ollama_response([[0.1, 0.2]])  # 1 vector
        svc = EmbeddingService(provider="ollama", dims=2)
        with pytest.raises(RuntimeError, match="returned 1 vectors for 2 inputs"):
            svc.embed_batch(["a", "b"])
