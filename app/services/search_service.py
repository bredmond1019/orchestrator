"""SearchService wraps Tavily to produce structured search results."""

import os

from pydantic import BaseModel
from tavily import TavilyClient


class SearchResult(BaseModel):
    """A single structured search result suitable for a tool-use agent loop."""

    title: str
    url: str
    content: str
    score: float | None = None


class SearchService:
    """Thin wrapper over the Tavily search client returning typed results."""

    def __init__(self) -> None:
        api_key = os.environ["TAVILY_API_KEY"]
        self._client = TavilyClient(api_key=api_key)

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Run a search and return clean structured results."""
        response = self._client.search(query, max_results=max_results)
        return [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", ""),
                score=r.get("score"),
            )
            for r in response.get("results", [])
        ]
