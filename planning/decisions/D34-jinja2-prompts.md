---
type: Decision
title: D34 — No hardcoded prompts — all prompts in .j2 files via PromptManager
description: Every LLM prompt is a Jinja2 template managed by PromptManager; no inline prompt strings in node code.
doc_id: D34-jinja2-prompts
layer: [engine]
project: orchestrator
status: active
keywords: [Jinja2, PromptManager, j2 templates, system prompts, prompt versioning]
related: [prompt-manager, api-reference]
---

# D34 — No hardcoded prompts — all prompts in .j2 files via PromptManager

**Decided:** Every LLM prompt is a Jinja2 template managed by `PromptManager`. No inline prompt strings in node code.
**Why:** Prompts iterate constantly. Separating them from code allows prompt tuning without touching logic and enables version control of prompt changes independently.
**Rejected:** Inline f-string prompts — they mix prompt authoring with Python logic, making it impossible to tune prompts without touching (and re-testing) node code.

*Originated in brain D8. Moved to orchestrator 2026-06-22 — PromptManager is orchestrator-specific infrastructure.*
