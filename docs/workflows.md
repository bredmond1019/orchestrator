---
type: Guide
title: Workflow Catalog
description: What each workflow does, its node DAG, how to trigger it, and example payloads.
doc_id: workflows
layer: [engine]
project: orchestrator
status: active
keywords: [workflow catalog, CONTENT_PIPELINE, DOCUMENT_QA, SDLC_FLOW, PRICE_SCOUT, MEMORY_INGEST, MEMORY_CONSOLIDATION, event payload, curl]
related: [api-reference, app-architecture-overview, data-contract, sdlc-flow-workflow, memory]
---

# Workflow Catalog

Eight production workflows ship with the framework. All are triggered by posting to `POST /events/` with a `workflow_type` and a `data` payload. The API persists the event and queues it for async processing — you get a 202 and a `task_id` immediately.

**All requests require the `X-API-Key` header:**

```bash
-H 'X-API-Key: <your ORCHESTRATION_API_KEY>'
```

---

## 1. Content Pipeline (`CONTENT_PIPELINE`)

**What it does:** Takes a YouTube or article URL, fetches and summarizes the content, embeds it, persists it as a `LearningArtifact`, and renders a static HTML digest. Optionally generates a self-corrected blog post in English + PT-BR.

**When to use:** Whenever you want to add a piece of content to your personal knowledge feed — a YouTube talk, a blog post, a technical article.

**Node DAG:**

```
SourceRouterNode
  ├── FetchTranscriptNode (YouTube)  →  SummarizerNode
  └── FetchArticleNode   (article)  →  SummarizerNode
                                         │
                                      StorageNode (embed + persist + render digest)
                                         │
                                   BlogDecisionRouterNode
                                         │ (only if make_blog=true)
                                      BlogWriterNode
                                         │
                                      SelfCriticNode
                                         │
                                      ReviseNode
                                         │
                                      TranslatePtBrNode (pt-BR translation)
```

If `make_blog` is `false`, the run ends after `StorageNode` — digest only, no LLM blog generation.

**Event payload:**

```json
{
  "workflow_type": "CONTENT_PIPELINE",
  "data": {
    "url": "https://www.youtube.com/watch?v=...",
    "make_blog": false
  }
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `url` | string | yes | YouTube URL or any article URL |
| `make_blog` | bool | no (default: false) | Set true to generate a blog post |
| `artifact_id` | UUID | no | Auto-generated if omitted |
| `timestamp` | datetime | no | Auto-generated if omitted |

**Trigger:**

```bash
# Digest only
curl -X POST http://localhost:8080/events/ \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-secret' \
  -d '{"workflow_type": "CONTENT_PIPELINE", "data": {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "make_blog": false}}'

# With blog post
curl -X POST http://localhost:8080/events/ \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-secret' \
  -d '{"workflow_type": "CONTENT_PIPELINE", "data": {"url": "https://example.com/some-article", "make_blog": true}}'
