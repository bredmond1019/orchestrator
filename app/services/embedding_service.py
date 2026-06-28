"""EmbeddingService — provider-agnostic text embedding.

The backend is selected from configuration (env vars, overridable per call site
via constructor args) so the embedding model/provider can be swapped without
touching any caller. Supported providers:

* ``ollama`` (default) — a local Ollama server (free, repeatable, no API key).
  Used for the Brain RAG corpus and the workflow vector stores.
* ``voyage`` — hosted VoyageAI embeddings (requires ``VOYAGE_API_KEY``).

Configuration (all optional; constructor args win over env, env wins over the
built-in defaults):

| arg / env                          | default                  |
|------------------------------------|--------------------------|
| ``provider`` / ``EMBEDDING_PROVIDER`` | ``ollama``            |
| ``model`` / ``EMBEDDING_MODEL``       | per-provider default  |
| ``dims`` / ``EMBEDDING_DIM``          | ``1024``              |
| ``base_url`` / ``OLLAMA_BASE_URL``    | ``http://localhost:11434`` |
| ``timeout`` / ``EMBEDDING_TIMEOUT_SECONDS`` | ``60``          |

``dims`` must match the ``Vector(EMBEDDING_DIM)`` width of the pgvector columns
(currently 1024). The default model for every provider is 1024-dim, so the
default config needs no migration. A returned vector whose width differs from
``dims`` fails loudly here rather than corrupting the vector store on insert.
"""

import os

import httpx
import voyageai

_DEFAULT_PROVIDER = "ollama"
_DEFAULT_MODELS = {"ollama": "mxbai-embed-large", "voyage": "voyage-2"}
_DEFAULT_DIMS = 1024
_DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
_DEFAULT_TIMEOUT_SECONDS = 60.0


class EmbeddingService:
    """Produce embedding vectors for text via a configurable provider."""

    def __init__(
        self,
        model: str | None = None,
        dims: int | None = None,
        *,
        provider: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._provider = (
            provider or os.getenv("EMBEDDING_PROVIDER") or _DEFAULT_PROVIDER
        ).strip().lower()
        if self._provider not in _DEFAULT_MODELS:
            raise ValueError(
                f"Unknown EMBEDDING_PROVIDER {self._provider!r}; "
                f"expected one of {sorted(_DEFAULT_MODELS)}"
            )

        self._model = model or os.getenv("EMBEDDING_MODEL") or _DEFAULT_MODELS[self._provider]
        self._dims = int(dims or os.getenv("EMBEDDING_DIM") or _DEFAULT_DIMS)

        if self._provider == "ollama":
            raw_url = base_url or os.getenv("OLLAMA_BASE_URL") or _DEFAULT_OLLAMA_BASE_URL
            # Accept either the native host or the OpenAI-compat ".../v1" URL
            # (the value shipped in .env.example) and normalise to the native
            # host, since we call Ollama's native /api/embed endpoint.
            normalised = raw_url.rstrip("/")
            if normalised.endswith("/v1"):
                normalised = normalised[: -len("/v1")].rstrip("/")
            self._base_url = normalised
            self._timeout = float(
                timeout
                or os.getenv("EMBEDDING_TIMEOUT_SECONDS")
                or _DEFAULT_TIMEOUT_SECONDS
            )
        else:  # voyage
            api_key = os.environ["VOYAGE_API_KEY"]
            self._client = voyageai.Client(api_key=api_key)

    def embed_text(self, text: str) -> list[float]:
        """Embed a single string and return its vector."""
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of strings and return one vector per input (in order)."""
        if not texts:
            return []
        if self._provider == "ollama":
            embeddings = self._embed_ollama(texts)
        else:
            embeddings = self._embed_voyage(texts)
        self._assert_shape(embeddings, len(texts))
        return embeddings

    def _embed_voyage(self, texts: list[str]) -> list[list[float]]:
        """Embed via the hosted VoyageAI client."""
        result = self._client.embed(texts, model=self._model)
        return result.embeddings

    def _embed_ollama(self, texts: list[str]) -> list[list[float]]:
        """Embed via a local Ollama server's native /api/embed endpoint."""
        response = httpx.post(
            f"{self._base_url}/api/embed",
            json={"model": self._model, "input": texts},
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        embeddings = data.get("embeddings")
        if not embeddings:
            raise RuntimeError(
                f"Ollama embed response missing 'embeddings' for model "
                f"{self._model!r}: {data}"
            )
        return embeddings

    def _assert_shape(self, embeddings: list[list[float]], expected_count: int) -> None:
        """Fail loudly on a count or dimension mismatch.

        A wrong model (or a provider count truncation) must never silently write
        misaligned or wrong-width rows into the ``Vector(dims)`` column.
        """
        if len(embeddings) != expected_count:
            raise RuntimeError(
                f"{self._provider} returned {len(embeddings)} vectors for "
                f"{expected_count} inputs"
            )
        if embeddings and len(embeddings[0]) != self._dims:
            raise RuntimeError(
                f"{self._provider} model {self._model!r} returned "
                f"{len(embeddings[0])}-dim vectors; expected {self._dims}. "
                f"Check EMBEDDING_MODEL/EMBEDDING_DIM against the pgvector column width."
            )
