---
type: Decision
title: D23 — Mac Mini two-face architecture: Caddy+Cloudflare for public, Tailscale for private
description: Two architecturally separate networking paths — public face (Caddy + Cloudflare DNS) and private face (Tailscale, no open ports).
---

# D23 — Mac Mini two-face architecture: Caddy+Cloudflare for public, Tailscale for private

**Decided:** Two architecturally separate networking paths. Public face (Caddy + Cloudflare DNS): `learn-agentic-ai.com` accessible to anyone. Private face (Tailscale): all private tooling, no open ports, your devices only.
**Why:** Tailscale cannot make a public website accessible to strangers — it's a private mesh by design. Each concern gets the right tool.
**Rejected:** Routing the public site through Tailscale; Tailscale Funnel for the public site; a unified public setup for everything.
