---
type: TaskSpec
title: Task Spec — Phase 1, Project E (Specialization Refactor)
description: Fix the ParallelNode merge gap and build a specialized, parallelized content pipeline (concept ‖ structure → draft → voice-match → critic → revise → store) alongside Project A for an old-vs-new quality comparison.
---

# Task Spec — Phase 1, Project E (Specialization Refactor)

## Goal
Build a specialized, parallelized content workflow — `Fetch → [ConceptExtractorNode ‖ StructureAnalystNode] → BlogDraftNode → VoiceMatchNode → SelfCritic → Revise → Store` — and fix the framework `ParallelNode` merge gap that the parallel pair is the first genuine need for.

## Context Pointers

- **Plan:** `planning/master-plan.md` → *Project E — Specialization Refactor* (the Before/After graph, the "fix the ParallelNode merge gap here" build note, and "run old and new pipelines; compare").
- **Framework merge gap:** `app/core/nodes/parallel.py` — `execute_nodes_in_parallel()` submits each `node().process(task_context)` against the **same shared** `TaskContext` from worker threads (race on `task_context.nodes`) and the collected `results` are never merged back by any concrete subclass. `NodeConfig.parallel_nodes` (`app/core/schema.py:42`) already carries the parallel set. Existing tests live in `tests/core/test_nodes_parallel.py`.
- **Reuse (read-only — do NOT edit these files):** `SourceRouterNode`, `FetchTranscriptNode`, `FetchArticleNode`, `SelfCriticNode`, `ReviseNode` from `app/workflows/content_pipeline_workflow_nodes/` (Component Reuse Map: `SelfCriticNode/ReviseNode` reused in E). `EmbeddingService`, `GenericRepository`, `LearningArtifact` for the store node. `AgentNode` / `AgentConfig` / `ModelProvider` base for every new agent node (see `blog_writer_node.py` for the canonical shape — `OutputType` subclass, `get_agent_config()`, `run_agent_recorded()`, `update_node(node_name=..., result=...)`).
- **CLAUDE.md rules in force:** prompts are `.j2` only via `PromptManager` (rule 2); register the new workflow in **both** `workflow_registry.py` **and** `schema_registry.py` (rule 6) — `TestSchemaRegistryCompleteness` enforces it; no deployment logic in nodes — model + persistence injected (rule 7); tests seed upstream nodes as `ctx.nodes["X"] = {"result": output}` to mirror `update_node` (rule 9); `customer_care` untouched (rule 3); Python 3.10+ type syntax, module docstring on line 1, `encoding="utf-8"`, `raise ... from e`, no f-strings in logging (code-style rules).
- **Decision:** This ships as a **new workflow** (`specialized_content`), not an in-place edit of `content_pipeline` — the plan calls for running old and new side by side to measure the quality delta, and it keeps Project A's files out of every Project E task's blast radius (parallel-merge safety).

### Parallel-merge file-ownership notes
- **`app/workflows/specialized_content_workflow_nodes/__init__.py` is created EMPTY and declared additive.** Every node task that adds a module to this package needs the package dir to exist, so each may create the empty `__init__.py`; mark it additive in the execution plan so identical empty creations union-merge. Workflows and tests import nodes by **full module path** (matching the Project A pattern — see `content_pipeline_workflow.py`), so no task adds exports to `__init__.py`.
- Each task below owns a **disjoint set of files** (named per step). The only shared mutations are the two registries in Task 5 — and only Task 5 touches them within this block.

## Step-by-Step Tasks

