---
type: AlignmentNotes
title: Diagnostic Alignment — Projects B and C Constraints
description: Constraint document governing how Projects B (research agent) and C (proposal generator) are specced. Both must produce output conforming to The Diagnostic artifact schemas in the company brain.
status: Active
brain_ref: agentic-portfolio/planning/the-diagnostic/
---

# Diagnostic Alignment — Projects B and C Constraints

## 1. What this document is

The Diagnostic (brain `planning/the-diagnostic/plan.md`) is the productized contracting practice — a paid intake session that turns a client interview into a ranked automation roadmap. Projects B and C in the python-orchestration-system are the orchestrated implementation of Stage 1's two halves. This document ensures they're built toward client-revenue output, not generic portfolio demos. Whoever specs Project B or C must read this before writing their task specs.

---

## 2. Project B (research agent) constraints

**Purpose in the diagnostic:** Project B's job is to conduct (or structure) the client intake and produce the structured evidence that feeds the scoring pass. It is the research half of Stage 1.

**Output schema constraint:**
Project B must produce output conforming to the `WorkflowCandidate` extraction schema defined in `agentic-portfolio/planning/the-diagnostic/intake.md`. Specifically:

```python
class WorkflowCandidate(BaseModel):
    name: str
    description: str
    frequency_evidence: str      # raw evidence from client — not a score
    time_cost_evidence: str      # raw evidence from client — not a score
    buildability_notes: str      # what we know about the systems involved
    knowledge_holder: str        # who holds this knowledge
    failure_mode: str            # what breaks when this goes wrong

class DiagnosticIntakeOutput(BaseModel):
    company_name: str
    company_type: str
    team_size: int
    primary_channels: list[str]
    existing_tools: list[str]
    existing_automations: list[str]
    top_workflows: list[WorkflowCandidate]
```

**What "research" means here:** Project B is not a web crawler. For diagnostic use, the "research" is structuring evidence from the intake call notes (raw text) into the schema above. The research agent reads the notes, asks clarifying questions if needed (via a follow-up prompt), and extracts the structured fields.

**Test constraint:** Project B's test suite must include at least one test that:
- Takes raw intake notes as input
- Verifies the output is a valid `DiagnosticIntakeOutput` instance
- Checks that `top_workflows` is non-empty and each candidate has all required fields

**Embedding constraint (W5 dependency):**
When Project B's output is saved, call `EmbeddingService.embed_text()` on a summary string:
```python
embed_text = f"{output.company_type}: {'; '.join(w.name for w in output.top_workflows)}"
```
Store as `BrainDocument(doc_type="diagnostic", file_path=f"diagnostics/{client_slug}/intake.json")`.
This enables "similar past diagnostics" semantic search once 3–5 runs exist. The `BrainDocument` schema is defined in `agentic-portfolio/planning/the-diagnostic/workstreams/brain-rag/index.md` and implemented in `app/database/brain_document.py` (W4 workstream).

---

## 3. Project C (proposal generator) constraints

**Purpose in the diagnostic:** Project C takes the structured intake output (from Project B) plus rubric scores and produces the client-facing deliverable. It is the synthesis half of Stage 1.

**Input:** `DiagnosticIntakeOutput` from Project B + scored candidates JSON from a scoring pass.

**Output format constraint:**
Project C must produce output conforming to the deliverable template in `agentic-portfolio/planning/the-diagnostic/deliverable.md`. Required sections:
1. Situation & Opportunity (plain prose, 1 page)
2. Ranked Automation Candidates (table with scores and tiers)
3. Top 3 Workflow Profiles (one page each, per template)
4. Recommended First Engagement (scope + price range + CTA)

**Scoring constraint:**
The rubric from `agentic-portfolio/planning/the-diagnostic/rubric.md` must be embedded in Project C's Jinja2 prompt template (per D8 — all prompts in external `.j2` templates via PromptManager). The template must include the axis definitions and anchor descriptions so the LLM scores consistently regardless of model version.

The composite formula:
```
composite = (frequency × 0.35) + (time_cost × 0.40) + (buildability × 0.25)
```

**Pydantic output model:**
```python
class WorkflowProfile(BaseModel):
    name: str
    current_state: str
    proposed_solution: str
    stack: list[str]
    rough_scope_weeks: tuple[int, int]  # (min, max)
    roi_hrs_per_week: float

class AutomationRoadmap(BaseModel):
    situation_summary: str
    candidates: list[ScoredCandidate]   # sorted by composite desc
    top_profiles: list[WorkflowProfile]  # top 3
    recommended_workflow: str
    engagement_scope: str
    price_range_brl: tuple[int, int]
```

**Test constraint:** Project C's test suite must include at least one test that:
- Takes a `DiagnosticIntakeOutput` and scored candidates as input
- Verifies output is a valid `AutomationRoadmap` instance
- Checks that `candidates` is sorted by composite score descending
- Checks that `top_profiles` contains exactly 3 entries (or all candidates if fewer than 3)

**Language note:** For São Paulo SMB clients, Project C should default to Portuguese output when `company_type` indicates a Brazilian business. Add a `language: Literal["EN", "PT"]` field to the prompt context.

---

## 4. Sequencing within the orchestrator roadmap

```
Project B (research agent)     ← thin cut first (~50 lines), then wire to diagnostic schema
Project C (proposal generator) ← after Project B output schema is stable
Project D (document Q&A + RAG) ← gates the competence checkpoint (independent of B+C)
```

Projects B and C are not gated on Project D. They can be built in parallel with D. The diagnostic can be run manually (see `agentic-portfolio/planning/the-diagnostic/stage1-spec.md`) before B+C are orchestrated.

---

## 5. Files to read before speccing B or C

- `agentic-portfolio/planning/the-diagnostic/plan.md` — the thesis and stage sequence
- `agentic-portfolio/planning/the-diagnostic/intake.md` — the interview guide and output schema
- `agentic-portfolio/planning/the-diagnostic/rubric.md` — scoring methodology
- `agentic-portfolio/planning/the-diagnostic/deliverable.md` — the client artifact template
- `agentic-portfolio/planning/the-diagnostic/workstreams/brain-rag/index.md` — BrainDocument schema (for embedding constraint)
