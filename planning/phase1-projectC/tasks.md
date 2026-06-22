---
type: TaskSpec
title: Task Spec — Phase 1, Project C (Proposal Generator)
description: Diagnostic-aligned client proposal generator workflow — research → scored opportunities → PT/EN roadmap → review/revise routing → storage.
---

# Task Spec — Phase 1, Project C (Proposal Generator)

## Goal
Build the `proposal_generator` workflow: research → structured scored opportunities → review/revise-with-routing, emitting a client-facing automation roadmap conforming to The Diagnostic deliverable template (PT + EN).

## Context Pointers
- **Plan:** `planning/master-plan.md` → "Project C — Client Proposal Generator" (DAG, review criteria, schemas).
- **Binding constraint (read first):** `planning/diagnostic-alignment/notes.md` §3 — Project C output **must** conform to the deliverable template. This governs the output schema (`AutomationRoadmap`, `WorkflowProfile`, scored candidates), the composite scoring formula `(frequency × 0.35) + (time_cost × 0.40) + (buildability × 0.25)`, the embedded rubric in the `.j2` prompt, and the PT/EN language field. Where the notes and the master-plan diverge on schema names, **the notes win**; the master-plan governs the DAG shape.
- **Brain reference docs** (parent repo, read-only): `agentic-portfolio/planning/the-diagnostic/deliverable.md` (sections), `rubric.md` (axis anchors), `intake.md` (`DiagnosticIntakeOutput` input shape).
- **Reuse:** `CompanyResearchNode` from Project B (`app/workflows/research_agent_workflow_nodes/company_research_node.py`) — first real cross-project node reuse. `EmbeddingService` + `BrainDocument` (`app/database/brain_document.py`) for storage. `GenericRepository` + `db_session` factory seam for persistence (no constructor injection — `node_class()` takes zero args).
- **Patterns to mirror:** `app/workflows/content_pipeline_workflow.py` (WorkflowSchema `start`/`nodes`/`connections`, router `is_router=True`, linear self-critic→revise branch, `StorageNode` persistence seam), `app/schemas/research_agent_schema.py` (event + output schema shape).
- **CLAUDE.md standing rules:** every workflow ships with tests (rule 1); no hardcoded prompts — `.j2` via `PromptManager` (rule 2); register in BOTH `workflow_registry.py` (rule 6) AND `app/api/schema_registry.py` (the gap that bit Project B); no deployment logic in nodes (rule 7); Python 3.10+ type syntax, module docstring line 1, `raise ... from e`, no f-strings in logging.

## Step-by-Step Tasks

### 1. Schemas + workflow scaffold + registration (foundational)
- Create `app/schemas/proposal_generator_schema.py`:
  - `ProposalGeneratorEventSchema` — `company_name: str`, `industry: str`, `description: str`, `language: Literal["EN", "PT"]` (default infer/`"PT"` per notes §3 language note), plus `artifact_id: UUID` (default_factory) and `timestamp: datetime` (mirror `ResearchAgentEventSchema`). Optional `intake_notes: str | None = None` to accept raw `DiagnosticIntakeOutput`-style notes.
  - `Opportunity` / `ScoredCandidate` — `name`, `problem_statement`, `proposed_solution`, `estimated_value`, `build_complexity`, plus axis scores `frequency`, `time_cost`, `buildability` and a derived `composite: float`.
  - `WorkflowProfile` — `name`, `current_state`, `proposed_solution`, `stack: list[str]`, `rough_scope_weeks: tuple[int, int]`, `roi_hrs_per_week: float`.
  - `AutomationRoadmap` (the deliverable output) — `situation_summary`, `candidates: list[ScoredCandidate]` (sorted composite-desc), `top_profiles: list[WorkflowProfile]` (top 3 or all if fewer), `recommended_workflow: str`, `engagement_scope: str`, `price_range_brl: tuple[int, int]`. Include the EN/PT body fields the writer fills.