### 1. Fix the ParallelNode merge gap (framework core)
- Owns: `app/core/nodes/parallel.py`, `tests/core/test_nodes_parallel.py`.
- Rework `execute_nodes_in_parallel()` so parallel sub-nodes do not race on shared mutable state and their outputs are **merged after the join**: run each `parallel_nodes` member in the executor, collect the per-node output slot each produced (each sub-node writes only its own uniquely-keyed `nodes[<SubNodeName>]` slot), then merge those slots into the parent `task_context` on the calling thread once all futures complete. No concurrent mutation of `task_context.nodes` mid-flight.
- Provide a working concrete merge in the base so a `ParallelNode` subclass's `process()` can call `execute_nodes_in_parallel(task_context)` and have both slots present afterward (the gap today is that results are returned and dropped).
- Preserve the existing abstract `process` contract and the `NodeConfig.parallel_nodes` lookup; do not change `core/schema.py`.
- Tests: assert **both** parallel slots are present in `task_context` after execution and correctly combined; assert one sub-node's write does not clobber the other's; assert the merge is order-independent. Keep/extend existing `test_nodes_parallel.py` cases.
- Foundational — Task 5 depends on this.

### 2. ConceptExtractorNode ‖ StructureAnalystNode (specialized analysis nodes + prompts)
- Owns: `app/workflows/specialized_content_workflow_nodes/concept_extractor_node.py`, `.../structure_analyst_node.py`, `app/prompts/concept_extractor.j2`, `app/prompts/structure_analyst.j2`, `tests/workflows/test_specialized_content_analysis_nodes.py`, and (empty, additive) `app/workflows/specialized_content_workflow_nodes/__init__.py`.
- Two `AgentNode` subclasses, each with a typed `OutputType`: `ConceptExtractorNode` pulls the key concepts/claims/entities from the fetched text; `StructureAnalystNode` analyzes the source's structure/flow/sections. Each reads the fetched text from the upstream fetch node's output and writes its own slot via `update_node(node_name=self.node_name, result=...)`.
- Prompts live in `.j2` files loaded via `PromptManager().get_prompt(...)` — never hardcoded.
- Tests: mock the agent; assert each node produces its typed output and writes its own uniquely-keyed slot; seed the upstream fetch output as `ctx.nodes["<FetchNode>"] = {"result": ...}` (rule 9).
- Independent of Tasks 1, 3, 4 (disjoint files) — runs in wave 1.

### 3. BlogDraftNode + VoiceMatchNode (downstream specialized nodes + prompts)
- Owns: `app/workflows/specialized_content_workflow_nodes/blog_draft_node.py`, `.../voice_match_node.py`, `app/prompts/blog_draft.j2`, `app/prompts/voice_match.j2`, `tests/workflows/test_specialized_content_draft_nodes.py`, and (empty, additive) `__init__.py`.
- `BlogDraftNode` (`AgentNode`): reads **both** the concept slot and the structure slot (by node name, `["result"]`) and drafts the post body from the combined analysis. `VoiceMatchNode` (`AgentNode`): rewrites the draft into Brandon's voice (the voice guidance asset; align with the existing `blog_writer.j2` voice rather than duplicating it verbatim).
- Tests: mock the agent; for `BlogDraftNode` seed **both** upstream slots as `ctx.nodes["ConceptExtractorNode"] = {"result": ...}` and `ctx.nodes["StructureAnalystNode"] = {"result": ...}` and assert it consumes both; for `VoiceMatchNode` seed the draft slot. Assert typed outputs.
- Independent of Tasks 1, 2, 4 (disjoint files) — runs in wave 1.

