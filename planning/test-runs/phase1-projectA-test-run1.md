# Phase 1 — Project A (content_pipeline) — Test Run 1

**Date:** 2026-06-22
**Goal:** First end-to-end run of the `content_pipeline` workflow against a **real
LLM** through the newly-landed `CLAUDE_CODE_SDK` provider, with step-by-step
observability captured here.

## Configuration

| Setting | Value |
|---|---|
| Input URL | `https://www.youtube.com/watch?v=DzbqeO_diOQ` |
| Run mode | Digest-only (`make_blog=false`) |
| LLM provider | `CLAUDE_CODE_SDK` (subscription-billed, via `claude-agent-sdk`) |
| Model | `sonnet` (CLI alias) |
| Workflow type | `CONTENT_PIPELINE` |
| Expected path | `SourceRouterNode → FetchTranscriptNode → SummarizerNode → StorageNode → BlogDecisionRouterNode` (ends; blog branch gated off) |
| Only LLM node exercised | `SummarizerNode` |

## Pre-flight (all green)

- `VOYAGE_API_KEY` resolves from root `.env.local` (len 46, `pa-` prefix) — exported into the worker env at launch (the app only `load_dotenv()`s `app/.env`, which has an empty placeholder; `EmbeddingService` requires `os.environ["VOYAGE_API_KEY"]`).
- `claude` CLI authenticated; headless `sonnet` smoke test returned `OK`.
- Alembic at head (`cc3ad971094e`) — `learning_artifacts` table + pgvector extension present.

## Code change for this run

Switched the 5 content_pipeline LLM nodes (`summarizer`, `blog_writer`,
`self_critic`, `revise`, `translate_ptbr`) `get_agent_config()` from
`ModelProvider.ANTHROPIC` / `claude-opus-4-8` → `ModelProvider.CLAUDE_CODE_SDK` /
`sonnet`. (Per decision: this is the new default; revert to `ANTHROPIC` manually
when needed.)

---

## Live node timeline

### Attempt 1 (event `4971c495…`) — FAILED at StorageNode, but validated the SDK path

| Node | Start | End | Duration | Result |
|---|---|---|---|---|
| SourceRouterNode | 11:32:32.534 | 11:32:32.535 | ~0s | routed → YouTube |
| FetchTranscriptNode | 11:32:32.536 | 11:32:33.651 | ~1.1s | transcript fetched (video has captions) |
| **SummarizerNode** | 11:32:33.664 | 11:33:49.389 | **~76s** | **✅ Claude SDK (sonnet) structured call succeeded** |
| StorageNode | 11:33:49.403 | 11:33:49.740 | ~0.3s | ❌ `DetachedInstanceError` (Voyage embed succeeded first) |

**What this already validated:** the `CLAUDE_CODE_SDK` provider drove a real
Sonnet call through pydantic-ai and returned a schema-valid `SummaryOutput` (no
error on the Summarizer boundary), and the `VOYAGE_API_KEY` wiring worked (the
embedding ran before the failure).

**Bug found (real, in `StorageNode`):**
`DetachedInstanceError: Instance <LearningArtifact …> is not bound to a Session`.
Cause: `_persist()` commits and closes its session inside a `with` block;
SQLAlchemy's default `expire_on_commit=True` then expires the instance, so the
subsequent `str(artifact.id)` access in `process()` (digest render + node output)
triggers an attribute refresh on a detached instance and raises. The existing
StorageNode tests monkeypatch `_persist`, so this real-session path was never
exercised — a true test gap a live run caught.

