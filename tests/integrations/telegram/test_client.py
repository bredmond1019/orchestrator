"""Tests for integrations.telegram.client.

Uses httpx's mock transport — always runs (no python-telegram-bot import needed).
"""

import json

import httpx
import pytest

from integrations.telegram.client import submit_event


class _MockTransport(httpx.BaseTransport):
    """Minimal httpx transport that returns a preset response."""

    def __init__(self, status_code: int = 202, body: dict | None = None):
        self._status_code = status_code
        self._body = body or {"task_id": "abc-123", "message": "ok"}

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self._last_request = request
        return httpx.Response(
            self._status_code,
            headers={"content-type": "application/json"},
            content=json.dumps(self._body).encode("utf-8"),
            request=request,
        )


def _make_transport_and_call(
    *,
    workflow_type: str = "CONTENT_PIPELINE",
    data: dict | None = None,
    api_base_url: str = "http://testserver",
    api_key: str = "test-key",
    cf_client_id: str = "",
    cf_client_secret: str = "",
    status_code: int = 202,
    body: dict | None = None,
) -> tuple[_MockTransport, dict]:
    transport = _MockTransport(status_code=status_code, body=body)
    # Monkey-patch httpx.post to use our mock transport
    original_post = httpx.post

    def _patched_post(url, *, json=None, headers=None, timeout=None):
        client = httpx.Client(transport=transport)
        return client.post(url, json=json, headers=headers, timeout=timeout)

    import integrations.telegram.client as _mod

    original = _mod.httpx.post
    _mod.httpx.post = _patched_post
    try:
        result = submit_event(
            workflow_type,
            data or {"url": "https://example.com", "make_blog": False},
            api_base_url=api_base_url,
            api_key=api_key,
            cf_client_id=cf_client_id,
            cf_client_secret=cf_client_secret,
        )
    finally:
        _mod.httpx.post = original

    return transport, result


class TestSubmitEventPayload:
    """Verify the CONTENT_PIPELINE payload and auth headers."""

    def test_sends_correct_workflow_type(self):
        transport, result = _make_transport_and_call(workflow_type="CONTENT_PIPELINE")
        req = transport._last_request
        body = json.loads(req.content)
        assert body["workflow_type"] == "CONTENT_PIPELINE"

    def test_sends_url_and_make_blog_false(self):
        transport, _ = _make_transport_and_call(
            data={"url": "https://example.com/article", "make_blog": False}
        )
        body = json.loads(transport._last_request.content)
        assert body["data"]["url"] == "https://example.com/article"
        assert body["data"]["make_blog"] is False

    def test_sends_x_api_key_header(self):
        transport, _ = _make_transport_and_call(api_key="secret-key")
        assert transport._last_request.headers["x-api-key"] == "secret-key"

    def test_sends_cf_headers_when_set(self):
        transport, _ = _make_transport_and_call(
            cf_client_id="cf-id-123",
            cf_client_secret="cf-secret-456",
        )
        headers = transport._last_request.headers
        assert headers["cf-access-client-id"] == "cf-id-123"
        assert headers["cf-access-client-secret"] == "cf-secret-456"

    def test_omits_cf_headers_when_not_set(self):
        transport, _ = _make_transport_and_call()
        headers = transport._last_request.headers
        assert "cf-access-client-id" not in headers
        assert "cf-access-client-secret" not in headers

    def test_posts_to_events_endpoint(self):
        transport, _ = _make_transport_and_call(api_base_url="http://localhost:8080")
        assert transport._last_request.url.path == "/events/"

    def test_returns_202_body(self):
        _, result = _make_transport_and_call(body={"task_id": "xyz", "message": "started"})
        assert result["task_id"] == "xyz"
        assert result["message"] == "started"


class TestSubmitEventErrors:
    """Verify error propagation."""

    def test_raises_on_4xx(self):
        with pytest.raises(httpx.HTTPStatusError):
            _make_transport_and_call(
                status_code=401, body={"detail": "Unauthorized"}
            )

    def test_raises_on_5xx(self):
        with pytest.raises(httpx.HTTPStatusError):
            _make_transport_and_call(
                status_code=503, body={"detail": "Service Unavailable"}
            )