```

**What gets stored:** A `LearningArtifact` row with title, summary, category, embedding vector, and optional blog text. Inspect with `scripts/inspect_run.py`.

---

## 2. Research Agent (`RESEARCH_AGENT`)

**What it does:** Takes a company name, runs a Tavily web search loop via the raw Anthropic tool-use API, and returns a structured research brief: what they do, where they bleed time, one automation hypothesis.

**When to use:** Pre-sales research before a client conversation. The thin-cut version — one node, no storage. The hardened multi-node version (with planner → research → critic → revise → BrainDocument write) is deferred for when a real prospect demands depth.

**Node DAG:**

```
CompanyResearchNode (terminal — single node)
```

**Event payload:**

```json
{
  "workflow_type": "RESEARCH_AGENT",
  "data": {
    "company_name": "Acme Corp"
  }
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `company_name` | string | yes | Name to research |
| `artifact_id` | UUID | no | Auto-generated |
| `timestamp` | datetime | no | Auto-generated |

**Trigger:**

```bash
curl -X POST http://localhost:8080/events/ \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-secret' \
  -d '{"workflow_type": "RESEARCH_AGENT", "data": {"company_name": "Notion"}}'
```

**Output shape (`ResearchBriefOutput`):**
- `company_name`
- `what_they_do` — short description
- `likely_time_sinks` — list of processes where they bleed time
- `automation_hypothesis` — one concrete ROI hypothesis

---

## 3. Proposal Generator (`PROPOSAL_GENERATOR`)

**What it does:** Takes client context (company, industry, description), runs the research agent tool loop, scores automation opportunities using a binding composite formula, writes a bilingual (PT/EN) diagnostic roadmap, self-reviews it, and persists the result.

**When to use:** After a discovery conversation, to generate a first draft of an automation proposal for a client. The scoring formula ensures consistency: `composite = (frequency × 0.35) + (time_cost × 0.40) + (buildability × 0.25)`.

**Node DAG:**

```
ProposalCompanyResearchNode
  └── OpportunityIdentifierNode (scores 3 candidates, picks one)
        └── ProposalWriterNode (writes PT/EN roadmap)
              └── ProposalReviewNode (validates against 5 Diagnostic criteria)
                    └── ProposalReviewRouterNode
                          ├── StorageNode (PASS branch)
                          └── ProposalReviseNode → StorageNode (REVISE branch)
```

**Event payload:**

```json
{
  "workflow_type": "PROPOSAL_GENERATOR",
  "data": {
    "company_name": "Acme Corp",
    "industry": "Healthcare",
    "description": "30-person clinic managing scheduling and billing manually",
    "language": "PT"
  }
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `company_name` | string | yes | Client company name |
| `industry` | string | yes | Industry / sector |
| `description` | string | yes | Brief context about the business |
| `language` | `"PT"` or `"EN"` | no (default: `"PT"`) | Output language |
| `intake_notes` | string | no | Raw diagnostic intake notes to enrich research |

**Trigger:**

```bash
curl -X POST http://localhost:8080/events/ \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-secret' \
  -d '{
    "workflow_type": "PROPOSAL_GENERATOR",
    "data": {
      "company_name": "Acme Clinic",
      "industry": "Healthcare",
      "description": "25-person private clinic in São Paulo, scheduling via phone and paper",
      "language": "PT"
    }
  }'