### 4. StoreSpecializedArtifactNode (embed-at-write + persist final post)
- Owns: `app/workflows/specialized_content_workflow_nodes/store_artifact_node.py`, `tests/workflows/test_specialized_content_storage_node.py`, and (empty, additive) `__init__.py`.
- Terminal store node for the new workflow: takes the final revised post, embeds it at write time via `EmbeddingService`, and persists a `LearningArtifact` via `GenericRepository` / the injected `db_session` factory (mirror Project A `StorageNode`'s seam — `node_class()` takes zero args; capture the artifact id from the event **before** persisting to avoid the `DetachedInstanceError` Project A hit). Reads the upstream `ReviseNode` output by name. Persistence stays injected — no deployment logic (rule 7).
- Tests: monkeypatch `_persist` (as Project A storage tests do) for the unit path, plus a post-persist regression test that the artifact id is read pre-commit; embedding mocked.
- Independent of Tasks 1, 2, 3 (disjoint files) — runs in wave 1.

### 5. AnalysisParallelNode + workflow assembly + registries
- Owns: `app/workflows/specialized_content_workflow_nodes/analysis_parallel_node.py`, `app/workflows/specialized_content_workflow.py`, `app/schemas/specialized_content_schema.py`, `app/workflows/workflow_registry.py` (append enum member), `app/api/schema_registry.py` (append entry), `tests/workflows/test_specialized_content_workflow.py`.
- `AnalysisParallelNode`: concrete `ParallelNode` subclass whose `NodeConfig.parallel_nodes = [ConceptExtractorNode, StructureAnalystNode]`; its `process()` calls `execute_nodes_in_parallel(task_context)` (from Task 1) and returns the merged context with both slots present.
- `SpecializedContentEventSchema`: `artifact_id` (UUID, default factory), `timestamp`, `url`. No `make_blog` flag — this pipeline always produces a specialized draft (that is the comparison).
- `SpecializedContentWorkflow.workflow_schema`: `SourceRouterNode → {FetchTranscriptNode | FetchArticleNode} → AnalysisParallelNode → BlogDraftNode → VoiceMatchNode → SelfCriticNode → ReviseNode → StoreSpecializedArtifactNode`. Reuse `SourceRouterNode`/`FetchTranscriptNode`/`FetchArticleNode`/`SelfCriticNode`/`ReviseNode` by import (no edits). Graph must be a DAG so `WorkflowValidator` passes.
- Register `SPECIALIZED_CONTENT` in **both** `workflow_registry.py` and `schema_registry.py` (rule 6).
- Tests: a parallel-merge assertion at the workflow level (after `AnalysisParallelNode`, both concept and structure slots are present and combined into `BlogDraftNode`'s input); DAG validity via `WorkflowValidator`; an end-to-end smoke test through the full node chain with agents mocked, asserting cross-node key contracts. `TestSchemaRegistryCompleteness` must pass.
- `dependsOn`: Tasks 1, 2, 3, 4 — runs in wave 2.

### 6. Old-vs-new comparison writeup
- Owns: `planning/phase1-projectE/comparison.md`.
- Document the architectural delta (naive linear Project A blog branch vs. specialized parallel Project E chain), the parallelism rationale, and the **methodology** for running the same source URL through both pipelines and comparing output quality. Capture the structural comparison now; flag the live model-run quality comparison as a manual operator step (the SDLC validation suite cannot make live model calls — consistent with this repo's other deferred e2e gates). OKF frontmatter required.
- `dependsOn`: Task 5 — runs in wave 3.

### 7. Validate
- Run the Validation Commands listed below and confirm all pass. Test count must be ≥ the 689-passing baseline (`pytest-count` `failOn: decrease`). `net-new-lint` clean, `pylint` 10.00/10, both registries complete.

## Acceptance Criteria
- `app/core/nodes/parallel.py`: a parallel run of two sub-nodes leaves **both** uniquely-keyed slots present in the `TaskContext`, correctly combined, with no clobbering or race — proven by tests in `tests/core/test_nodes_parallel.py`.
- New workflow `specialized_content` exists with the full chain `Fetch → [Concept ‖ Structure] → BlogDraft → VoiceMatch → SelfCritic → Revise → Store`, validates as a DAG, and is registered in **both** `workflow_registry.py` and `schema_registry.py` (`TestSchemaRegistryCompleteness` passes).
- Four new specialized agent nodes (`ConceptExtractorNode`, `StructureAnalystNode`, `BlogDraftNode`, `VoiceMatchNode`) each load their system prompt from a `.j2` via `PromptManager`; no prompt is hardcoded in Python.
- `StoreSpecializedArtifactNode` embeds at write time and persists a `LearningArtifact` via injected `GenericRepository`/`db_session`, reading the artifact id before commit (no `DetachedInstanceError`).
- Every new node and the workflow ship with tests; total collected test count ≥ 689 (no decrease).
- `planning/phase1-projectE/comparison.md` documents the old-vs-new architectural delta and the comparison methodology.
- Project A's `content_pipeline` files and `customer_care` are unchanged.

## Validation Commands
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

## Notes
<!-- filled in as work happens -->
