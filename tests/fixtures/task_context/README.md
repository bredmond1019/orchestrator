# `task_context` fixture — provenance

`research_agent_task_context.json` is a **real, code-path-captured** `TaskContext` — the output of
an actual `ResearchAgentWorkflow` run, dumped via `TaskContext.model_dump(mode="json")`, the same
call the Celery worker uses to persist `events.task_context` (`app/worker/tasks.py`). It is not
hand-authored.

> **Why this exists.** `engine-rs/crates/engine-contract/tests/round_trip.rs` claims byte-for-byte
> conformance with this repo's data contract (`docs/data-contract.md`), but the fixture it asserted
> against (`python_task_context.json`) was written by the Rust side about itself during EN.0.B —
> hand-typed UUID, round-number timestamps, and a `ticket_id`/`title` naming EN.0.B itself. Nothing
> verified engine-rs actually matched Python, and this repo had no test asserting its own contract
> shape either. Structurally identical to the `claude-code-rs` CLI schema drift fixed 2026-07-16 (see
> that repo's `planning/decisions/D2-cli-schema-provenance.md`) — a consumer-authored fixture is a
> tautology, not evidence. See `planning/task-context-fixture/notes.md` for the full finding.

## What's here

| File | Captured from | Notes |
|---|---|---|
| `research_agent_task_context.json` | `ResearchAgentWorkflow`, single `CompanyResearchNode` run | Anthropic client + `PromptManager.get_prompt` mocked; no DB/Celery involved |

This repo owns the fixture (D20's owner-owns-it pattern). `engine-rs` keeps a checked-in copy at
`crates/engine-contract/tests/fixtures/research_agent_task_context.json` so it stays
standalone-clonable; `engine-rs`'s `round_trip.rs` fails loudly if its copy diverges from a copy of
this file placed alongside it (see that repo's fixture README for the divergence check).

## What was redacted, and why

Per the D2 precedent — **redact only what would churn on every re-emission, never a value that
describes shape**:

- `event.artifact_id` / `event.timestamp` — the emission script passes fixed literals instead of
  `ResearchAgentEventSchema`'s `uuid4()`/`datetime.now()` defaults, so these need no post-hoc
  redaction at all.
- `node_runs.*.started_at` / `node_runs.*.completed_at` — stamped by `Workflow.node_context` via
  `datetime.now(UTC)`; redacted to the fixed sentinel `2026-07-16T00:00:00Z` so the file is
  identical on every re-run. (`Z`, not `+00:00` — engine-rs's `chrono` normalizes UTC-offset-zero
  timestamps to `Z` on re-serialization; matching that here avoids a false-positive drift signal
  on a value that is synthetic to begin with.)

**Nothing else is redacted.** `usage` (`input_tokens`/`output_tokens`/`model`), `status`, `input`,
and every node output field are left exactly as the workflow produced them — those are the values a
conformance test needs to assert against, not noise to scrub.

## How to re-emit

```bash
uv run python scripts/emit_task_context_fixture.py
```

The script is deterministic (fixed event literals + mocked Anthropic responses), so re-running it
produces a byte-identical file unless the workflow's actual output shape changed. If the diff is
non-empty, that's real drift — the Python-side conformance test
(`tests/services/test_task_context_fixture.py`) exists to catch it here, and `engine-rs`'s
`round_trip.rs` exists to catch it there. Update both copies together; do not let them diverge
silently.