```

**Output shape (`AutomationRoadmap`):**
- `situation_summary`
- `candidates` — list of `ScoredCandidate` sorted by composite score
- `top_profiles` — up to 3 detailed workflow profiles
- `recommended_workflow`, `engagement_scope`, `price_range_brl`
- `body_pt` / `body_en` — full prose roadmap

---

## 4. Document Ingest (`DOCUMENT_INGEST`)

**What it does:** Parses a document (plain text or PDF), splits it into section-aware overlapping token chunks, embeds all chunks in a single batched Voyage call, and persists them as `ContentChunk` rows with vectors. Creates the searchable corpus that `DOCUMENT_QA` queries against.

**When to use:** Before you can ask questions about a document, you must ingest it. Run this once per document; the chunks persist in the database.

**Node DAG:**

```
ParseDocumentNode → ChunkDocumentNode → EmbedChunksNode → StoreChunksNode
```

**Event payload:**

```json
{
  "workflow_type": "DOCUMENT_INGEST",
  "data": {
    "title": "My Document",
    "content": "The full text of the document goes here..."
  }
}
```

For a PDF, use `content_b64` (base64-encoded bytes) + `mime_type`:

```json
{
  "workflow_type": "DOCUMENT_INGEST",
  "data": {
    "title": "Annual Report 2024",
    "content_b64": "<base64-encoded PDF bytes>",
    "mime_type": "application/pdf"
  }
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `title` | string | yes | Human-readable document title |
| `content` | string | either/or | Raw text |
| `content_b64` | string | either/or | Base64 PDF bytes |
| `mime_type` | string | no (default: `"text/plain"`) | Only needed with `content_b64` |
| `chunk_size` | int | no (default: 500) | Max tokens per chunk |
| `overlap` | int | no (default: 50) | Token overlap between chunks |
| `doc_id` | UUID | no | Auto-generated; save it to query later |

**Trigger:**

```bash
curl -X POST http://localhost:8080/events/ \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-secret' \
  -d '{
    "workflow_type": "DOCUMENT_INGEST",
    "data": {
      "title": "Test Document",
      "content": "Agentic AI systems combine language models with tools and memory to complete multi-step tasks autonomously. Unlike chatbots, they plan, act, and self-correct."
    }
  }'
```

Note the `doc_id` from the payload (or generate one before sending): you'll need it to query against this document.

---

## 5. Document Q&A (`DOCUMENT_QA`)

**What it does:** Embeds a question, retrieves the most relevant chunks from a previously ingested document via two-stage hybrid retrieval (semantic candidate set → keyword re-rank → score fusion), assembles the RAG context alongside prior session turns, generates a grounded answer, and persists the Q&A turn to the chat session.

**When to use:** After ingesting a document with `DOCUMENT_INGEST`. Pass the same `doc_id` you used when ingesting. Reuse `session_id` across questions to get conversation memory.

**Node DAG:**

```
EmbedQuestionNode → RetrieveChunksNode → AssembleContextNode → AnswerNode → UpdateSessionMemoryNode
```

The retrieval uses hybrid scoring: semantic similarity (Voyage embeddings) combined with a keyword re-rank, with 2× weight on section-title chunks. The `"content"` corpus uses a binary ILIKE keyword match; the `"brain"` corpus uses graded Postgres full-text search (`ts_rank` over a weighted `content_tsv` column) so a term in a doc's title/keywords outranks one in body text.

**Event payload:**

```json
{
  "workflow_type": "DOCUMENT_QA",
  "data": {
    "doc_id": "<uuid of ingested document>",
    "question": "What is an agentic AI system?"
  }
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `doc_id` | UUID | yes | Must match a previously ingested document |
| `question` | string | yes | The user question |
| `session_id` | UUID | no | Auto-generated; pass the same one to maintain conversation history |
| `corpus` | `"content"` or `"brain"` | no (default: `"content"`) | `"brain"` queries the brain_documents corpus |
| `filters` | dict | no | Optional metadata filters for `"brain"` corpus only. Accepted keys: `"layer"` (array overlap), `"project"` (scalar `==`), `"status"` (scalar `==`). Ignored for `"content"` corpus. |
| `include_archived` | bool | no (default: `false`) | `"brain"` corpus only. When `false`, excludes `status='archived'` docs; set `true` for historical queries. No effect on `"content"`. |
| `expand_structural` | bool | no (default: `true`) | `"brain"` corpus only. When `true`, widens retrieval through the `related:`-neighborhood of the top semantic hits (`brain_edges`, OR.G); results added this way are flagged `"via": "structural"`. Set `false` for semantic-only retrieval. No effect on `"content"`. |

**Trigger (two-shot conversation):**

```bash
# First question — let session_id be generated
curl -X POST http://localhost:8080/events/ \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-secret' \
  -d '{
    "workflow_type": "DOCUMENT_QA",
    "data": {
      "doc_id": "<your-doc-id>",
      "question": "What is an agentic AI system?",
      "session_id": "00000000-0000-0000-0000-000000000001"
    }
  }'

# Follow-up — same session_id for memory
curl -X POST http://localhost:8080/events/ \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-secret' \
  -d '{
    "workflow_type": "DOCUMENT_QA",
    "data": {
      "doc_id": "<your-doc-id>",
      "question": "How do they differ from chatbots?",
      "session_id": "00000000-0000-0000-0000-000000000001"
    }
  }'
