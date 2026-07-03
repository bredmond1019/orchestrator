---
type: Reference
title: Architect Prompt
description: Documentation for architect-prompt
doc_id: architect-prompt
layer: [meta]
status: active
related: [synthesis, sdlc-workflow-nodes-design]
---

You are a Principal Software Architect specializing in code analysis, systems integration, and
  compiler/orchestrator design.

    I am translating a JS-based workflow engine (.claude/workflows/) and a Python-subprocess-based CLI wrapper
  system (reference-repos/tac-N/adws) into a unified, Python-native workflow engine using FastAPI, Celery, and
  a DAG of execution Nodes in this repository.

    Analyze all the attached codebase files and documentation. Pay extra attention to:
    1. **Slash Commands Reference:** `/Users/brandon/Dev/agentic-portfolio/base-template/.
  claude/commands/README.md`
    2. **Workflow Documentation:** `/Users/brandon/Dev/agentic-portfolio/core/orchestrator/docs/workflows.md`
  (and any related docs under `/Users/brandon/Dev/agentic-portfolio/core/docs/workflows`)
    3. **First-Pass Node Design:** `/Users/brandon/Dev/agentic-portfolio/core/orchestrator/docs/sdlc-workflow-
  nodes-design.md`
    4. **API Reference:** `/Users/brandon/Dev/agentic-portfolio/core/orchestrator/docs/api-reference.md`
    5. **Active JS Engines:** `.claude/workflows/sdlc-flow.js`, `sdlc-run.js`, `sdlc-block.js`, and `sdlc-
  task.js`
    6. **Reference Integration Repos:** `/reference-repos/` (to see how Python-subprocess integration has been
  handled previously)

    ### Core Context & Objective
    Our current workflow tracks project progression via:
    - `planning/state.json` (which correlates to the `master-plan.md` progress tracker).
    - High-level slash commands used sequentially: `/generate-master-plan` -> `/generate-tasks` (for a block
  of work) -> `/breakdown` (if tasks need sub-steps) -> `/sdlc-flow` or `/sdlc-run --from implement` (which
  execute the developer loop).
    - The JS workflows (`sdlc-flow.js`, `sdlc-run.js`) are orchestrations of individual slash commands:
  `/generate-tasks`, `/implement`, `/test`, `/fix`, `/review`, `/wrap-up`, etc.

    **Key Architectural Shifts:**
    1. **Machine-Parsable Tasks:** Currently, the `/generate-tasks` command produces a markdown file (`tasks.
  md` with `### N.` task headings). We want this task-generation step to produce a **machine-parsable JSON
  object** (similar in structure to our `state.json`) for cleaner, more robust node routing and validation,
  while keeping it aligned with our orchestration state.
    2. **Subprocess/CLI to Python-Native Nodes:** While the `reference-repos` (e.g. `adws`) demonstrate
  programmatic ways to wrap the Claude CLI and parse its stream-json output, we want to adapt these concepts
  into our native Python node architecture (`app/core/nodes/` and `app/workflows/`) using direct LLM/SDK calls
  (like `ClaudeCodeModel` and `ModelProvider.CLAUDE_CODE_SDK` already in our code).

    Write a comprehensive, deep-dive architectural synthesis explaining how all variables, states, and systems
  connect. Your response will be fed directly into Claude 3.5 Sonnet to write concrete Python code, so be
  highly technical and precise.

    ---

    ### Structure your synthesis into the following sections:

    #### 1. Task Generation & Machine-Parsable Schema
    *   **Structured JSON vs Markdown Tasks:** Detail a proposed JSON schema for the output of `/generate-
  tasks` (or `GenerateTasksNode`) to make tasks machine-parsable. Show how it connects to `planning/state.
  json` and task loop progression.
    *   **Task List Ingestion:** Explain how the workflow can dynamically load and trace progress through this
  JSON-based task list, as opposed to grepping markdown files for `### N.` headings.

    #### 2. Slash Command Logic & State Integration
    *   **The Command Suite:** Map how `/generate-tasks`, `/generate-master-plan`, `/implement`, `/test`,
  `/fix`, `/review`, and `/wrap-up` behave individually, including their inputs, outputs, and side-effects.
    *   **Piping commands in Python:** Contrast the JS runtime command invocation (`agent()`, `runTests()`)
  with the Python CLI subprocess methods shown in `reference-repos`. Explain how we should adapt these
  commands into native `Node` executions.

    #### 3. Translation of JS Engines to Python Nodes
    *   **Design Alignment:** Review `/Users/brandon/Dev/agentic-portfolio/core/orchestrator/docs/sdlc-
  workflow-nodes-design.md`. For each of the proposed nodes, validate if the design matches the JS runtime
  mechanics of `sdlc-flow.js` and `sdlc-run.js`. Point out any missing stages, telemetry captures, or control
  gates.
    *   **Engine API Seams:** Read `/Users/brandon/Dev/agentic-portfolio/core/orchestrator/docs/api-reference.
  md`. Map how the new nodes will leverage existing Python primitives like `Node`, `AgentNode`, `RouterNode`,
  `TaskContext`, and `WorkflowSchema`.

    #### 4. Git & Worktree Lifecycle
    *   **Workspace Management:** Step-by-step commands for creating, checking out, and clean-up/merging of
  branches and sparse-checkout worktrees under `trees/` as done in `sdlc-flow.js` and `sdlc-task.js`.
    *   **Isolation and Port Mapping:** Address how the Python workflows can safely run tasks concurrently
  (like `sdlc-block.js` does with `sdlc-task.js`), avoiding database, port, or workspace collisions.

    #### 5. The Validation & Harness Engine
    *   **harness.json Mapping:** Detail how the Python nodes should parse and execute the 5 check types
  defined in `harness.json` (`command`, `baseline-diff`, `count-delta`, `warning-scan`, `forbidden-pattern-
  scan`), and the documentation `emoji-gate`.
    *   **Baselines and Reporting:** Detail how baseline snaps are captured before implementation and checked
  during the test/validate phase.

    #### 6. Retry, Triage, and Model Tiering
    *   **Triage and Loop Control:** Explain the exact rules for routing failures to `RETRYABLE` vs `MAJOR`
  (immediate-bail).
    *   **Model Tiering & Escalation:** Detail the model hierarchy (e.g. Haiku for parsing/scouting/testing,
  Sonnet for implementation/documentation, and Opus for planning/final-review/escalated fixes) and explain how
  the Python runtime should dynamically inject these choices on a per-node basis.

    #### 7. Unified Data Flow Map
    *   Provide a single step-by-step sequence diagram or data flow path from the initialization of a block in
  `state.json` through implementation, testing, review, wrap-up, and PR merge.
    ```***