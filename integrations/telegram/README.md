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

## How the bot reaches the API

The bot uses Telegram's **long-poll** transport — it makes outbound HTTPS requests to
Telegram's servers asking "any new messages?" roughly every second.  No inbound port is
opened on the Mac Mini, and no TLS certificate is needed on your end.

Your phone's message path is:

```
Phone → Telegram servers → bot's long-poll on Mac Mini → POST /events/ on localhost
```

The bot never exposes an inbound port, so it always connects to the API as
`http://localhost:8080` (or `http://api:8080` in Docker Compose) regardless of how the
API is exposed to the outside world.  The two concerns — "how does my phone reach the bot"
and "how does a browser / other tool reach the API directly" — are independent.

---

## Running locally (dev)

```bash
# Install the optional telegram extra
uv sync --extra telegram

# Set required env vars
export TELEGRAM_BOT_TOKEN=<your-token>
export ORCHESTRATION_API_KEY=<your-key>
export ORCHESTRATION_API_BASE_URL=http://localhost:8080

# Start the bot (Ctrl-C to stop)
python -m integrations.telegram.bot
```

## Running via Docker Compose (recommended for Mac Mini)

The `telegram_bot` service in `docker/docker-compose.ai-event-system.yml` starts with the
full stack.  It connects to the API over the internal Compose network (`http://api:8080`)
so CF Access headers are not needed.

```bash
# 1. Fill in docker/.env (copy from docker/.env.example)
#    Required: TELEGRAM_BOT_TOKEN, ORCHESTRATION_API_KEY
#    Optional: TELEGRAM_ALLOWED_CHAT_IDS

# 2. Start the full stack (API + Celery + Postgres + Redis + bot)
cd docker && ./start.sh

# Confirm the bot is running
docker logs <PROJECT_NAME>_telegram_bot --tail 20
```

The service has `restart: unless-stopped` so it survives Docker daemon restarts and Mac
reboots (assuming Docker Desktop is set to launch at login).

## Running as a launchd service (non-Docker Mac Mini)

If you prefer not to run the full Docker stack, you can run the bot as a lightweight
launchd agent alongside a locally-installed API.

Create `~/Library/LaunchAgents/com.brandon.orchestration-telegram-bot.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.brandon.orchestration-telegram-bot</string>
  <key>ProgramArguments</key>
  <array>
    <string>/path/to/repo/.venv/bin/python</string>
    <string>-m</string>
    <string>integrations.telegram.bot</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/path/to/repo</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>TELEGRAM_BOT_TOKEN</key>   <string>YOUR_TOKEN</string>
    <key>ORCHESTRATION_API_KEY</key> <string>YOUR_KEY</string>
    <key>ORCHESTRATION_API_BASE_URL</key> <string>http://localhost:8080</string>
    <key>TELEGRAM_ALLOWED_CHAT_IDS</key> <string>YOUR_CHAT_ID</string>
  </dict>
  <key>RunAtLoad</key>       <true/>
  <key>KeepAlive</key>       <true/>
  <key>StandardOutPath</key> <string>/tmp/telegram-bot.log</string>
  <key>StandardErrorPath</key><string>/tmp/telegram-bot.err</string>
</dict>
</plist>
```

Load it:

```bash
launchctl load ~/Library/LaunchAgents/com.brandon.orchestration-telegram-bot.plist
launchctl start com.brandon.orchestration-telegram-bot

# Check logs
tail -f /tmp/telegram-bot.log
```

---

## First-time setup: get your bot token and chat ID

**1. Create the bot (@BotFather)**

```
1. Open Telegram and search for @BotFather
2. /newbot → pick a name and username (e.g. mydigest_bot)
3. Copy the token — this is TELEGRAM_BOT_TOKEN
```

**2. Find your chat ID (needed for the allowlist)**

Start a conversation with the bot (send it any message), then call:

```bash
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates"
# Look for "chat":{"id": <NUMBER>} in the response
```

Set `TELEGRAM_ALLOWED_CHAT_IDS=<NUMBER>` to lock the bot to your account only.

---

## Accessing the API directly from other devices

The bot always connects to the API via localhost, so the network scenarios below only
matter if you want to call the API directly from another device (e.g., `curl` from your
MacBook, or the `bastion` CLI).

### Scenario A — Cloudflare Tunnel (public, already set up)

The API is published at `api.learn-agentic-ai.com` via `cloudflared`.  Access is gated by
Cloudflare Access (edge) + `X-API-Key` (in-app).

```bash
# From any device, anywhere
curl -X POST https://api.learn-agentic-ai.com/events/ \
  -H 'X-API-Key: <key>' \
  -H 'Content-Type: application/json' \
  -d '{"workflow_type": "CONTENT_PIPELINE", "data": {"url": "https://...", "make_blog": false}}'
```

Manual steps still required on the Mac Mini (not done yet — see brain repo
`docs/infrastructure.md`):
- Add an ingress rule in `~/.cloudflared/config.yml` for `api.learn-agentic-ai.com → localhost:8080`
- Create a Cloudflare Access application + service token for the bot
- `cloudflared` tunnel restart

### Scenario B — Tailscale private access

Lets devices on your tailnet (MacBook, phone, tablet) hit the API without exposing it
publicly.  The API stays inside your tailnet; only authenticated tailnet devices can reach it.

**Current limitation:** the Docker Compose port binding is `127.0.0.1:8080:8080` (loopback
only), so the API is not reachable from other tailnet devices by default.

To enable Tailscale access, change the port binding in
`docker/docker-compose.ai-event-system.yml` from:

```yaml
ports:
  - "127.0.0.1:8080:8080"
```

to:

```yaml
ports:
  - "0.0.0.0:8080:8080"   # reachable from tailnet; still protected by X-API-Key
```

Then restart the stack (`./stop.sh && ./start.sh`) and call from any tailnet device:

```bash
curl -X POST http://brandons-mac-mini:8080/events/ \
  -H 'X-API-Key: <key>' \
  -H 'Content-Type: application/json' \
  -d '{"workflow_type": "CONTENT_PIPELINE", "data": {"url": "https://...", "make_blog": false}}'
```

Use the MagicDNS hostname (`brandons-mac-mini`) or the Tailscale IP
(`100.104.113.100`).  No CF Access headers needed — Tailscale handles network-layer auth.

**Security note:** opening `0.0.0.0` binds to all interfaces on the Mini, not just the
Tailscale interface.  If you want to bind *only* to Tailscale, use the Mini's Tailscale IP
instead: `100.104.113.100:8080:8080`.  The `X-API-Key` check remains as defense-in-depth
at the application layer regardless.

### Scenario C — Same machine (bot use case, no change needed)

The Telegram bot always runs on the Mac Mini alongside the API, so `http://localhost:8080`
works regardless of the network scenario above.  No port binding change is needed for the
bot to function.

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