```

---

## 6. Memory Ingest (`MEMORY_INGEST`)

**What it does:** Fast, per-interaction memory extraction — the first stage of the two-stage block OR.S memory pipeline (Honcho reference architecture, D25). Extracts an episode summary, outcome, tags, and candidate facts from a single interaction via Claude, then writes the episode (upserting the owning `Peer`) and upserts the extracted facts as `SemanticMemory` rows.

**When to use:** Call this once per interaction with a peer (a client, company, product, SOP, or user) to record what happened, in near-real-time. Deep cross-episode reasoning happens later, out of band, via `MEMORY_CONSOLIDATION`.

See [memory.md](memory.md) for the full memory-layer architecture (entities, decay, the never-overwrite contradiction rule).

**Node DAG:**

```
IngestTimeExtractionNode -> MemoryWriteNode
```

`IngestTimeExtractionNode` (`AgentNode`) extracts the structured episode + candidate facts (system prompt from `memory_ingest_extraction.j2`). `MemoryWriteNode` (terminal) writes the `AgentEpisode` and upserts facts into the memory store.

**Event payload:**

```json
{
  "workflow_type": "MEMORY_INGEST",
  "data": {
    "workspace_id": "orchestrator",
    "peer_id": "acme-corp",
    "peer_type": "client",
    "session_id": "00000000-0000-0000-0000-000000000001",
    "interaction": "Called to discuss Q3 renewal; wants a 20% discount for a 2-year term."
  }
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `workspace_id` | string | yes | D47 workspace name (`brain.toml` `[[repos]].slug` format) this interaction is scoped to |
| `peer_id` | string | yes | The entity this interaction concerned — caller-supplied (e.g. a client slug) |
| `peer_type` | string | yes | One of `client`, `company`, `product`, `sop`, `user` |
| `session_id` | string | no | The session/conversation this interaction belongs to, if any |
| `interaction` | string | yes | Raw interaction text (transcript or free-text summary) to extract from |

**Trigger:**

```bash
curl -X POST http://localhost:8080/events/ \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-secret' \
  -d '{
    "workflow_type": "MEMORY_INGEST",
    "data": {
      "workspace_id": "orchestrator",
      "peer_id": "acme-corp",
      "peer_type": "client",
      "interaction": "Called to discuss Q3 renewal; wants a 20% discount for a 2-year term."
    }
  }'
```

---

## 7. Memory Consolidation (`MEMORY_CONSOLIDATION`)

**What it does:** Dream-time consolidation — the second stage of the two-stage block OR.S memory pipeline. Reasons deeply (Claude only, D35 frontier-only rule) across a peer's (or every peer's, in a workspace) recently accumulated episodes and current facts to distill durable `SemanticMemory` rows, resolve contradictions (lower-and-insert, never overwrite/delete), and refresh `Peer.representation`.

**When to use:** Run out of band (nightly batch or on demand) after enough `MEMORY_INGEST` episodes have accumulated for a workspace. Scheduling (Celery beat/cron) is deployment config and out of scope for this workflow — it is only ever event-dispatched, like every other workflow in this repo.

See [memory.md](memory.md) for the full memory-layer architecture.

**Node DAG:**

```
LoadMemoryContextNode -> ConsolidationNode -> ConsolidationWriteNode
```

`LoadMemoryContextNode` loads recent episodes, current facts, and prior representation for every peer in scope. `ConsolidationNode` (`AgentNode`, pinned to `ModelProvider.CLAUDE_CODE_SDK` / `"opus"` per D35) runs the deep per-peer consolidation pass (system prompt from `memory_consolidation.j2`), keyed per `peer_id` so multi-peer runs stay isolated. `ConsolidationWriteNode` (terminal) writes the consolidated facts and refreshes each peer's representation.

**Event payload:**

```json
{
  "workflow_type": "MEMORY_CONSOLIDATION",
  "data": {
    "workspace_id": "orchestrator",
    "peer_id": "acme-corp",
    "since": "2026-07-01T00:00:00Z"
  }
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `workspace_id` | string | yes | D47 workspace name this consolidation pass is scoped to (episodes/peers matched by verbatim string) |
| `peer_id` | string | no | Consolidate only this peer; omit to consolidate every peer in the workspace |
| `since` | datetime | no | Only reason over episodes at/after this timestamp; omit to consider all episodes |

**Trigger:**

```bash
curl -X POST http://localhost:8080/events/ \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-secret' \
  -d '{
    "workflow_type": "MEMORY_CONSOLIDATION",
    "data": {
      "workspace_id": "orchestrator"
    }
  }'
