---
type: Decision
title: "D12 — Repo strategy: one Python monorepo; separate repos only for different languages/deployables"
description: The Python framework and all Python workflows live in one monorepo; separate repos only for different languages/deploy lifecycles.
doc_id: D12-repo-strategy-monorepo
layer: [engine, meta]
project: orchestrator
status: active
keywords: [monorepo, repo strategy, Python framework, workflow directories, language boundary]
related: [master-plan]
---

# D12 — Repo strategy: one Python monorepo; separate repos only for different languages/deployables

**Decided:** The Python framework and all Python workflows (Projects A–H) live in **one monorepo** — every project is a workflow directory (workflow + nodes + prompts + tests) added alongside the existing ones, not a clone. Separate repos only for genuinely different languages/deploy lifecycles: the Rust CLI, the website.
**Why:** The architecture is "framework as scaffold, projects as attached workflows," with heavy verbatim component reuse across projects. Clone-per-project would fragment the framework into divergent copies with no clean way to propagate fixes. Test for "new repo?": *does it share the Python framework's code/dependency tree?* If yes, same repo.
**Rejected:** Cloning the orchestration repo per project — optimizes for unwanted isolation at the cost of the reuse that is the whole design.
