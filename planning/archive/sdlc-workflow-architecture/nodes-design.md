---
type: Reference
title: SDLC Workflow Nodes Design
description: Structural blueprint for implementing sdlc-flow and sdlc-run workflows as Python-native Nodes and DAG configurations, including model routing strategies.
doc_id: sdlc-workflow-nodes-design
layer: [engine]
project: orchestrator
status: archived
keywords: [sdlc, workflows, nodes, design, flow, run, models]
related: [readme, app-architecture-overview, node-model-comparison]
---

# Design Specification: Python-Native Nodes for SDLC Workflows

This document details the architectural design for implementing `sdlc-flow` and `sdlc-run` as native workflows under `app/workflows/` using the FastAPI/Celery orchestration system. It also outlines the strict model routing strategy (Cloud vs. Local) based on node complexity.

---

## 1. Node Reference Index

Each stage of the SDLC pipeline maps to a concrete Python `Node` subclass. This structure enforces a clean separation of concerns, enables reuse (e.g., in other workflows), and allows per-node model routing.

| Proposed Node Class | Base Class | Responsibility | AI/LLM Usage | Target Model Tier |
| :--- | :--- | :--- | :--- | :--- |
| `SetupWorktreeNode` | `Node` | Creates/locates sparse checkouts in `trees/` and sets up local port routing. | Deterministic (Git CLI) | Haiku / 8B Local |
| `GenerateTasksNode` | `AgentNode` | Generates a `tasks.md` spec if missing (planning fallback). | Yes (Frontier Model) | Opus / Pro |
| `EnumerateTasksNode` | `Node` | Parses the `### N.` task headings from `tasks.md` and filters range. | Deterministic (Python parser) | Haiku / 8B Local |
| `LoadStateNode` | `Node` | Reads `sdlc-flow-state.json` to configure skips for already passed tasks. | Deterministic (JSON load) | Haiku / 8B Local |
| `SaveStateNode` | `Node` | Commits changes and writes the running state back to `sdlc-flow-state.json`. | Deterministic (JSON dump + Git) | Haiku / 8B Local |
| `UpdateTaskStatusNode` | `Node` | Surgically edits the `tasks.md` checkbox markers (`[ ]` to `[~]`, `[x]`, or `[fail]`). | Deterministic (Regex) | Haiku / 8B Local |
| `ImplementTaskNode` | `AgentNode` | Authors code modifications using the `ModelProvider.CLAUDE_CODE_SDK` seam. | Yes (Coding Model) | Sonnet / Pro |
| `TestTaskNode` (Validate) | `Node` | Runs the test command, baseline diff, warning, and emoji gates. | Deterministic (Subprocess) | Haiku / 8B Local |
| `TriageTaskNode` | `RouterNode` | Analyzes test output to route to retry/fix loops or trigger a `MAJOR` bail. | Yes (Fast Classifier) | Sonnet / 32B Local |
| `ConsolidatedReviewNode` | `AgentNode` | Performs final code review check over the complete diff vs criteria. | Yes (Frontier/Reasoning) | Sonnet / Opus / Pro |
| `PatchDocsNode` | `AgentNode` | Surgically patches changed API surfaces in `docs/*.md` (Bootstrap mode if empty). | Yes (Writing Model) | Sonnet / 32B Local |
| `WrapUpNode` | `AgentNode` | Appends log entries to `log.md` and updates `planning/status.md`. | Yes (Summarization Model) | Sonnet / 32B Local |
| `PullRequestNode` (Merge) | `Node` | Commits remaining state, pushes branch, opens PR, and handles auto-merges. | Deterministic (Git/GitHub API) | Haiku / 8B Local |

---

## 2. Model Routing & Target Hardware Strategy

Because SDLC operations range from highly complex software engineering to basic text parsing, the system heavily utilizes **per-node model assignment**. 

### The Local Hardware Profiles
* **M2 MacBook Pro (32GB RAM):** Capable of running models up to ~35B parameters (e.g., `Qwen2.5-32B`, ~20 GB). Do not run 70B models at 4-bit, as they will swap and degrade speed.
* **M1 Mac Mini (16GB RAM):** Hard capped at ~12B parameters before swap (e.g., `Llama-3.1-8B-Instruct`, `Mistral-Nemo-12B`).

### ✅ Safe for Mac Mini (16GB) - "The Utility Setup"
If deploying a local worker on the Mac Mini, you can safely route the following deterministic/administrative nodes to **`Llama-3.1-8B-Instruct`**:
* `SetupWorktreeNode`, `EnumerateTasksNode`, `TestTaskNode`, `UpdateTaskStatusNode`, `SaveStateNode`, `LoadStateNode`, `PullRequestNode`. 
* *Why:* These nodes wrap basic CLI/Regex operations and extract JSON. An 8B model is perfectly capable and lightning fast.

