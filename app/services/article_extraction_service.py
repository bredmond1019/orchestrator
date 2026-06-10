"""ArticleExtractionService — trafilatura first, Firecrawl fallback."""

import logging
import os

import trafilatura
from pydantic import BaseModel

try:
    from firecrawl import FirecrawlApp
except ImportError:  # pragma: no cover - firecrawl is an optional runtime dep
    FirecrawlApp = None

log = logging.getLogger(__name__)


class ArticleResult(BaseModel):
    """Structured result of an article extraction attempt."""

    text: str
    title: str | None = None
    fetch_status: str  # "ok" | "fallback_used" | "failed"


class ArticleExtractionService:
    """Extract readable article text from a URL.

    Default path uses ``trafilatura`` (free, local, fast for clean articles).
    When trafilatura returns nothing — typically JS-rendered pages — and a
    ``FIRECRAWL_API_KEY`` is present, falls back to Firecrawl's hosted scraper.

    The service is stateless and never raises on extraction failure: callers
    receive an ``ArticleResult`` with ``fetch_status="failed"`` instead. Any
    per-agent call budget belongs in the calling node, not here.
    """

    def __init__(self) -> None:
        self._firecrawl_key = os.getenv("FIRECRAWL_API_KEY")

    def extract(self, url: str) -> ArticleResult:
        """Return extracted article content for ``url``.

        Never raises: on total failure returns ``fetch_status="failed"`` and
        logs the failure so the surrounding pipeline keeps running.
        """
        downloaded = trafilatura.fetch_url(url)
        text = trafilatura.extract(downloaded) if downloaded else None

        if text:
            return ArticleResult(text=text, fetch_status="ok")

        if self._firecrawl_key and FirecrawlApp is not None:
            fallback = self._extract_with_firecrawl(url)
            if fallback is not None:
                return fallback

        log.warning("Article extraction failed for %s", url)
        return ArticleResult(text="", fetch_status="failed")

    def _extract_with_firecrawl(self, url: str) -> ArticleResult | None:
        """Attempt the Firecrawl fallback; return None if it yields nothing."""
        try:
            fc_app = FirecrawlApp(api_key=self._firecrawl_key)
            result = fc_app.scrape_url(url, params={"formats": ["markdown"]})
            content = result.get("markdown") or result.get("content", "")
            if content:
                return ArticleResult(text=content, fetch_status="fallback_used")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.warning("Firecrawl fallback failed for %s: %s", url, exc)
        return None
