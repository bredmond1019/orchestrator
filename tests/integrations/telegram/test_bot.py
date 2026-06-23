"""Tests for integrations.telegram.bot.

Guarded with pytest.importorskip so the collection passes when the
optional ``python-telegram-bot`` extra is not installed.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

telegram = pytest.importorskip("telegram")

from integrations.telegram.bot import (  # noqa: E402 — after importorskip
    _build_allowlist_filter,
    _handle_digest,
    _handle_url_message,
    _is_valid_url,
)


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------


class TestIsValidUrl:
    def test_accepts_https_url(self):
        assert _is_valid_url("https://example.com/article") is True

    def test_accepts_http_url(self):
        assert _is_valid_url("http://example.com") is True

    def test_rejects_bare_text(self):
        assert _is_valid_url("just some text") is False

    def test_rejects_ftp_url(self):
        assert _is_valid_url("ftp://example.com") is False

    def test_rejects_empty(self):
        assert _is_valid_url("") is False


# ---------------------------------------------------------------------------
# Allowlist filter
# ---------------------------------------------------------------------------


class TestAllowlistFilter:
    def _make_message(self, chat_id: int):
        msg = MagicMock()
        msg.chat_id = chat_id
        return msg

    def test_empty_allowlist_permits_all(self):
        flt = _build_allowlist_filter([])
        from telegram.ext import filters as tg_filters
        assert flt is tg_filters.ALL

    def test_filter_permits_listed_chat(self):
        flt = _build_allowlist_filter([111, 222])
        assert flt.filter(self._make_message(111)) is True

    def test_filter_rejects_unlisted_chat(self):
        flt = _build_allowlist_filter([111, 222])
        assert flt.filter(self._make_message(999)) is False


# ---------------------------------------------------------------------------
# /digest command handler
# ---------------------------------------------------------------------------


def _make_update(text: str = "", chat_id: int = 12345):
    """Build a minimal mock Update object."""
    update = MagicMock()
    update.message = MagicMock()
    update.message.chat_id = chat_id
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


def _make_context(args: list[str] | None = None):
    ctx = MagicMock()
    ctx.args = args or []
    return ctx


_GOOD_CFG = {
    "api_base_url": "http://localhost:8080",
    "api_key": "test-key",
    "cf_client_id": "",
    "cf_client_secret": "",
}

_SUBMIT_PATH = "integrations.telegram.bot.submit_event"


class TestHandleDigest:
    @pytest.mark.asyncio
    async def test_replies_usage_when_no_args(self):
        update = _make_update()
        ctx = _make_context(args=[])
        await _handle_digest(update, ctx, _GOOD_CFG)
        update.message.reply_text.assert_awaited_once()
        msg = update.message.reply_text.call_args[0][0]
        assert "Usage" in msg

    @pytest.mark.asyncio
    async def test_rejects_invalid_url(self):
        update = _make_update()
        ctx = _make_context(args=["not-a-url"])
        await _handle_digest(update, ctx, _GOOD_CFG)
        msg = update.message.reply_text.call_args[0][0]
        assert "valid" in msg.lower()

    @pytest.mark.asyncio
    async def test_submits_content_pipeline_event(self):
        update = _make_update()
        ctx = _make_context(args=["https://example.com/article"])
        with patch(_SUBMIT_PATH, return_value={"task_id": "t-1", "message": "ok"}) as mock_sub:
            await _handle_digest(update, ctx, _GOOD_CFG)
        mock_sub.assert_called_once()
        call_kwargs = mock_sub.call_args
        assert call_kwargs[0][0] == "CONTENT_PIPELINE"
        payload = call_kwargs[0][1]
        assert payload["url"] == "https://example.com/article"
        assert payload["make_blog"] is False

    @pytest.mark.asyncio
    async def test_replies_queued_on_success(self):
        update = _make_update()
        ctx = _make_context(args=["https://example.com/article"])
        with patch(_SUBMIT_PATH, return_value={"task_id": "t-1", "message": "ok"}):
            await _handle_digest(update, ctx, _GOOD_CFG)
        reply = update.message.reply_text.call_args[0][0]
        assert "Queued" in reply

    @pytest.mark.asyncio
    async def test_replies_error_on_api_failure(self):
        import httpx
        update = _make_update()
        ctx = _make_context(args=["https://example.com/article"])
        with patch(_SUBMIT_PATH, side_effect=httpx.RequestError("connection refused")):
            await _handle_digest(update, ctx, _GOOD_CFG)
        reply = update.message.reply_text.call_args[0][0]
        assert "Failed" in reply or "failed" in reply.lower()


# ---------------------------------------------------------------------------
# Bare URL message handler
# ---------------------------------------------------------------------------


class TestHandleUrlMessage:
    @pytest.mark.asyncio
    async def test_submits_bare_url(self):
        update = _make_update(text="https://example.com/page")
        ctx = _make_context()
        with patch(_SUBMIT_PATH, return_value={"task_id": "t-2", "message": "ok"}) as mock_sub:
            await _handle_url_message(update, ctx, _GOOD_CFG)
        mock_sub.assert_called_once()
        payload = mock_sub.call_args[0][1]
        assert payload["url"] == "https://example.com/page"
        assert payload["make_blog"] is False

    @pytest.mark.asyncio
    async def test_rejects_non_url_message(self):
        update = _make_update(text="hello world")
        ctx = _make_context()
        await _handle_url_message(update, ctx, _GOOD_CFG)
        msg = update.message.reply_text.call_args[0][0]
        assert "valid" in msg.lower()

    @pytest.mark.asyncio
    async def test_passes_auth_headers_to_client(self):
        cfg = {
            **_GOOD_CFG,
            "cf_client_id": "cf-id",
            "cf_client_secret": "cf-sec",
        }
        update = _make_update(text="https://example.com/page")
        ctx = _make_context()
        with patch(_SUBMIT_PATH, return_value={"task_id": "t-3", "message": "ok"}) as mock_sub:
            await _handle_url_message(update, ctx, cfg)
        call_kwargs = mock_sub.call_args[1]
        assert call_kwargs["cf_client_id"] == "cf-id"
        assert call_kwargs["cf_client_secret"] == "cf-sec"
