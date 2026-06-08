# Breakdown — Decompose a task spec into agent-executable sub-steps.

Takes a task spec from `planning/tasks/` and produces a granular breakdown where every
sub-step names exact file paths, class/function names, and what to write or change —
precise enough for an agent (or a human) to execute without interpretation.

## Variables

$ARGUMENTS — path to the task spec to break down (e.g. `planning/tasks/phase0-blockC/tasks.md`).
             If omitted, default to the current block's spec identified via `planning/STATUS.md`.
             If no spec exists for the current block, say so and suggest running `/next-task`.

## Instructions

1. Resolve the target spec:
   - If `$ARGUMENTS` is provided, read that file.
   - If omitted, read `planning/STATUS.md` to find the current block, then read its spec.
   - If neither yields a file, stop and explain clearly.

2. Read the spec in full. Note:
   - Every step in **Step-by-Step Tasks**
   - The **Relevant Files** or **Context Pointers** section
   - The **Acceptance Criteria** and **Validation Commands** (copied verbatim into the breakdown)

3. Read `CLAUDE.md` for standing rules (prompts must be `.j2` files, workflow registration, tests
   required, known bugs). These constraints belong in the relevant sub-steps, not as a separate note.

4. **For each step in the spec, before writing its breakdown:** read the actual source files
   that step touches. This is not optional — the breakdown must name real things:
   - If a step says "unit test `TaskContext`" → read `app/core/task.py` to get the actual
     method names and signatures before writing the test sub-steps.
   - If a step says "add `EmbeddingService`" → read `app/services/` to understand the existing
     service pattern before writing the implementation sub-steps.
   - If a step creates a new workflow node → read an existing node in
     `app/workflows/customer_care_workflow_nodes/` to match the exact pattern.
   - Read only what is relevant to each step. Do not load the entire codebase.

5. Decompose each spec step into numbered sub-steps using the format `N.M`
   (e.g. step 2 → sub-steps 2.1, 2.2, 2.3). Each sub-step must be atomic:
   - One file to create or one specific change to one existing file.
   - If creating a file: state the full path and the complete structure (classes, functions,
     fixtures, imports) — not "add a test file."
   - If editing a file: state the exact function or line to change and what to add or replace.
   - If running a command: write the exact command, not a description of what to run.

6. After each logical group of sub-steps (not only at the end), add an inline **Verify** check:
   a single command or observation that confirms the group succeeded before moving on.

7. Write the breakdown to `planning/tasks/<block-dir>/breakdown.md` — same directory as the spec, named `breakdown.md`.

8. Return only the path to the file created.

## What makes a sub-step unambiguous

Good sub-step:
> **2.3 Create `tests/core/test_task.py`**
> File: `tests/core/test_task.py`
> Class: `TestTaskContext`
> - `test_add_result_stores_value` — call `ctx.add_result("k", "v")`, assert `ctx.get_result("k") == "v"`
> - `test_get_all_results_returns_dict` — add two keys, assert `ctx.get_all_results()` returns `{"k1": ..., "k2": ...}`
> - `test_missing_key_returns_none` — assert `ctx.get_result("missing")` returns `None` (or raises — match actual behaviour in `task.py`)

Bad sub-step (too vague to execute without interpretation):
> - Add tests for TaskContext

## Context / Files to Read

- `$ARGUMENTS` (the spec file, or the current block's spec)
- `planning/STATUS.md` (only if $ARGUMENTS is omitted)
- `CLAUDE.md`
- Source files relevant to each step (read per-step, not upfront)

## Output Format

```md
# Task Breakdown — <spec title>

## Source Spec
`<path to the spec file this was generated from>`

## Goal
<copied verbatim from the spec>

## How to Use
Work top to bottom. Each sub-step is a single atomic action. Run the inline **Verify**
checks as you go — do not batch them at the end. Each check must pass before continuing.

---

## Steps

### Step 1: <step name from spec>

#### 1.1 <atomic action — one file or one change>
**File:** `<exact relative path>`
**Action:** <create / add function / edit line / run command>
<precise content, structure, or change — not a description>

#### 1.2 <next atomic action>
...

**Verify:** `<exact command>` → <expected output or exit code>

---

### Step 2: <step name from spec>

#### 2.1 ...

...

**Verify:** `<exact command>` → <expected output>

---

<!-- repeat for every step in the spec -->

---

## Acceptance Criteria
<copied verbatim from the spec — do not paraphrase>

## Validation Commands
<copied verbatim from the spec — do not paraphrase>

## Notes
<any discoveries made while reading the codebase that affect execution — e.g. a method
 signature differs from what the spec implied, or a standing rule from CLAUDE.md applies>
```

## Report

Return only the path to the file created (e.g. `planning/tasks/phase0-blockC/breakdown.md`).
