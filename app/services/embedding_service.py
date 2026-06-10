"""EmbeddingService wraps VoyageAI (or any provider) to produce float vectors."""

import os

import voyageai


class EmbeddingService:
    """Produce embedding vectors for text.

    The ``model`` and ``dims`` are constructor params so a local embedding
    model (e.g. Qwen3-Embedding via Ollama) slots in without code changes.
    This is the deliberate provider seam that Project H evaluates.
    """

    def __init__(self, model: str = "voyage-2", dims: int = 1024) -> None:
        api_key = os.environ["VOYAGE_API_KEY"]
        self._client = voyageai.Client(api_key=api_key)
        self._model = model
        self._dims = dims

    def embed_text(self, text: str) -> list[float]:
        """Embed a single string and return its vector."""
        result = self._client.embed([text], model=self._model)
        return result.embeddings[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of strings and return one vector per input."""
        result = self._client.embed(texts, model=self._model)
        return result.embeddings