### ✅ Safe for MacBook Pro (32GB) - "The Contributor Setup"
If deploying a local worker on the MBP, you unlock the ability to route mid-tier reasoning tasks to **`Qwen2.5-32B-Instruct`** (or `Command-R 35B`):
* `TriageTaskNode` (Categorizing failures).
* `PatchDocsNode` (Writing markdown documentation updates).
* `WrapUpNode` (Synthesizing Git logs into human-readable prose).

### ❌ ABSOLUTELY Cloud-Only (Do Not Run Locally)
For production SDLC workflows, the following nodes **must** remain on Frontier Cloud models. Do not use local models for these:
1. **`ImplementTaskNode` (Coding):** Writing production-grade software requires the deepest context windows and highest coding benchmarks. **Claude 3.5 Sonnet** is the absolute industry standard here. A local 32B model will struggle with complex multi-file architectural changes.
2. **`ConsolidatedReviewNode` (LLM-as-a-judge):** Authoritative code review requires rigorous adherence to acceptance criteria and the ability to spot subtle logic bugs. Local models are prone to hallucinating a "pass". Keep this on **Claude 3.5 Sonnet** (escalating to **Opus** for final retries).
3. **`GenerateTasksNode` (Planning):** Generating the architectural spec that drives the entire pipeline requires peak reasoning. **Claude 3 Opus** or **Gemini 1.5 Pro** should be used.

---

## 3. Detailed Node Architecture

### SetupWorktreeNode
* **Inputs:** `spec_slug`, `branch_name`, `resume` flag.
* **Logic:**
  1. Computes the worktree path: `trees/{branch_name}`.
  2. Runs `git worktree add trees/{branch_name} -b {branch_name} origin/main`.
  3. Executes sparse-checkout to minimize worktree footprint:
     ```bash
     git sparse-checkout init --cone
     git sparse-checkout set <tracked_dirs_excluding_heavy_assets>
     ```
  4. Copies `.env` and `.env.local` templates.
  5. Inspects active port bindings and writes `.ports.env` (e.g. `BACKEND_PORT=9101`, `FRONTEND_PORT=9201`) to support isolated service launches.
* **Outputs:** Sets `worktree_path` and allocated ports in `TaskContext.data`.

### EnumerateTasksNode
* **Inputs:** `spec_slug` (to locate `planning/{spec_slug}/tasks.md`), task selection range string (e.g., `1-3,5`).
* **Logic:**
  1. Opens and reads `planning/{spec_slug}/tasks.md`.
  2. Parses headings matching regex `r"^### (\d+)\."`.
  3. Filters headings using task selection parser.
* **Outputs:** Stores list of task integers (e.g. `[1, 2, 3, 5]`) in `TaskContext.data["tasks_to_run"]`.

### LoadStateNode / SaveStateNode
* **Inputs:** `spec_slug`.
* **Logic (Load):** Reads `planning/{spec_slug}/sdlc/sdlc-flow-state.json`. If present, populates `TaskContext.data["passed_tasks"]` to allow skipping.
* **Logic (Save):** 
  1. Collects telemetry and spent budget from `TaskContext`.
  2. Serializes `TaskContext.data` state object to JSON.
  3. Appends markdown worklog sections to `planning/{spec_slug}/sdlc/worklog.md`.
  4. Explicitly adds and commits `sdlc-flow-state.json` and `worklog.md` using `git commit -m "chore: flow state — <stage>"`.

### ImplementTaskNode
* **Inputs:** Active `task_number`, `worktree_path`, `spec_slug`.
* **Logic:**
  1. Builds a prompt wrapping the description and acceptance criteria from `tasks.md` under `### {task_number}`.
  2. If a `breakdown.md` exists, appends the checklist sub-steps from `### Step {task_number}:`.
  3. Dispatches execution to `ClaudeCodeModel` (which runs via the `ClaudeAgentSdkBackend` or `BastionSessionBackend` protocol).
  4. Instructs the model to restrict edits to target files and write unit tests for any new logic.
* **Outputs:** Returns the list of modified files and the execution short hash.

