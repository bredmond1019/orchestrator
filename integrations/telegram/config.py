"""Environment-driven configuration for the Telegram bot integration.

All required variables are validated at import time so the bot fails fast
instead of producing cryptic errors at runtime.

Required:
    TELEGRAM_BOT_TOKEN         — Bot token from @BotFather.
    ORCHESTRATION_API_KEY      — Shared secret for ``X-API-Key`` auth.

Optional:
    ORCHESTRATION_API_BASE_URL — Base URL for the orchestration API
                                  (default: ``http://localhost:8080``).
    TELEGRAM_ALLOWED_CHAT_IDS  — Comma-separated integer chat IDs to accept.
                                  Empty string or unset means no allowlist
                                  (accept all chats — not recommended for
                                  production).
    CF_ACCESS_CLIENT_ID        — Cloudflare Access service-token client ID.
    CF_ACCESS_CLIENT_SECRET    — Cloudflare Access service-token secret.
                                  Both CF vars must be set together; if only
                                  one is present the bot raises at startup.
"""

import os


class _MissingEnvError(RuntimeError):
    """Raised when a required environment variable is absent."""


def _require(name: str) -> str:
    """Return the value of *name* or raise if it is unset or empty."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise _MissingEnvError(
            f"Required environment variable {name!r} is not set. "
            "Ensure it is present before starting the Telegram bot."
        )
    return value


def _optional(name: str, default: str = "") -> str:
    """Return the value of *name*, falling back to *default*."""
    return os.environ.get(name, default).strip()


def load_config() -> dict:
    """Load and validate the bot configuration from environment variables.

    Returns:
        dict: Validated configuration mapping with keys:
            ``bot_token``, ``api_key``, ``api_base_url``,
            ``allowed_chat_ids``, ``cf_client_id``, ``cf_client_secret``.

    Raises:
        _MissingEnvError: A required variable is absent.
        ValueError: Only one of the CF Access pair is set.
    """
    bot_token = _require("TELEGRAM_BOT_TOKEN")
    api_key = _require("ORCHESTRATION_API_KEY")
    api_base_url = _optional("ORCHESTRATION_API_BASE_URL", "http://localhost:8080")

    raw_ids = _optional("TELEGRAM_ALLOWED_CHAT_IDS", "")
    if raw_ids:
        allowed_chat_ids: list[int] = [int(x.strip()) for x in raw_ids.split(",") if x.strip()]
    else:
        allowed_chat_ids = []

    cf_client_id = _optional("CF_ACCESS_CLIENT_ID")
    cf_client_secret = _optional("CF_ACCESS_CLIENT_SECRET")
    if bool(cf_client_id) != bool(cf_client_secret):
        raise ValueError(
            "CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET must both be set or both be unset."
        )

    return {
        "bot_token": bot_token,
        "api_key": api_key,
        "api_base_url": api_base_url,
        "allowed_chat_ids": allowed_chat_ids,
        "cf_client_id": cf_client_id,
        "cf_client_secret": cf_client_secret,
    }
