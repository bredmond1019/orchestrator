---
type: Decision
title: D16 — Architecture: one deployment-agnostic Python brain, two shells (superseded by D26 as product architecture; retained as engineering discipline)
description: One Python core exposing a clean HTTP API, wrapped by two shells. Superseded by D26 as product architecture; deployment-agnostic discipline retained.
---

# D16 — Architecture: one deployment-agnostic Python brain, two shells *(superseded by D26 as product architecture; retained as engineering discipline)*

**Decided:** Build the Company Brain as one Python core exposing a clean HTTP API. Two shells wrap the same core: SMB Rust appliance + cloud enterprise.
**Why:** Avoids rewrite when scaling; clean layer separation; deployment-agnostic discipline keeps the orchestration core portable.
*Note: D26 supersedes the "two-product-shells" framing. The deployment-agnostic discipline remains good engineering practice.*