```

---

## 8. SDLC Flow (`SDLC_FLOW`)

**What it does:** Drives a structured spec (`SDLCTask` list persisted as JSON) through a sequential implement → test → triage → review loop, task by task, in one shared git worktree — then patches docs, writes a wrap-up log, and opens a PR. Replaces markdown-based task parsing with the `SDLCState`/`SDLCTask` schema in `app/schemas/sdlc_schema.py`.

**When to use:** To run an `/sdlc-flow`-style spec end to end as an orchestrated workflow rather than a manual slash-command sequence.

**Setup, task-loop mechanics, the state file, resuming, and debugging:** see [sdlc-flow-workflow.md](sdlc-flow-workflow.md) — this section only covers the DAG and the trigger payload.

**Node DAG:**

```
SetupWorktreeNode → LoadTaskStateNode → TaskQueueRouterNode (router)
                                            │ (pending task)      │ (no tasks left)
                                            v                     v
                                      ImplementTaskNode      PatchDocsNode
                                            │                     │
                                            v                     v
                                       TestTaskNode            WrapUpNode
                                            │                     │
                                            v                     v
                                      TriageTaskNode        PullRequestNode
                                            │
                                            v
                                 TriageRouterNode (router)
                                  │ (PASS)      │ (MAJOR_BAIL)
                                  v             v
                       ConsolidatedReviewNode  WrapUpNode
                                  │
                                  v
                        ReviewRouterNode (router)
                        │ (PASS)      │ (structural FAIL)
                        v             v
              UpdateTaskStatusNode   WrapUpNode
                        │
                        v
                  SaveStateNode
                        │
                        v (loops back for the next pending task)
                TaskQueueRouterNode
```

`TriageRouterNode` also routes `RETRYABLE` back to `ImplementTaskNode`, and `ReviewRouterNode` also routes minor `FAIL`/`PARTIAL` back to `ImplementTaskNode` — both are runtime-only routing decisions (not declared `NodeConfig.connections` edges), so the declared graph stays acyclic for `WorkflowValidator` while the actual execution graph loops. See the module docstring in `app/workflows/sdlc_flow_workflow.py` for the full reasoning.

**Event payload:**

```json
{
  "workflow_type": "SDLC_FLOW",
  "data": {
    "spec_slug": "sdlc-workflow-architecture/tasks.md",
    "task_range": "1-3",
    "resume": false,
    "auto_pr": true
  }
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `spec_slug` | string | yes | Slug identifying the target spec directory |
| `task_range` | string | no | e.g. `"1-3,5"` (1-indexed, inclusive); omit to run all tasks |
| `resume` | bool | no (default: `false`) | Reattach to an existing worktree/state instead of creating a new one |
| `auto_pr` | bool | no (default: `true`) | Whether to open a PR automatically once the run completes |
| `branch_name` | string | no | Override for the git branch name; derived from `spec_slug` if unset |

---

## Inspect the workflow graph

The API exposes workflow graphs as JSON — useful for seeing node connections without reading source code:

```bash
# List all registered workflow types
curl http://localhost:8080/workflows

# Get the node graph for a specific workflow
curl http://localhost:8080/workflows/CONTENT_PIPELINE/graph
curl http://localhost:8080/workflows/DOCUMENT_QA/graph
```

The graph endpoint returns `start`, `nodes` (with `connections`, `is_router` flag, `description`), and `description` — no auth required.

---

## Reference implementations (not for direct use)

`CUSTOMER_CARE` is a frozen reference workflow used only for the original tech demo. Do not trigger it with real LLM calls — it has no tests and is not maintained. It exists in the codebase so you can see the original event schema structure.
