# Implementation Report — phase1-projectD-task4

**Date:** 2026-06-22
**Plan:** planning/phase1-projectD/tasks.md
**Scope:** Task 4

## What Was Built or Changed

- `app/schemas/document_qa_schema.py` — `DocumentQAEventSchema` Pydantic model with `doc_id`, `question`, `session_id` (auto-generated), and `corpus` fields.
- `app/prompts/document_qa_answer.j2` — System prompt for `AnswerNode` instructing the model to answer strictly from the provided context, cite section titles, and fall back to "I don't have that in the document" when context is insufficient. No hardcoded prompt in Python (CLAUDE.md rule 2).
- `app/workflows/document_qa_workflow_nodes/embed_question_node.py` — `EmbedQuestionNode`: plain `Node` that embeds the question text via `EmbeddingService` and stores the vector in `TaskContext`.
- `app/workflows/document_qa_workflow_nodes/assemble_context_node.py` — `AssembleContextNode`: plain `Node` that combines retrieved chunks (formatted with `Section: <title> (relevance: <score>)`) and prior `ChatSession` turns into a combined context result; `_load_session` is a mockable DB seam.
- `app/workflows/document_qa_workflow_nodes/answer_node.py` — `AnswerNode`: `AgentNode` subclass with `AnswerOutput(answer, cited_sections)` output type; calls `run_agent_recorded` for telemetry capture; system prompt loaded via `PromptManager`.
- `app/workflows/document_qa_workflow_nodes/update_session_memory_node.py` — `UpdateSessionMemoryNode`: plain `Node` that loads or creates a `ChatSession`, appends the user question + assistant answer as new turns, extends `topics_covered`, and persists via `GenericRepository`; `_load_session`/`_persist` are mockable seams.
- `app/workflows/document_qa_workflow.py` — `DocumentQAWorkflow`: linear five-node DAG wired with `WorkflowSchema`.
- `tests/workflows/test_document_qa_nodes.py` — 23 node-level tests covering: `EmbedQuestionNode` (embedding stored, called once, correct question), `AssembleContextNode` (section titles + relevance scores in context, prior turns in history, both present simultaneously, empty session case, null section title renders as "General", question threaded through), `AnswerNode` (result stored under result key, answer text accessible, user prompt shape, prior conversation in prompt, agent called once), `UpdateSessionMemoryNode` (new session with two turns, existing session appends turns, result reports session_id + turn count, topics_covered extended, no duplicate topics).
- `tests/workflows/test_document_qa_workflow.py` — 14 workflow wiring + schema tests covering structure (start node, 5-node set, linear connections, no routers), `WorkflowValidator` acceptance, and `DocumentQAEventSchema` validation (required fields, auto session_id, corpus defaults, validation errors).

## Files Created or Modified

| File | Action |
|---|---|
| `app/schemas/document_qa_schema.py` | created |
| `app/prompts/document_qa_answer.j2` | created |
| `app/workflows/document_qa_workflow_nodes/embed_question_node.py` | created |
| `app/workflows/document_qa_workflow_nodes/assemble_context_node.py` | created |
| `app/workflows/document_qa_workflow_nodes/answer_node.py` | created |
| `app/workflows/document_qa_workflow_nodes/update_session_memory_node.py` | created |
| `app/workflows/document_qa_workflow.py` | created |
| `tests/workflows/test_document_qa_nodes.py` | created |
| `tests/workflows/test_document_qa_workflow.py` | created |

## Validation Output

**Commands run:**
```
cd app && uv run python -c 'import main'
cd app && uv run python -c 'import worker.config'
cd app && uv run python -c 'import database.session'
cd app && uv run python -c 'import database.repository'
uv run python -m ruff check app/
uv run python -m pylint app/
uv run python -m pytest --collect-only -q
uv run python -m pytest
```
**Result:** PASSED

## Decisions and Trade-offs

- **EmbedQuestionNode re-embed vs. share**: `RetrieveChunksNode` re-embeds the question internally. The node is kept as a named DAG step to make the workflow readable and expose the embedding for potential future consumers — the overlap is intentional per the breakdown spec.
- **AssembleContextNode `_load_session` as seam**: the session load is isolated to a single method so tests can inject fake sessions without any database. Same pattern as `_persist` in `StorageNode` and `StoreChunksNode`.
- **`UpdateSessionMemoryNode` `_persist` uses `exists` check**: the repository's `exists()` method guards the create-vs-update decision without relying on ORM state. New sessions use `create`; existing ones use `update` (which calls `session.merge`).
- **`AnswerNode.process` handles both Pydantic model and dict**: `run_agent_recorded` may store the `OutputType` instance directly when `node_run` is not set; `UpdateSessionMemoryNode` reads via `hasattr` to handle both paths cleanly.
- **Workflow registration deferred**: Task 4 is scope-contained to the nodes, schema, workflow class, and tests. Registration in `workflow_registry.py` and `schema_registry.py` is Task 5's exclusive scope (to avoid collision on the shared registry files).

## Follow-up Work

- **Task 5** registers `DocumentQAWorkflow` (and `DocumentIngestWorkflow`) in both `workflow_registry.py` and `schema_registry.py`; runs `TestSchemaRegistryCompleteness`.
- **Task 6** documents `DocumentQAWorkflow`, `AssembleContextNode`, and `UpdateSessionMemoryNode` in `docs/api-reference.md`.
- Two-stage SQL in `RetrieveChunksNode._semantic_search` and `_keyword_search` is validated by unit tests with mocked DB calls; the actual pgvector query is exercised at integration/manual test time only (noted in breakdown.md gap section).

## git diff --stat

```
(new files only — no existing files modified in this task)
app/prompts/document_qa_answer.j2                                         | 19 +
app/schemas/document_qa_schema.py                                         | 36 +++
app/workflows/document_qa_workflow.py                                     | 56 +++++
app/workflows/document_qa_workflow_nodes/answer_node.py                   | 65 ++++++
app/workflows/document_qa_workflow_nodes/assemble_context_node.py         | 93 ++++++++++
app/workflows/document_qa_workflow_nodes/embed_question_node.py           | 36 +++
app/workflows/document_qa_workflow_nodes/update_session_memory_node.py    | 116 +++++++++++++
tests/workflows/test_document_qa_nodes.py                                 | 498 ++++++++++++++++++++++++++++++++++++++++++++++++++++
tests/workflows/test_document_qa_workflow.py                              | 120 +++++++++++++
```
