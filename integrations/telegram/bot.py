"""Telegram long-poll bot — fire-and-forget CONTENT_PIPELINE dispatcher.

Entry point: run this file directly (``python -m integrations.telegram.bot``)
or via the ``telegram_bot`` Docker Compose service.

Supported commands:
    /digest <url>   — Submit the given URL as a CONTENT_PIPELINE event and
                      reply "Queued ✅".

Bare URL messages are also accepted as shorthand for ``/digest``.

Extending:
    To add new commands (e.g. ``/research``, ``/proposal``), define a new
    async handler function and register it with ``application.add_handler``
    in ``_build_application``.

Security:
    The chat-id allowlist (``TELEGRAM_ALLOWED_CHAT_IDS``) is enforced via
    a pre-handler filter.  Messages from unlisted chats are silently ignored.

Transport:
    # TODO(scale): switch to webhook transport for production deployments
    # that need lower latency or must run behind a reverse proxy without
    # outbound polling overhead.  See python-telegram-bot's
    # ``Updater.start_webhook`` / ``Application.run_webhook`` API.
"""

import logging
import re

import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from integrations.telegram.client import submit_event
from integrations.telegram.config import load_config

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)

_WORKFLOW_TYPE = "CONTENT_PIPELINE"


def _is_valid_url(text: str) -> bool:
    """Return True if *text* looks like an http/https URL."""
    return bool(_URL_RE.match(text.strip()))


def _build_allowlist_filter(allowed_chat_ids: list[int]):
    """Return a telegram ``filters.BaseFilter`` that permits listed chat IDs.

    When *allowed_chat_ids* is empty every chat is permitted (useful for
    local development but not recommended for production).
    """
    if not allowed_chat_ids:
        return filters.ALL

    class _AllowlistFilter(filters.BaseFilter):
        def filter(self, message) -> bool:
            return message.chat_id in allowed_chat_ids

    return _AllowlistFilter()


async def _handle_digest(update: Update, context: ContextTypes.DEFAULT_TYPE, cfg: dict) -> None:
    """Handle the ``/digest <url>`` command."""
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /digest <url>")
        return

    url = args[0]
    if not _is_valid_url(url):
        await update.message.reply_text("Please provide a valid http/https URL.")
        return

    await _submit_and_reply(update, url, cfg)


async def _handle_url_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE, cfg: dict
) -> None:
    """Handle a bare URL message as a shorthand for ``/digest``."""
    text = (update.message.text or "").strip()
    if not _is_valid_url(text):
        await update.message.reply_text("Please send a valid http/https URL.")
        return

    await _submit_and_reply(update, text, cfg)


async def _submit_and_reply(update: Update, url: str, cfg: dict) -> None:
    """Submit a CONTENT_PIPELINE event for *url* and reply to the user."""
    data = {"url": url, "make_blog": False}
    try:
        result = submit_event(
            _WORKFLOW_TYPE,
            data,
            api_base_url=cfg["api_base_url"],
            api_key=cfg["api_key"],
            cf_client_id=cfg.get("cf_client_id", ""),
            cf_client_secret=cfg.get("cf_client_secret", ""),
        )
        task_id = result.get("task_id", "")
        reply = "Queued ✅"
        if task_id:
            reply += f" (task_id: {task_id})"
        await update.message.reply_text(reply)
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        logger.error("Failed to submit event for url=%s: %s", url, exc)
        await update.message.reply_text("Failed to queue the request. Please try again later.")


def _build_application(cfg: dict) -> Application:
    """Construct and return the configured ``Application`` instance.

    Args:
        cfg: Validated config dict from ``load_config()``.

    Returns:
        Application: Ready-to-run telegram bot application.
    """
    application = Application.builder().token(cfg["bot_token"]).build()

    allowlist_filter = _build_allowlist_filter(cfg["allowed_chat_ids"])

    async def digest_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await _handle_digest(update, context, cfg)

    async def url_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await _handle_url_message(update, context, cfg)

    application.add_handler(
        CommandHandler("digest", digest_handler, filters=allowlist_filter)
    )
    application.add_handler(
        MessageHandler(filters.TEXT & filters.Regex(_URL_RE) & allowlist_filter, url_handler)
    )

    return application


def main() -> None:
    """Load config and start the long-poll loop."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = load_config()
    application = _build_application(cfg)
    logger.info("Starting Telegram bot (long-poll mode)")
    # TODO(scale): switch to webhook transport for production deployments.
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