**Fix applied:** capture `artifact_id = task_context.event.artifact_id` (already
the source of the row's PK) into a local before `_persist`, and use that local for
the digest render and node output instead of touching the detached ORM
attribute. No change to the persistence seam / session semantics.

### Attempt 2 (event `9a1cb478-6e47-11f1-bd68-3642e9db01ce`) — ✅ full green end-to-end

| Node | Start (UTC) | End (UTC) | Duration | Result |
|---|---|---|---|---|
| SourceRouterNode | 14:35:23.297 | 14:35:23.298 | ~0s | success — routed → YouTube |
| FetchTranscriptNode | 14:35:23.299 | 14:35:24.546 | ~1.25s | success — transcript fetched (`fetch_status=ok`) |
| **SummarizerNode** | 14:35:24.558 | 14:36:43.193 | **~78.6s** | success — **Claude SDK (sonnet) structured `SummaryOutput`** |
| StorageNode | 14:36:43.211 | 14:36:43.535 | ~0.32s | success — embed (Voyage 1024-dim) + persist + digest HTML |
| BlogDecisionRouterNode | 14:36:43.547 | 14:36:43.548 | ~0s | success — `make_blog=false` → ends (blog branch gated off) |
| BlogWriter / SelfCritic / Revise / TranslatePtBr | — | — | — | `pending` (correctly never ran) |

Celery: `Task process_incoming_event[043b97e6…] succeeded in 80.31s`.

## Final per-node envelope

Read back from the committed `events.task_context` via `scripts/inspect_run.py`.

- **Graph:** 10 nodes seeded `pending` up-front; 6 ran (5 on the digest path + the
  router), 4 blog-branch nodes stayed `pending` — the observability layer shows the
  full DAG topology *and* which branch executed.
- **SummarizerNode usage:** `input_tokens=4, output_tokens=3156, model=sonnet`.
  - `model=sonnet` + a populated `output_tokens` is the proof the LLM ran through
    `CLAUDE_CODE_SDK` (not a mock).
  - ⚠️ **`input_tokens=4` is wrong as a prompt-size signal** — the `NodeRun.input`
    field captured the *full* (large) transcript, but the Claude Code SDK's
    `ResultMessage.usage` reports the bulk of prompt tokens as cache reads, not
    `input_tokens`. Token accounting via the SDK is partial vs. the raw Anthropic
    API. (Observability caveat, not a run failure.)
- **Structured output:** `SummaryOutput` came back fully populated and accurate for
  the actual video ("Plan F3" planning meta-skill dev vlog) — title, category
  (`ai_engineering`), tl_dr, 11 core_concepts, 8 key_insights, questions_raised,
  connections_to_my_work, further_exploration. Structured JSON-schema output
  round-tripped cleanly through the SDK → pydantic-ai → `SummaryOutput`.
- **Persistence:** `LearningArtifact` row `98683735-43c3-4fba-a1fe-242e6f5bab5f` —
  `source_type=youtube`, `fetch_status=ok`, `make_blog=False`, **1024-dim embedding**.
- **Digest:** `app/_digest/ai_engineering/98683735-….html` (artifact page) +
  `app/_digest/ai_engineering/index.html` (category index) written.

## Verdict

**PASS (after one fix).** The `content_pipeline` workflow ran end-to-end against a
real Sonnet model through the new `CLAUDE_CODE_SDK` provider, with full
step-by-step observability captured here.

**What this run proved:**
1. `CLAUDE_CODE_SDK` works in a live workflow — subscription-billed Sonnet,
   structured output, ~79s for a long transcript.
2. The observability layer is genuinely useful: per-node status/timing, the captured
   prompt, token usage, model, and the executed-vs-pending branch are all readable
   from `events.task_context`.
3. The Voyage embedding path and digest rendering work with a real key.

**Issues found:**
1. **`StorageNode` `DetachedInstanceError` (fixed this run).** Post-commit ORM
   attribute access; fixed by reading the id from the event before persisting.
   Root cause it slipped through: the StorageNode tests monkeypatch `_persist`, so
   the real session/commit/expire path had no coverage.

**Recommended follow-ups (not done here):**
- Add a `StorageNode` regression test that exercises `process()` with a real (or
  fake-but-session-bound) repository so the detach path can't regress. (Honors the
  "every workflow ships with tests" rule for the gap this exposed.)
- Decide how to surface true prompt-token counts for the Claude Code SDK provider
  (e.g. fold `cache_read_input_tokens`/`cache_creation_input_tokens` into the
  recorded usage) so `NodeRun.usage` is meaningful for SDK-backed nodes.
- `nodes["SummarizerNode"]` carries the summary under both `output` and `result`
  (AgentNode records `output`; the node also writes `result`). Harmless duplication;
  worth a cleanup pass if it bothers consumers.