- Create the workflow package: `app/workflows/proposal_generator_workflow_nodes/__init__.py` and a **minimal stub** `app/workflows/proposal_generator_workflow.py` (`ProposalGeneratorWorkflow(Workflow)` with a stub `WorkflowSchema` and `event_schema=ProposalGeneratorEventSchema` — the DAG is wired in Task 7).
- Register in `app/workflows/workflow_registry.py` (`PROPOSAL_GENERATOR = ProposalGeneratorWorkflow`) AND `app/api/schema_registry.py` (`PROPOSAL_GENERATOR.name → ProposalGeneratorEventSchema`).
- **Owns:** `app/schemas/proposal_generator_schema.py`, `app/workflows/proposal_generator_workflow.py`, `app/workflows/proposal_generator_workflow_nodes/__init__.py`, `app/workflows/workflow_registry.py`, `app/api/schema_registry.py`, `tests/schemas/test_proposal_generator_schema.py`.
- Tests: schema validation (composite computed correctly; `candidates` sort invariant; `top_profiles` ≤ 3 rule), and a registry-presence test guarding both `workflow_registry` and `schema_registry` (regression guard from Project B).

### 2. CompanyResearchNode reuse (depends on 1)
- Create `app/workflows/proposal_generator_workflow_nodes/company_research_node.py` reusing Project B's `CompanyResearchNode` (subclass or thin wrapper) so the proposal pipeline opens with the proven raw tool-use research loop. Adapt input to read `ProposalGeneratorEventSchema` (`company_name` + `industry` + `description`/`intake_notes`) and write research evidence to `TaskContext` under this node's output key.
- **Owns:** `company_research_node.py`, `tests/workflows/test_proposal_company_research_node.py`. (Do NOT edit Project B's node file — reuse via import/subclass.)
- Tests: mocked tool client; asserts evidence is written to context and the loop terminates.

### 3. OpportunityIdentifierNode — scoring against the rubric (depends on 1)
- Create `OpportunityIdentifierNode` (AgentNode) reading the research evidence and emitting 3 scored opportunities. Score each on `frequency`/`time_cost`/`buildability` per the rubric anchors and compute `composite` with the binding formula. Sort `candidates` composite-desc; pick `recommended`.
- Prompt: `app/prompts/proposal_opportunity_identifier.j2` — **embed the rubric axis definitions and anchor descriptions** (notes §3 scoring constraint) so scoring is model-version-stable. Loaded via `PromptManager`.
- **Owns:** `opportunity_identifier_node.py`, `app/prompts/proposal_opportunity_identifier.j2`, `tests/workflows/test_opportunity_identifier_node.py`.
- Tests: mocked agent; structured-output validation; composite math; one recommendation (not three).

### 4. ProposalWriterNode — PT + EN roadmap (depends on 1)
- Create `ProposalWriterNode` (AgentNode) producing the `AutomationRoadmap` deliverable: Situation & Opportunity prose, ranked candidates table, top-3 `WorkflowProfile`s, recommended first engagement (scope + `price_range_brl` + CTA). Honor `event.language` (default PT for Brazilian `industry`/`company_type`).
- Prompt: `app/prompts/proposal_writer.j2` (and/or `proposal_writer_pt.j2` / `_en.j2`) — encode the deliverable template's four required sections (notes §3). Loaded via `PromptManager`.
- **Owns:** `proposal_writer_node.py`, `app/prompts/proposal_writer*.j2`, `tests/workflows/test_proposal_writer_node.py`.
- Tests: mocked agent; valid `AutomationRoadmap` out; PT and EN both exercised; `top_profiles` exactly 3 (or all if fewer).

### 5. Review + router + revise branch (depends on 1)
- Create `ProposalReviewNode` (AgentNode) validating the roadmap against the explicit criteria (notes/master-plan §C): names client ≥3×, exactly one specific testable deliverable, realistic timeline (4–8 wks first project), avoids vague language, investment matches complexity — each PASS/FAIL with a line reference, yielding a `pass`/`revise` verdict.
- Create `ProposalReviewRouterNode` (RouterNode, `is_router=True`) → `StorageNode` on `pass`, → `ReviseNode` on `revise`.
- Create `ReviseNode` (AgentNode) that addresses feedback and produces the corrected roadmap, then flows to `StorageNode` (strictly linear — no loop-back, keep the DAG acyclic per `WorkflowValidator`).
- Prompts: `app/prompts/proposal_review.j2`, `app/prompts/proposal_revise.j2` via `PromptManager`.
- **Owns:** `proposal_review_node.py`, `proposal_review_router_node.py`, `proposal_revise_node.py`, `app/prompts/proposal_review.j2`, `app/prompts/proposal_revise.j2`, `tests/workflows/test_proposal_review_router.py`.
- Tests: review criteria PASS/FAIL emission; router pass/revise branching; revise path produces a corrected roadmap.

### 6. StorageNode — BrainDocument + embedding (depends on 1)
- Create `StorageNode` persisting the final roadmap via `GenericRepository` + the `db_session` factory seam (capture ids before commit — avoid the Project A `DetachedInstanceError`: commit closes the session). Call `EmbeddingService.embed_text()` on a summary string and store a `BrainDocument(doc_type="proposal"|"diagnostic", file_path=...)` per notes §2/§3. No deployment logic in the node.
- **Owns:** `storage_node.py`, `tests/workflows/test_proposal_storage_node.py`.
- Tests: persistence path with mocked repository/session; embedding called; post-commit id read works (regression guard).

### 7. Wire the workflow DAG + integration test (depends on 2,3,4,5,6)
- Fill `ProposalGeneratorWorkflow.workflow_schema` in `app/workflows/proposal_generator_workflow.py`: `start=CompanyResearchNode`; connections `CompanyResearchNode → OpportunityIdentifierNode → ProposalWriterNode → ProposalReviewNode → ProposalReviewRouterNode → {StorageNode | ReviseNode}`, `ReviseNode → StorageNode`. Mark the router `is_router=True`. Confirm `WorkflowValidator` passes (acyclic, all connections resolve).
- **Owns:** `app/workflows/proposal_generator_workflow.py` (fills the Task-1 stub — serialized after Task 1 via the dependency chain, no concurrent edit), `tests/workflows/test_proposal_generator_workflow.py`.
- Tests: end-to-end run with all agents/tools mocked, both pass and revise routes; the diagnostic-constraint test (notes §3) — given intake-style input, output is a valid `AutomationRoadmap`, `candidates` sorted composite-desc, `top_profiles` exactly 3 (or all if fewer).

### 8. Validate
- Run the Validation Commands listed below and confirm all pass.

## Acceptance Criteria
- `proposal_generator` workflow runs end-to-end (mocked agents/tools) through both the `pass` and `revise` routes and produces a valid `AutomationRoadmap`.
- Output conforms to the deliverable template: four required sections present; `candidates` sorted by `composite` descending; `top_profiles` contains exactly 3 (or all candidates if fewer than 3).
- Composite scoring uses `(frequency × 0.35) + (time_cost × 0.40) + (buildability × 0.25)`; the rubric anchors are embedded in the `.j2` prompt, not in Python.
- Proposal renders in both PT and EN per `event.language`; review criteria enforce client-name ≥3×, one testable deliverable, 4–8 wk timeline, no vague language.
- Registered in BOTH `workflow_registry.py` and `app/api/schema_registry.py`; `CompanyResearchNode` reused from Project B without editing Project B's file.
- No hardcoded system prompts; storage goes through `GenericRepository`/`db_session` with no `if running_locally:` logic; all new tests pass and the suite count does not drop.

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
<filled in as work happens>
