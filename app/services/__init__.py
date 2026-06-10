"""Shared services layer."""

from services.article_extraction_service import ArticleExtractionService, ArticleResult

__all__ = [
    "ArticleExtractionService",
    "ArticleResult",
]
