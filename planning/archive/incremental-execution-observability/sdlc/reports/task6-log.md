# Task Log — incremental-execution-observability task 6

**Spec:** incremental-execution-observability
**Task:** 6
**Verdict:** PASS
**Date:** 2026-06-20
**Branch:** incremental-execution-observability-task6
**Applied:** true

---

## status.md — Current Focus Line
incremental-execution-observability — Task 7: Workflow graph introspection endpoint (Phase 3)

## status.md — Last Updated Line
2026-06-20 — incremental-execution-observability in progress (Tasks 1–6 complete; Task 7 next — workflow graph introspection endpoint)

## status.md — Notes Column
Tasks 1–6 done (status/timing envelope, framework stamping, on_progress callback, worker persistence, Phase 1 tests, per-node token/cost capture); Task 7 (graph endpoint) next

---

## Log Entry

## 2026-06-20 (task 6 — per-node token + cost capture)

Implemented Phase 2 of the incremental execution observability spec: per-node token and cost capture in the framework-owned `AgentNode` and `ToolUseNode` base classes. A `usage: dict | None` field was added to `NodeRun` in `app/core/task.py`, and both `app/core/nodes/agent.py` and `app/core/nodes/tool_use.py` were updated to populate `NodeRun.usage` with `{input_tokens, output_tokens, model}` from the provider response after each LLM call. Non-LLM nodes leave `usage` as `None`. Tests assert that a stubbed provider response yields the expected token counts on the `NodeRun`, and that non-LLM nodes record no usage. The review passed on the first attempt with all validation commands green. Next: Task 7 — Workflow graph introspection endpoint (Phase 3).

```
aa833a0 docs: update docs for incremental-execution-observability-task6
31ec381 feat: implement incremental-execution-observability-task6
939b0fe chore: init worktree incremental-execution-observability-task6
```
