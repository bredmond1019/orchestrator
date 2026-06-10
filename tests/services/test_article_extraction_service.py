"""Unit tests for ArticleExtractionService."""

from unittest.mock import MagicMock, patch

import pytest

from services.article_extraction_service import ArticleExtractionService, ArticleResult


@pytest.fixture
def service_no_firecrawl(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    return ArticleExtractionService()


@pytest.fixture
def service_with_firecrawl(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "test-key")
    return ArticleExtractionService()


class TestTrafilaturaSuccess:
    def test_returns_ok_status_when_text_extracted(self, service_no_firecrawl):
        with (
            patch(
                "services.article_extraction_service.trafilatura.fetch_url",
                return_value=b"<html>content</html>",
            ),
            patch(
                "services.article_extraction_service.trafilatura.extract",
                return_value="Article text",
            ),
        ):
            result = service_no_firecrawl.extract("https://example.com/article")
        assert isinstance(result, ArticleResult)
        assert result.fetch_status == "ok"
        assert result.text == "Article text"

    def test_does_not_call_firecrawl_on_success(self, service_with_firecrawl):
        with (
            patch(
                "services.article_extraction_service.trafilatura.fetch_url",
                return_value=b"<html>content</html>",
            ),
            patch(
                "services.article_extraction_service.trafilatura.extract",
                return_value="Clean article",
            ),
            patch("services.article_extraction_service.FirecrawlApp") as mock_fc_cls,
        ):
            result = service_with_firecrawl.extract("https://example.com/article")
        assert result.fetch_status == "ok"
        mock_fc_cls.assert_not_called()


class TestFirecrawlFallback:
    def test_fallback_triggered_when_trafilatura_empty(self, service_with_firecrawl):
        mock_fc = MagicMock()
        mock_fc.scrape_url.return_value = {"markdown": "Firecrawl content"}
        with (
            patch(
                "services.article_extraction_service.trafilatura.fetch_url",
                return_value=None,
            ),
            patch(
                "services.article_extraction_service.FirecrawlApp",
                return_value=mock_fc,
            ),
        ):
            result = service_with_firecrawl.extract("https://js-heavy.com")
        assert result.fetch_status == "fallback_used"
        assert result.text == "Firecrawl content"

    def test_fallback_skipped_without_api_key(self, service_no_firecrawl):
        with (
            patch(
                "services.article_extraction_service.trafilatura.fetch_url",
                return_value=None,
            ),
            patch("services.article_extraction_service.FirecrawlApp") as mock_fc_cls,
        ):
            result = service_no_firecrawl.extract("https://js-heavy.com")
        assert result.fetch_status == "failed"
        mock_fc_cls.assert_not_called()

    def test_fallback_failure_returns_failed_status(self, service_with_firecrawl):
        mock_fc = MagicMock()
        mock_fc.scrape_url.side_effect = RuntimeError("network down")
        with (
            patch(
                "services.article_extraction_service.trafilatura.fetch_url",
                return_value=None,
            ),
            patch(
                "services.article_extraction_service.FirecrawlApp",
                return_value=mock_fc,
            ),
        ):
            result = service_with_firecrawl.extract("https://js-heavy.com")
        assert result.fetch_status == "failed"
        assert result.text == ""

    def test_fallback_empty_content_returns_failed(self, service_with_firecrawl):
        mock_fc = MagicMock()
        mock_fc.scrape_url.return_value = {"markdown": "", "content": ""}
        with (
            patch(
                "services.article_extraction_service.trafilatura.fetch_url",
                return_value=None,
            ),
            patch(
                "services.article_extraction_service.FirecrawlApp",
                return_value=mock_fc,
            ),
        ):
            result = service_with_firecrawl.extract("https://js-heavy.com")
        assert result.fetch_status == "failed"


class TestGracefulFailure:
    def test_graceful_failure_when_all_fail(self, service_no_firecrawl):
        with patch(
            "services.article_extraction_service.trafilatura.fetch_url",
            return_value=None,
        ):
            result = service_no_firecrawl.extract("https://broken.com")
        assert result.fetch_status == "failed"
        assert result.text == ""