### TestTaskNode (Validate)
* **Inputs:** `worktree_path`, `planning/harness.json` configuration.
* **Logic:**
  Iterates over the checks defined in `harness.json`. For each check, runs subprocess executions inside `worktree_path`:
  * **`command`:** Runs `pytest`/`pylint` etc., checking the exit code.
  * **`baseline-diff`:** Redirects test output to a temporary JSON file. Compares current output against pre-run baseline JSON files in `sdlc/reports/` using Python dictionaries. Reports net-new failures only.
  * **`warning-scan`:** Scans output log files for warning-severity regex matches.
  * **`forbidden-pattern-scan`:** Runs `grep` queries to ensure clean imports/patterns.
  * **`emoji-gate`:** Runs `git diff --name-only main..HEAD` and scans changed markdown files for stray emoji characters.
* **Outputs:** Stores `all_passed` Boolean, detailed test logs, pass/fail counts, and failure logs.

### TriageTaskNode
* **Inputs:** Failing logs from `TestTaskNode`, active `attempt` counter, `max_attempts`.
* **Logic:**
  1. Implements `RouterNode`.
  2. Routes task execution back to `ImplementTaskNode` if the failure is classified as `RETRYABLE` (transient error, or progress was made and a fix can address it).
  3. If the attempt count exceeds `max_attempts`, or if an `IMMEDIATE-BAIL` condition is detected (missing dependencies, ambiguous spec, out of scope, stuck error), bails.
* **Outputs:** Sets target node route to `ImplementTaskNode` (retry) or `WrapUpNode` (bail).

### ConsolidatedReviewNode
* **Inputs:** Full git diff of the worktree branch vs main.
* **Logic:**
  1. Runs the complete, authoritative harness checks.
  2. Utilizes a frontier reasoning model (e.g. Claude 3.5 Sonnet / Opus) to check the diff against the complete list of acceptance criteria in `tasks.md`.
  3. Issues a `PASS`, `FAIL`, or `PARTIAL` verdict.
  4. If `FAIL`/`PARTIAL` and the issues are minor/localized, sets route to run a targeted patch loop.
  5. If structural/broad, sets route to `WrapUpNode` to bail.

### PatchDocsNode
* **Inputs:** List of modified source files.
* **Logic:**
  1. Searches `docs/` for files referencing modified files or symbols.
  2. Patches the doc files to match the new API signatures or behavior.
  3. If `docs/` is empty, enters Bootstrap mode to create `architecture.md`, `api-reference.md`/`cli.md`, and `index.md` from scratch.

### WrapUpNode
* **Inputs:** Run execution metrics, active task history, final verdict.
* **Logic:**
  1. Surgically edits `planning/status.md` using regex to update progress status and bump timestamps.
  2. Prepends a dated summary block to `log.md` containing run outcomes and recent git log commits.
  3. Generates the final markdown report file under `reports/`.

### PullRequestNode (Merge)
* **Inputs:** `branch_name`, `pr_base`, `auto_merge` flag.
* **Logic:**
  1. Pushes the branch to remote origin.
  2. Calls the GitHub API (or runs `gh pr create`) to open a pull request.
  3. If `auto_merge` is true and the verdict is `PASS`, merges the PR (`gh pr merge --merge --delete-branch`), updates main, and deletes the local worktree and branch.

---

## 4. Workflow DAG Wiring

We can configure two main workflow classes under `app/workflows/`:

### `SDLCFlowWorkflow` (Sequential shared-worktree flow)
Executes tasks sequentially in a single worktree. The `TaskContext` routes execution through a task loop:
```
SetupWorktreeNode ──> EnumerateTasksNode ──> LoadStateNode
                              │
                    ┌─────────▼─────────┐
                    │  UpdateTaskStatus │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │ ImplementTaskNode │◄──────────┐
                    └─────────┬─────────┘           │
                              │                     │ Retry
                    ┌─────────▼─────────┐           │
                    │   TestTaskNode    │           │
                    └─────────┬─────────┘           │
                              │                     │
                    ┌─────────▼─────────┐           │
                    │  TriageTaskNode   ├───────────┘
                    └─────────┬─────────┘
                              │
                              ├──► (Bail) ──┐
                              ▼             ▼
                        [Next Task] ──> WrapUpNode ──> PullRequestNode
                              │             ▲
                              ▼             │
                    ConsolidatedReviewNode ─┘ (Pass/Broad Fail)
                              │
                              └─► (Localized Fail) ──► ImplementTaskNode
```

### `SDLCRunWorkflow` (In-place, report-based execution)
This workflow is designed to execute task operations in-place (without a worktree) and supports resume operations. It checks for local report files at the start and skips straight to the next unrun stage (`implement`, `test`, `review`, `document`, or `wrap-up`).
