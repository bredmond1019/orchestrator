---
type: Guide
title: Telegram Bot Integration
description: Run/deploy/extend instructions for the long-poll Telegram bot that submits CONTENT_PIPELINE events.
---

# Telegram Bot Integration

Long-poll, fire-and-forget Telegram bot that dispatches `CONTENT_PIPELINE` events to the
orchestration API.  Send the bot a URL (via `/digest <url>` or as a bare message) and it
queues the job and replies "Queued ✅".  It never polls for a result.

## Required environment variables

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | Bot token from @BotFather |
| `ORCHESTRATION_API_KEY` | yes | Shared secret for `X-API-Key` auth |
| `ORCHESTRATION_API_BASE_URL` | no | API base URL (default: `http://localhost:8080`) |
| `TELEGRAM_ALLOWED_CHAT_IDS` | no | Comma-separated chat IDs to accept (empty = allow all) |
| `CF_ACCESS_CLIENT_ID` | no | Cloudflare Access service-token client ID |
| `CF_ACCESS_CLIENT_SECRET` | no | Cloudflare Access service-token secret |

Both `CF_ACCESS_*` variables must be set together or both left unset.

## Running locally

```bash
# Install the optional telegram extra
uv sync --extra telegram

# Set required env vars
export TELEGRAM_BOT_TOKEN=<your-token>
export ORCHESTRATION_API_KEY=<your-key>
export ORCHESTRATION_API_BASE_URL=http://localhost:8080

# Start the bot
python -m integrations.telegram.bot
```

## Running via Docker Compose

The `telegram_bot` service in `docker/docker-compose.ai-event-system.yml` runs the bot
automatically.  Set the env vars in `docker/.env` (see `docker/.env.example`).

```bash
cd docker && ./start.sh
```

## Extending with new commands

1. Define a new async handler function in `bot.py`:
   ```python
   async def _handle_research(update: Update, context: ContextTypes.DEFAULT_TYPE, cfg: dict) -> None:
       ...
   ```
2. Register it with `application.add_handler` inside `_build_application`:
   ```python
   application.add_handler(CommandHandler("research", research_handler, filters=allowlist_filter))
   ```

## Long-poll to webhook migration

The bot currently uses Telegram's long-poll transport (`run_polling`), which is the simplest
deployment model and requires no inbound port or TLS certificate.

For production deployments that need lower latency or webhook-based triggering, switch to
`application.run_webhook`.  The `# TODO(scale)` comment in `bot.py` marks the run loop.
See the python-telegram-bot docs:
https://docs.python-telegram-bot.org/en/stable/telegram.ext.application.html#telegram.ext.Application.run_webhook
