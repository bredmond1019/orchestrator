---
type: Decision
title: "D24 — Firecrawl role: trafilatura-first for single articles, Firecrawl-fallback for JS/paywall, CrawlSiteNode for site ingestion; free tier until a real crawl demands upgrade"
description: ArticleExtractionService uses trafilatura as default with Firecrawl as fallback; Firecrawl /crawl powers a CrawlSiteNode; free tier until a real crawl demands upgrade.
doc_id: D24-firecrawl-role
layer: [engine]
project: orchestrator
status: active
keywords: [Firecrawl, trafilatura, article extraction, CrawlSiteNode, web scraping]
related: [master-plan, D21-project-a-knowledge-feed]
---

# D24 — Firecrawl role: trafilatura-first for single articles, Firecrawl-fallback for JS/paywall, CrawlSiteNode for site ingestion; free tier until a real crawl demands upgrade

**Decided:** `ArticleExtractionService` uses trafilatura as default, Firecrawl as fallback. Firecrawl's `/crawl` endpoint powers a `CrawlSiteNode` for multi-page site ingestion. Free tier (500 credits/month) until a real crawl demands upgrade. Add `max_calls` guard when Firecrawl runs inside an agent tool loop.
**Why:** trafilatura handles most personal feed extraction for free. Firecrawl earns its place for JS-rendered pages, systematic crawling, and MCP-native access.
**Rejected:** Replacing trafilatura entirely with Firecrawl; self-hosting Firecrawl; skipping the `max_calls` guard.
