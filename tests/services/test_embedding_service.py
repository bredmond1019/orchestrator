"""Unit tests for EmbeddingService."""

from unittest.mock import MagicMock, patch

import pytest

from services.embedding_service import EmbeddingService


@pytest.fixture
def mock_voyage_client():
    with patch("services.embedding_service.voyageai.Client") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def service(mock_voyage_client, monkeypatch):
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    return EmbeddingService()


class TestEmbedText:
    def test_returns_first_embedding(self, service, mock_voyage_client):
        mock_voyage_client.embed.return_value = MagicMock(embeddings=[[0.1, 0.2, 0.3]])
        result = service.embed_text("hello")
        assert result == [0.1, 0.2, 0.3]

    def test_calls_embed_with_single_item_list(self, service, mock_voyage_client):
        mock_voyage_client.embed.return_value = MagicMock(embeddings=[[0.0]])
        service.embed_text("test")
        mock_voyage_client.embed.assert_called_once_with(["test"], model="voyage-2")


class TestEmbedBatch:
    def test_returns_list_of_float_lists(self, service, mock_voyage_client):
        mock_voyage_client.embed.return_value = MagicMock(
            embeddings=[[0.1, 0.2], [0.3, 0.4]]
        )
        result = service.embed_batch(["a", "b"])
        assert len(result) == 2
        assert result[0] == [0.1, 0.2]

    def test_delegates_full_list_to_client(self, service, mock_voyage_client):
        mock_voyage_client.embed.return_value = MagicMock(embeddings=[[], []])
        service.embed_batch(["x", "y"])
        mock_voyage_client.embed.assert_called_once_with(["x", "y"], model="voyage-2")


class TestConfigSwapSeam:
    def test_custom_model_passed_to_client(self, mock_voyage_client, monkeypatch):
        monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
        svc = EmbeddingService(model="local-qwen3", dims=768)
        mock_voyage_client.embed.return_value = MagicMock(embeddings=[[1.0]])
        svc.embed_text("seam")
        mock_voyage_client.embed.assert_called_once_with(["seam"], model="local-qwen3")
