"""Unit tests for SearchService."""

from unittest.mock import MagicMock, patch

import pytest

from services.search_service import SearchResult, SearchService


@pytest.fixture
def mock_tavily():
    with patch("services.search_service.TavilyClient") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def service(mock_tavily, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    return SearchService()


class TestSearch:
    def test_returns_search_result_instances(self, service, mock_tavily):
        mock_tavily.search.return_value = {
            "results": [
                {"title": "A", "url": "https://a.com", "content": "text", "score": 0.9}
            ]
        }
        results = service.search("test query")
        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].title == "A"
        assert results[0].score == 0.9

    def test_max_results_passed_to_client(self, service, mock_tavily):
        mock_tavily.search.return_value = {"results": []}
        service.search("query", max_results=3)
        mock_tavily.search.assert_called_once_with("query", max_results=3)

    def test_empty_results_returns_empty_list(self, service, mock_tavily):
        mock_tavily.search.return_value = {"results": []}
        assert service.search("nothing") == []

    def test_missing_fields_default_gracefully(self, service, mock_tavily):
        mock_tavily.search.return_value = {"results": [{"url": "https://b.com"}]}
        results = service.search("partial")
        assert len(results) == 1
        assert results[0].title == ""
        assert results[0].content == ""
        assert results[0].score is None
