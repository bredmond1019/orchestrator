"""HTTP client for submitting events to the orchestration API.

Uses ``httpx`` (already a dev dep) for synchronous HTTP so the module is
importable without the optional ``python-telegram-bot`` extra.  The client
is intentionally fire-and-forget: it submits the event and returns the 202
response body; it never polls for a result.
"""

import logging

import httpx

logger = logging.getLogger(__name__)

_EVENTS_PATH = "/events/"


def submit_event(
    workflow_type: str,
    data: dict,
    *,
    api_base_url: str,
    api_key: str,
    cf_client_id: str = "",
    cf_client_secret: str = "",
) -> dict:
    """Submit a workflow event to the orchestration API.

    Args:
        workflow_type: Registered workflow type string (e.g. ``"CONTENT_PIPELINE"``).
        data: Workflow-specific payload dict.
        api_base_url: Base URL of the orchestration API
            (e.g. ``http://localhost:8080``).
        api_key: Value for the ``X-API-Key`` authentication header.
        cf_client_id: Cloudflare Access client ID (sent only when non-empty).
        cf_client_secret: Cloudflare Access client secret (sent only when non-empty).

    Returns:
        dict: Parsed JSON body from the 202 Accepted response, containing
            at minimum ``task_id`` and ``message``.

    Raises:
        httpx.HTTPStatusError: The API returned a non-2xx status.
        httpx.RequestError: A network-level failure occurred.
    """
    url = api_base_url.rstrip("/") + _EVENTS_PATH
    headers: dict[str, str] = {"X-API-Key": api_key}
    if cf_client_id and cf_client_secret:
        headers["CF-Access-Client-Id"] = cf_client_id
        headers["CF-Access-Client-Secret"] = cf_client_secret

    payload = {"workflow_type": workflow_type, "data": data}

    logger.info("Submitting event workflow_type=%s to %s", workflow_type, url)

    response = httpx.post(url, json=payload, headers=headers, timeout=10.0)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "API returned %s for workflow_type=%s: %s",
            exc.response.status_code,
            workflow_type,
            exc.response.text,
        )
        raise

    return response.json()
