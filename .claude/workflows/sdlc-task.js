// =============================================================================
// sdlc-task — Parallel-Safe SDLC Pipeline with Auto-Managed Worktree
// =============================================================================
//
// A parallel-safe variant of sdlc-run that:
//   1. Auto-creates a git worktree for this specific task
//   2. Runs the full SDLC pipeline inside that worktree
//   3. Defers STATUS.md / DEVLOG.md updates to a task log file
//      (applied at merge time via /clean-worktree)
//
// This lets multiple tasks run simultaneously with zero shared file writes,
// eliminating merge conflicts. sdlc-run.js is unchanged and still available
// for sequential use.
//
// USAGE
//   /sdlc-task phase0-blockC 8    runs task 8 in an isolated worktree
//
//   Task number is REQUIRED. For full-block runs use /sdlc-run instead.
//
// PIPELINE STAGES (in order)
//   Worktree   → auto-create (or suffix-increment) isolated git worktree
//   Scout      → detect current stage from report files
//   Plan       → generate task spec (skipped if spec already exists)
//   Implement  → execute the task from spec
//   Fix        → targeted fixes for FAIL/PARTIAL review (up to 3 attempts)
//   Test       → 8-check suite: imports, ruff, pylint, pytest collect + full
//   Review     → fresh pytest + acceptance criteria; verdict gates next stage
//   Document   → surgical patches to docs/ (gates on PASS verdict)
//   Wrap-up    → write task log file (defers STATUS/DEVLOG to merge time)
//
// WHAT RUNS IN THE WORKTREE vs. MAIN
//   Worktree branch: all code, test, doc, and report changes
//   Main (at merge): STATUS.md + DEVLOG.md updates (applied by /clean-worktree)
//
// MERGE FLOW
//   After pipeline completes:
//     /clean-worktree <branchName>
//   This: merges the branch → applies the task log → updates STATUS/DEVLOG →
//         commits → removes worktree → deletes branch.
//
// WORKTREE PATH CONVENTION
//   trees/<blockId-lowercased>-task<N>   e.g. trees/phase0-blockc-task8
//   If that name is taken, auto-increments: trees/phase0-blockc-task8-2, -3, etc.
//   The actual branch name is always reported in the pipeline output and task log.
//
// RESUMPTION
//   Same as sdlc-run: the scout checks which report files exist.
//   If the worktree already exists at setup time, a new suffixed worktree is
//   created rather than resuming the old one. This ensures clean state for retries.
//
// COMMIT STRATEGY (same as sdlc-run)
//   feat: implement <stem>         implement agent
//   fix: fix pass N for <stem>     fix agent (one per pass)
//   docs: update docs for <stem>   document agent
//   chore: wrap up <stem>          finalize agent (reports + task log)
//
// =============================================================================

export const meta = {
  name: 'sdlc-task',
  description: 'Run the SDLC pipeline for a single task in an isolated worktree — parallel-safe variant of sdlc-run',
  whenToUse: 'When running a specific numbered task in parallel with other tasks. Task number is required. Usage: /sdlc-task phase0-blockC 8',
  phases: [
    { title: 'Worktree',   detail: 'Auto-create (or suffix-increment) git worktree for isolated execution' },
    { title: 'Scout',      detail: 'Determine current pipeline stage from report files' },
    { title: 'Plan',       detail: 'Generate task spec (only if spec file does not yet exist)' },
    { title: 'Implement',  detail: 'Execute the task' },
    { title: 'Fix',        detail: 'Targeted fixes for FAIL/PARTIAL review' },
    { title: 'Test',       detail: 'Run 8-check validation suite in the worktree' },
    { title: 'Review',     detail: 'Verify acceptance criteria; issue verdict' },
    { title: 'Document',   detail: 'Patch docs/ (gates on PASS verdict)' },
    { title: 'Wrap-up',    detail: 'Write task log file (STATUS/DEVLOG deferred to merge time)' },
  ]
}

// ----------------------------------------------------------------
// Parse args: REQUIRE "phase0-blockC 8" — task number is mandatory
// ----------------------------------------------------------------
const rawArgs = typeof args === 'string' ? args.trim() : ''
if (!rawArgs) {
  log('ERROR: No arguments provided.')
  log('Usage: /sdlc-task phase0-blockC 8')
  log('Task number is required. For full-block runs, use /sdlc-run instead.')
  return { error: 'Missing required arguments: block ID and task number' }
}

const parts = rawArgs.split(/\s+/)
const blockId = parts[0]
const taskNumber = parts.length > 1 ? parseInt(parts[1], 10) : null

if (taskNumber === null || isNaN(taskNumber)) {
  log(`ERROR: Task number is required but not provided (got: "${rawArgs}").`)
  log('Usage: /sdlc-task phase0-blockC 8')
  log('For full-block runs use /sdlc-run instead.')
  return { error: 'Task number required', rawArgs }
}

const specFile    = `planning/tasks/${blockId}/tasks.md`
const stem        = `${blockId}-task${taskNumber}`
const reportsDir  = `planning/tasks/${blockId}/reports`
const taskPrefix  = `task${taskNumber}-`
const implementReport = `${reportsDir}/${taskPrefix}implement.md`
const testReport      = `${reportsDir}/${taskPrefix}test.md`
const reviewReport    = `${reportsDir}/${taskPrefix}review.md`
const documentReport  = `${reportsDir}/${taskPrefix}document.md`
const workflowReport  = `${reportsDir}/${taskPrefix}workflow.md`
const logFile         = `${reportsDir}/${taskPrefix}log.md`
const breakdownFile   = `planning/tasks/${blockId}/breakdown.md`

// Base branch name (suffix may be appended by setup agent)
const baseBranchName = `${blockId}-task${taskNumber}`.toLowerCase().replace(/[^a-z0-9-]/g, '-')

log(`Target: ${blockId} task ${taskNumber}`)
log(`Spec: ${specFile} | Stem: ${stem}`)

// ----------------------------------------------------------------
// Schemas
// ----------------------------------------------------------------
const SETUP_SCHEMA = {
  type: 'object',
  required: ['branchName', 'worktreePath', 'wasCreated'],
  properties: {
    branchName:    { type: 'string', description: 'Actual branch name used (may have -2, -3 suffix if base was taken)' },
    worktreePath:  { type: 'string', description: 'Absolute path to the worktree directory' },
    wasCreated:    { type: 'boolean', description: 'true if a new worktree was created, false if it already existed' },
    notes:         { type: 'string' }
  }
}

const SCOUT_SCHEMA = {
  type: 'object',
  required: ['startStage', 'specFileExists', 'blockStatus', 'existingReports', 'statusSummary'],
  properties: {
    startStage: {
      type: 'string',
      enum: ['generate-tasks', 'implement', 'fix', 'test', 'review', 'document', 'wrap-up'],
    },
    specFileExists:    { type: 'boolean' },
    blockStatus: {
      type: 'string',
      enum: ['Not started', 'In progress', 'Done', 'Blocked', 'Skipped', 'Unknown'],
    },
    existingReports:   { type: 'array', items: { type: 'string' } },
    reviewVerdict:     { type: 'string', description: 'PASS, FAIL, PARTIAL, or empty string' },
    currentFocus:      { type: 'string' },
    lastDevlogEntry:   { type: 'string' },
    statusSummary:     { type: 'string' },
    discrepancies:     { type: 'string' }
  }
}

const STAGE_SCHEMA = {
  type: 'object',
  required: ['reportFile', 'success'],
  properties: {
    reportFile:     { type: 'string' },
    success:        { type: 'boolean' },
    filesModified:  { type: 'array', items: { type: 'string' } },
    commitHash:     { type: 'string' },
    notes:          { type: 'string' }
  }
}

const TEST_SCHEMA = {
  type: 'object',
  required: ['reportFile', 'allPassed', 'passCount', 'failCount'],
  properties: {
    reportFile:   { type: 'string' },
    allPassed:    { type: 'boolean' },
    passCount:    { type: 'integer' },
    failCount:    { type: 'integer' },
    failedTests:  { type: 'array', items: { type: 'string' } },
    notes:        { type: 'string' }
  }
}

const REVIEW_SCHEMA = {
  type: 'object',
  required: ['reportFile', 'verdict'],
  properties: {
    reportFile:      { type: 'string' },
    verdict:         { type: 'string', enum: ['PASS', 'FAIL', 'PARTIAL'] },
    failureReasons:  { type: 'array', items: { type: 'string' } },
    unmetCriteria:   { type: 'array', items: { type: 'string' } },
    notes:           { type: 'string' }
  }
}

const LOG_SCHEMA = {
  type: 'object',
  required: ['logFile', 'applied'],
  properties: {
    logFile:    { type: 'string' },
    applied:    { type: 'boolean' },
    nextFocus:  { type: 'string', description: 'The Current focus string written to the log file' },
    notes:      { type: 'string', description: 'Any decisions that should be added to DECISIONS.md' }
  }
}

const FINALIZE_SCHEMA = {
  type: 'object',
  required: ['workflowReportFile', 'commitMessage'],
  properties: {
    workflowReportFile: { type: 'string' },
    commitMessage:      { type: 'string' },
    commitHash:         { type: 'string' },
    notes:              { type: 'string' }
  }
}

// ----------------------------------------------------------------
// Stage results accumulator
// ----------------------------------------------------------------
const stageResults = []

// ================================================================
// PHASE 0: WORKTREE SETUP — auto-create isolated worktree
// ================================================================
phase('Worktree')
log(`Setting up worktree for ${stem}...`)

const setupResult = await agent(`
You are the worktree setup agent. Your job is to create (or locate) an isolated git worktree
for this pipeline run. All bash commands run from the MAIN REPO ROOT (your current CWD).

Target:
  Block:          ${blockId}
  Task:           ${taskNumber}
  Base name:      ${baseBranchName}

STEP 1 — Get the absolute path to the repo root:
  Run: git rev-parse --show-toplevel
  Store the output as repoRoot (trim whitespace).

STEP 2 — Find a free worktree name using this exact algorithm:

  Start with candidate = "${baseBranchName}" and work through each suffix in turn:

  Iteration 1 — candidate = "${baseBranchName}":
    Run: git worktree list | grep "trees/${baseBranchName}"
    Run: git branch --list "${baseBranchName}"
    If BOTH return nothing → "${baseBranchName}" is free. Use it. Skip to STEP 3.

  Iteration 2 — candidate = "${baseBranchName}-2":
    Run: git worktree list | grep "trees/${baseBranchName}-2"
    Run: git branch --list "${baseBranchName}-2"
    If BOTH return nothing → "${baseBranchName}-2" is free. Use it. Skip to STEP 3.

  Iteration 3 — candidate = "${baseBranchName}-3":
    ... same pattern ...

  Continue through "-10" as the cap. Use the first free candidate found.
  Store the chosen name as branchName.

STEP 3 — Create the worktree:
  Run these commands in order (replace [branchName] and [repoRoot] with actual values):

  a. mkdir -p trees
  b. git worktree add --no-checkout trees/[branchName] -b [branchName]
  c. git -C trees/[branchName] sparse-checkout init --cone
  d. git -C trees/[branchName] sparse-checkout set app tests docs planning .claude
  e. git -C trees/[branchName] checkout
  f. if [ -f .env ]; then cp .env trees/[branchName]/.env; fi
  g. git -C trees/[branchName] commit --allow-empty -m "chore: init worktree [branchName]"

STEP 4 — Verify:
  Run: git worktree list
  Run: ls trees/[branchName]/
  Confirm the worktree exists and contains app/, tests/, planning/, .claude/ directories.

STEP 5 — Compute the absolute worktree path:
  worktreePath = repoRoot + "/trees/" + branchName

Return your result using the StructuredOutput tool:
  branchName:   the final chosen branch name (e.g. "${baseBranchName}" or "${baseBranchName}-2")
  worktreePath: the ABSOLUTE path to the worktree (e.g. /Users/brandon/Dev/.../trees/${baseBranchName})
  wasCreated:   true (a new worktree was created)
  notes:        any issues encountered
`, { label: 'worktree-setup', schema: SETUP_SCHEMA, phase: 'Worktree' })

if (!setupResult) {
  log('Worktree setup agent returned null — aborting pipeline')
  return { error: 'Worktree setup failed', blockId, taskNumber, stem }
}

const { branchName, worktreePath } = setupResult
log(`Worktree ready: ${worktreePath} (branch: ${branchName})`)
stageResults.push({ stage: 'worktree-setup', ...setupResult, success: true })

// ----------------------------------------------------------------
// Build the worktree path injection header — prepended to EVERY agent prompt
// ----------------------------------------------------------------
const W = `
╔══════════════════════════════════════════════════════════════════╗
║  WORKING DIRECTORY: ${worktreePath}
║
║  You are in a git worktree — NOT the main repo.
║  Shell state does NOT persist between Bash tool calls.
║  START EVERY Bash tool call with:
║    cd ${worktreePath} &&
║
║  "repo root" = ${worktreePath}
║  "app/ directory" = ${worktreePath}/app
║  Relative paths (planning/tasks/...) resolve from: ${worktreePath}
╚══════════════════════════════════════════════════════════════════╝
`

// ================================================================
// PHASE 1: SCOUT — determine current pipeline stage
// ================================================================
phase('Scout')

const scout = await agent(`${W}
You are the pipeline scout for the SDLC workflow system.

Target:
  Block ID:    ${blockId}
  Task number: ${taskNumber}
  Spec file:   ${specFile}
  Report stem: ${stem}
  Reports dir: ${reportsDir}

Your job is to determine which SDLC stage to start from, based on which report files exist.
Run these checks using the Bash tool (all commands start with: cd ${worktreePath} &&):

STEP 1 — Check spec file:
  cd ${worktreePath} && ls -la ${specFile} 2>/dev/null && echo "SPEC_EXISTS" || echo "SPEC_MISSING"

STEP 2 — Check report files:
  cd ${worktreePath} && ls ${implementReport} 2>/dev/null && echo "HAS_IMPLEMENT" || echo "NO_IMPLEMENT"
  cd ${worktreePath} && ls ${testReport} 2>/dev/null && echo "HAS_TEST" || echo "NO_TEST"
  cd ${worktreePath} && ls ${reviewReport} 2>/dev/null && echo "HAS_REVIEW" || echo "NO_REVIEW"
  cd ${worktreePath} && ls ${documentReport} 2>/dev/null && echo "HAS_DOCUMENT" || echo "NO_DOCUMENT"
  cd ${worktreePath} && ls ${reportsDir}/*.md 2>/dev/null | head -20 || echo "NO_BLOCK_REPORTS"

STEP 3 — Read STATUS.md:
  cd ${worktreePath} && head -60 planning/STATUS.md

STEP 4 — Read recent DEVLOG (at the worktree root):
  cd ${worktreePath} && head -60 DEVLOG.md

STEP 5 — If review report exists, extract the verdict:
  cd ${worktreePath} && grep -iE "\\*\\*Verdict|## Verdict|^Verdict:" ${reviewReport} 2>/dev/null | head -5 || echo "NO_REVIEW_REPORT"

STEP 6 — Determine startStage using this EXACT priority order:
  1. Spec file MISSING → "generate-tasks"
  2. Spec exists, no implement report → "implement"
  3. Implement report exists, no test report → "test"
  4. Test report exists, no review report → "review"
  5. Review report with FAIL or PARTIAL verdict → "fix"
  6. Review report with PASS verdict, no document report → "document"
  7. Document report exists → "wrap-up"

STEP 7 — Find this block's status in STATUS.md progress table. Look for a row containing
  "${blockId}" and extract its Status column value.

STEP 8 — Note any discrepancy between DEVLOG and report files.

Return your findings using the StructuredOutput tool.
`, { label: 'scout', schema: SCOUT_SCHEMA, phase: 'Scout' })

if (!scout) {
  log('Scout agent failed — cannot determine pipeline state, aborting')
  return { error: 'Scout failed', blockId, taskNumber, stem }
}

log(`Scout: start from "${scout.startStage}" | block status: "${scout.blockStatus}"`)
if (scout.discrepancies) log(`Discrepancies: ${scout.discrepancies}`)
if (scout.statusSummary) log(scout.statusSummary)

// Block "Not started" warning — do NOT edit STATUS.md in the worktree.
// STATUS.md changes are always deferred to the task log (applied at merge time).
// If the block needs to be flipped before parallel tasks start, run /start-block first.
if (scout.blockStatus === 'Not started') {
  log(`Note: Block "${blockId}" is "Not started" in STATUS.md.`)
  log(`The task log will record the block status flip — applied when this branch merges to main.`)
  log(`To update STATUS.md immediately (e.g. before other parallel tasks start), run /start-block ${blockId} from the main session.`)
}

let currentStage = scout.startStage
let reviewAttempts = 0
const MAX_REVIEW_ATTEMPTS = 3
let lastReviewResult = null

// ================================================================
// PHASE 2: PLAN — generate-tasks (only if spec file missing)
// ================================================================
if (currentStage === 'generate-tasks') {
  phase('Plan')
  log('Spec file not found — running generate-tasks...')

  const genResult = await agent(`${W}
You need to generate the task spec for block "${blockId}".

Spec file to create: ${specFile}
Worktree root: ${worktreePath}

Instructions:

1. Read planning/MASTER_PLAN.md (at the worktree root) — find the section covering "${blockId}".
   Run: cd ${worktreePath} && cat planning/MASTER_PLAN.md

2. Read planning/Agentic_Engineering_Projects_and_Learning_Plan.md — find the matching section.

3. Read .claude/CLAUDE.md — note all standing rules and the known bugs table.
   Wait, read CLAUDE.md from the main repo: cd ${worktreePath} && cat CLAUDE.md

4. Read an existing spec as format reference:
   cd ${worktreePath} && cat planning/tasks/phase0-blockC/tasks.md

   Also create the block directory structure now if it does not exist:
   cd ${worktreePath} && mkdir -p planning/tasks/${blockId}/reports

5. Write ${specFile} (absolute path: ${worktreePath}/${specFile}) following the standard format.

   Rules:
   - Every workflow task must include writing tests (CLAUDE.md Rule 1)
   - The final task must always be "Validate"
   - Tasks should be numbered ### 1., ### 2., etc.
   - Include exact file paths and class/method names

Return using StructuredOutput:
  reportFile: "${specFile}"
  success: true if written successfully
  filesModified: ["${specFile}"]
  notes: brief note about what was generated
`, { label: 'generate-tasks', schema: STAGE_SCHEMA, phase: 'Plan' })

  if (!genResult || !genResult.success) {
    log('generate-tasks failed — aborting pipeline')
    stageResults.push({ stage: 'generate-tasks', success: false })
    return { error: 'generate-tasks failed', blockId, taskNumber, stem, stageResults }
  }
  stageResults.push({ stage: 'generate-tasks', ...genResult })
  log(`Task spec written: ${genResult.reportFile}`)
  currentStage = 'implement'
}

// ================================================================
// PHASES 3–5: IMPLEMENT → (FIX →) TEST → REVIEW (with retry loop)
// ================================================================
while (['implement', 'fix', 'test', 'review'].includes(currentStage) && reviewAttempts < MAX_REVIEW_ATTEMPTS) {

  // ----------------------------------------------------------
  // IMPLEMENT
  // ----------------------------------------------------------
  if (currentStage === 'implement') {
    phase('Implement')
    log('Running implement...')

    const implResult = await agent(`${W}
You are the implementation agent for the SDLC pipeline.

Target:
  Block:           ${blockId}
  Task:            Task ${taskNumber} only
  Spec file:       ${specFile}
  Report to write: ${implementReport}
  Worktree root:   ${worktreePath}

Instructions:

1. Read CLAUDE.md — internalize all standing rules and known bugs.
   Run: cd ${worktreePath} && cat CLAUDE.md

2. Read the spec file, focusing on the "### ${taskNumber}." section:
   Run: cd ${worktreePath} && cat ${specFile}
   Implement ONLY the "### ${taskNumber}." section. Do not implement other tasks.

2.5. Check for an optional breakdown file (more granular sub-steps written by /breakdown):
   Run: cd ${worktreePath} && ls ${breakdownFile} 2>/dev/null && echo "BREAKDOWN_EXISTS" || echo "NO_BREAKDOWN"

   If BREAKDOWN_EXISTS:
     Read ${worktreePath}/${breakdownFile}
     Find the "### Step ${taskNumber}:" section — use its atomic sub-steps as the primary
     execution guide for HOW to implement this task.
     Inline "Verify:" commands are live checkpoints — run each before moving to the next sub-step.
     tasks.md is authoritative for scope/acceptance criteria; breakdown.md is authoritative for HOW.

   If NO_BREAKDOWN: proceed using tasks.md only.

3. Execute each step methodically using Read, Edit, Write, and Bash tools.
   ALL file paths must be absolute (under ${worktreePath}) OR use:
     cd ${worktreePath} && <command>

4. As you implement:
   - Follow every CLAUDE.md rule (no hardcoded prompts, no deployment logic in nodes, etc.)
   - Write tests for all new code (CLAUDE.md Rule 1 — no exceptions)
   - Never hardcode system prompts in Python — use .j2 files via PromptManager

5. Run the Validation Commands from the spec to confirm correctness:
   cd ${worktreePath} && uv run pytest 2>&1 | tail -20
   cd ${worktreePath} && uv run ruff check app/ 2>&1 | tail -20

6. Write the implementation report:
   Absolute path: ${worktreePath}/${implementReport}

   Format:
   # Implementation Report — ${stem}

   **Date:** [run: cd ${worktreePath} && date +%Y-%m-%d]
   **Plan:** ${specFile}
   **Scope:** Task ${taskNumber}

   ## What Was Built or Changed
   - [bullet list with file paths]

   ## Files Created or Modified
   | File | Action |
   |---|---|
   | path/to/file.py | created / modified |

   ## Validation Output
   **Commands run:**
   \`\`\`
   [commands]
   \`\`\`
   **Results:**
   \`\`\`
   [actual output]
   \`\`\`
   Status: PASSED / FAILED

   ## Decisions and Trade-offs
   [non-obvious choices]

   ## Follow-up Work
   [anything deferred]

   ## git diff --stat
   \`\`\`
   [run: cd ${worktreePath} && git diff --stat]
   \`\`\`

7. Commit your changes. Run from the worktree:
   cd ${worktreePath} && git status
   Stage files explicitly by name (never git add -A or git add .):
     cd ${worktreePath} && git add app/file1.py tests/file2.py ${implementReport}
   Commit using HEREDOC:
     cd ${worktreePath} && git commit -m "$(cat <<'EOF'
     feat: implement ${stem}

     EOF
     )"
   Run: cd ${worktreePath} && git log --oneline -1

Return using StructuredOutput:
  reportFile: "${implementReport}"
  success: true if implementation completed without critical errors
  filesModified: array of source files created or modified
  commitHash: 7-character short hash from git log --oneline -1
  notes: one-line summary
`, { label: 'implement', schema: STAGE_SCHEMA, phase: 'Implement' })

    if (!implResult) {
      log('Implement agent returned null — aborting pipeline')
      stageResults.push({ stage: 'implement', success: false, notes: 'Agent returned null' })
      break
    }
    stageResults.push({ stage: 'implement', ...implResult })
    if (!implResult.success) {
      log('Implement reported failure — aborting pipeline')
      break
    }
    currentStage = 'test'
  }

  // ----------------------------------------------------------
  // FIX (review retry path)
  // ----------------------------------------------------------
  if (currentStage === 'fix') {
    phase('Fix')
    const fixPass = reviewAttempts + 1
    log(`Running fix (pass ${fixPass}) — targeting review failures...`)

    const fixResult = await agent(`${W}
You are the fix agent for the SDLC pipeline. Make targeted fixes for the failures identified
in the last review — NOT a full re-implementation.

Target:
  Block:                ${blockId}
  Task:                 Task ${taskNumber}
  Review report:        ${reviewReport}
  Prior implement report: ${implementReport}
  Report to write:      ${implementReport}  ← overwrites this slot (Fix Pass ${fixPass})
  Worktree root:        ${worktreePath}

GATE CHECKS (do these first):
1. cd ${worktreePath} && ls ${reviewReport} 2>/dev/null && echo EXISTS || echo MISSING
   If MISSING → stop, return success: false, notes: "No review report found."
2. cd ${worktreePath} && grep -i "verdict" ${reviewReport} | head -3
   If verdict is PASS → stop, return success: false, notes: "Review verdict is already PASS."

Instructions:

1. Read the review report:
   cd ${worktreePath} && cat ${reviewReport}
   Extract: failing criteria, Issues Found section, Fresh Test Results.

2. Read the prior implement report:
   cd ${worktreePath} && cat ${implementReport}

3. If a breakdown file exists, check the relevant sub-steps for original intent:
   Run: cd ${worktreePath} && ls ${breakdownFile} 2>/dev/null && echo EXISTS || echo MISSING
   If EXISTS: read ${worktreePath}/${breakdownFile} and find the "### Step ${taskNumber}:" section.
   Use it to understand what the original implementation was supposed to do for the failing criterion.
   Do NOT re-implement from scratch — use it only as context for the targeted fix.

4. Make MINIMUM targeted changes to address the failing criteria.
   Fix ONLY what the review identified as failing.

5. Run the Validation Commands from the spec:
   cd ${worktreePath} && cat ${specFile} | grep -A 20 "## Validation Commands"
   Then run those commands.

6. Overwrite the implement report at: ${worktreePath}/${implementReport}

   Format:
   # Fix Pass ${fixPass} — ${stem}

   **Date:** [run: cd ${worktreePath} && date +%Y-%m-%d]
   **Plan:** ${specFile}
   **Fix pass:** ${fixPass}

   ## Failures Addressed
   [each failing criterion and how it was fixed]

   ## Changes Made
   - [targeted changes with file paths]

   ## Files Created or Modified
   | File | Action |
   |---|---|
   [IMPORTANT: include ALL files from prior implement report PLUS newly touched files]

   ## Validation Output
   [commands and actual output]
   Status: PASSED / FAILED

   ## git diff --stat
   \`\`\`
   [run: cd ${worktreePath} && git diff --stat]
   \`\`\`

7. Commit your changes:
   cd ${worktreePath} && git status
   cd ${worktreePath} && git add <changed files> ${implementReport}
   cd ${worktreePath} && git commit -m "$(cat <<'EOF'
   fix: fix pass ${fixPass} for ${stem}
   EOF
   )"
   cd ${worktreePath} && git log --oneline -1

Return using StructuredOutput:
  reportFile: "${implementReport}"
  success: true if fixes applied and validation passed
  filesModified: files changed this pass only
  commitHash: 7-character short hash
  notes: one-line summary of what was fixed
`, { label: `fix-${fixPass}`, schema: STAGE_SCHEMA, phase: 'Fix' })

    if (!fixResult) {
      log('Fix agent returned null — aborting pipeline')
      stageResults.push({ stage: 'fix', attempt: fixPass, success: false, notes: 'Agent returned null' })
      break
    }
    stageResults.push({ stage: 'fix', attempt: fixPass, ...fixResult })
    if (!fixResult.success) {
      log(`Fix pass ${fixPass} reported failure — aborting pipeline`)
      break
    }
    currentStage = 'test'
  }

  // ----------------------------------------------------------
  // TEST
  // ----------------------------------------------------------
  if (currentStage === 'test') {
    phase('Test')
    log('Running 8-check test suite...')

    const testResult = await agent(`${W}
You are the test agent for the SDLC pipeline. Run the 8-check validation suite in the worktree.

Target:
  Spec:            ${specFile}
  Report to write: ${testReport}
  Worktree root:   ${worktreePath}

Run ALL 8 checks IN ORDER. Capture full output (stdout + stderr) for each.
All commands start with: cd ${worktreePath} &&

CHECK 1 — App import:
  cd ${worktreePath}/app && uv run python -c "import main" 2>&1
  echo "CHECK1_EXIT:$?"

CHECK 2 — Worker import:
  cd ${worktreePath}/app && uv run python -c "import worker.config" 2>&1
  echo "CHECK2_EXIT:$?"

CHECK 3 — Database session import:
  cd ${worktreePath}/app && uv run python -c "import database.session" 2>&1
  echo "CHECK3_EXIT:$?"

CHECK 4 — Repository import:
  cd ${worktreePath}/app && uv run python -c "import database.repository" 2>&1
  echo "CHECK4_EXIT:$?"

CHECK 5 — Ruff lint:
  cd ${worktreePath} && uv run ruff check app/ 2>&1
  echo "CHECK5_EXIT:$?"

CHECK 6 — Pylint:
  cd ${worktreePath} && uv run pylint app/ 2>&1
  echo "CHECK6_EXIT:$?"

CHECK 7 — Pytest collect:
  cd ${worktreePath} && uv run pytest --collect-only -q 2>&1
  echo "CHECK7_EXIT:$?"

CHECK 8 — Pytest full:
  cd ${worktreePath} && uv run pytest 2>&1
  echo "CHECK8_EXIT:$?"

Write the test report to: ${worktreePath}/${testReport}

Format:
# Test Report — ${stem}

**Date:** [run: date +%Y-%m-%d]
**Spec:** ${specFile}
**Scope:** Task ${taskNumber}

## Summary

| Test | Result | Error |
|---|---|---|
[FAILED rows first, then PASSED rows]

## Full Results (JSON)
\`\`\`json
[array of {test_name, passed, execution_command, test_purpose, error}]
\`\`\`

Return using StructuredOutput:
  reportFile: "${testReport}"
  allPassed: true only if ALL 8 checks passed (exit code 0)
  passCount: integer
  failCount: integer
  failedTests: array of test_name strings for failed checks
  notes: one-line summary
`, { label: 'test', schema: TEST_SCHEMA, phase: 'Test' })

    if (!testResult) {
      log('Test agent returned null — recording failure, continuing to review')
      stageResults.push({ stage: 'test', attempt: reviewAttempts + 1, allPassed: false, success: false, notes: 'Agent returned null' })
    } else {
      stageResults.push({ stage: 'test', attempt: reviewAttempts + 1, ...testResult, success: testResult.allPassed })
      if (!testResult.allPassed) {
        log(`Test failures (${testResult.failCount}): ${(testResult.failedTests || []).join(', ')}`)
      } else {
        log(`All ${testResult.passCount} checks passed`)
      }
    }
    currentStage = 'review'
  }

  // ----------------------------------------------------------
  // REVIEW
  // ----------------------------------------------------------
  if (currentStage === 'review') {
    phase('Review')
    reviewAttempts++
    log(`Running review (attempt ${reviewAttempts}/${MAX_REVIEW_ATTEMPTS})...`)

    const reviewResult = await agent(`${W}
You are the review agent for the SDLC pipeline. Verify the implementation against the spec.

Target:
  Block:            ${blockId}
  Task:             Task ${taskNumber}
  Spec file:        ${specFile}
  Implement report: ${implementReport}
  Test report:      ${testReport}
  Report to write:  ${reviewReport}
  Worktree root:    ${worktreePath}

Instructions:

1. Read the spec file:
   cd ${worktreePath} && cat ${specFile}
   Extract the COMPLETE "## Acceptance Criteria" section.

2. Read the implement report:
   cd ${worktreePath} && cat ${implementReport}

3. Read the test report:
   cd ${worktreePath} && cat ${testReport}

4. Run FRESH authoritative tests (this result determines the verdict):
   cd ${worktreePath} && uv run pytest 2>&1

5. For each acceptance criterion, read relevant source files and determine:
   MET — fully satisfied
   PARTIAL — partially satisfied
   NOT_MET — not satisfied

6. Determine verdict:
   PASS — ALL criteria MET AND fresh pytest passes (exit 0)
   PARTIAL — some criteria PARTIAL, OR tests pass but some criteria not fully met
   FAIL — any criterion NOT_MET, OR fresh pytest fails
   (A fresh test failure ALWAYS prevents PASS)

7. Write the review report: ${worktreePath}/${reviewReport}

   Format:
   # Review Report — ${stem}

   **Date:** [run: date +%Y-%m-%d]
   **Spec:** ${specFile}
   **Scope:** Task ${taskNumber}
   **Verdict:** PASS / PARTIAL / FAIL

   ## Acceptance Criteria Check
   | Criterion | Status | Evidence |
   |---|---|---|
   | [criterion] | MET / PARTIAL / NOT_MET | [file:line or test name] |

   ## Fresh Test Results
   [pytest summary — pass/fail counts, failure output]

   ## Verdict: PASS / PARTIAL / FAIL
   [one paragraph explaining the verdict]

   ## Issues Found
   [specific problems — empty if PASS]

   ## Next Steps
   [what to do based on verdict]

Return using StructuredOutput:
  reportFile: "${reviewReport}"
  verdict: "PASS", "FAIL", or "PARTIAL"
  failureReasons: array of strings (empty if PASS)
  unmetCriteria: array of criterion texts that were NOT_MET or PARTIAL (empty if PASS)
  notes: one-line summary
`, { label: `review-${reviewAttempts}`, schema: REVIEW_SCHEMA, phase: 'Review' })

    if (!reviewResult) {
      log(`Review agent returned null (attempt ${reviewAttempts}) — treating as FAIL`)
      lastReviewResult = { verdict: 'FAIL', failureReasons: ['Review agent returned null'], unmetCriteria: [], reportFile: reviewReport }
      stageResults.push({ stage: 'review', attempt: reviewAttempts, verdict: 'FAIL', success: false, notes: 'Agent returned null' })
    } else {
      lastReviewResult = reviewResult
      stageResults.push({ stage: 'review', attempt: reviewAttempts, ...reviewResult, success: reviewResult.verdict === 'PASS' })
      log(`Review verdict: ${reviewResult.verdict} (attempt ${reviewAttempts}/${MAX_REVIEW_ATTEMPTS})`)
    }

    if (lastReviewResult.verdict === 'PASS') {
      currentStage = 'document'
    } else if (reviewAttempts < MAX_REVIEW_ATTEMPTS) {
      log(`Review ${lastReviewResult.verdict} — running fix pass ${reviewAttempts + 1}/${MAX_REVIEW_ATTEMPTS}...`)
      currentStage = 'fix'
    } else {
      log(`Review FAILED after ${MAX_REVIEW_ATTEMPTS} attempts — skipping to wrap-up with FAIL status`)
      currentStage = 'wrap-up'
    }
  }
} // end implement→fix→test→review retry loop

// ================================================================
// PHASE 6: DOCUMENT (gates on PASS verdict)
// ================================================================
if (currentStage === 'document') {
  phase('Document')
  log('Running document stage...')

  const docResult = await agent(`${W}
You are the documentation agent for the SDLC pipeline. Surgically patch docs/ in the worktree.

Target:
  Block:            ${blockId}
  Task:             Task ${taskNumber}
  Review report:    ${reviewReport}
  Implement report: ${implementReport}
  Report to write:  ${documentReport}
  Worktree root:    ${worktreePath}

Instructions:

1. Read the review report:
   cd ${worktreePath} && cat ${reviewReport}
   GATE CHECK: If the verdict is FAIL or PARTIAL, stop immediately.
   Return: success: false, notes: "Blocked — review verdict was not PASS".

2. Read the implement report:
   cd ${worktreePath} && cat ${implementReport}
   Find the "## Files Created or Modified" table.

3. For each source file in that table, find which docs/*.md files reference it:
   cd ${worktreePath} && grep -rl "ClassName\\|function_name\\|filename" docs/ 2>/dev/null

4. Read each relevant doc file and surgically patch ONLY affected sections:
   - Update class signatures, method lists, descriptions that changed
   - Add documentation for new public APIs
   - Never delete documented items that still exist
   - Use the Edit tool with absolute paths: ${worktreePath}/docs/filename.md

5. If docs/app-architecture-overview.md needs updating, add it to NEEDS_REVIEW
   in the document report but do NOT edit it directly.

6. Write the document report: ${worktreePath}/${documentReport}

   Format:
   # Documentation Report — ${stem}

   **Date:** [run: date +%Y-%m-%d]
   **Spec:** ${specFile}
   **Verdict gate:** PASS (confirmed)

   ## Docs Patched
   | Doc File | Section Updated | Change Summary |
   |---|---|---|

   ## Docs Flagged NEEDS_REVIEW
   [list any docs needing human review]

   ## Docs Clean (no changes needed)
   [docs checked but unchanged]

7. Commit your changes:
   cd ${worktreePath} && git status
   If no doc files were patched, commit just the report:
     cd ${worktreePath} && git add ${documentReport}
   If docs were patched:
     cd ${worktreePath} && git add docs/file1.md docs/file2.md ${documentReport}
   cd ${worktreePath} && git commit -m "$(cat <<'EOF'
   docs: update docs for ${stem}
   EOF
   )"
   cd ${worktreePath} && git log --oneline -1

Return using StructuredOutput:
  reportFile: "${documentReport}"
  success: true if docs checked and report written (even if no changes needed)
  filesModified: doc files actually patched (empty if none)
  commitHash: 7-character short hash
  notes: one-line summary
`, { label: 'document', schema: STAGE_SCHEMA, phase: 'Document' })

  if (!docResult) {
    stageResults.push({ stage: 'document', success: false, notes: 'Document agent returned null' })
    log('Document agent returned null')
  } else {
    stageResults.push({ stage: 'document', ...docResult })
    if (!docResult.success) {
      log(`Document stage blocked: ${docResult.notes}`)
    } else {
      log(`Docs updated: ${(docResult.filesModified || []).join(', ') || 'none needed changes'}`)
    }
  }
  currentStage = 'wrap-up'
}

// ================================================================
// PHASE 7: WRAP-UP — write task log (deferred STATUS/DEVLOG) + finalize
// ================================================================
phase('Wrap-up')

const finalVerdict = lastReviewResult?.verdict || 'NOT_REACHED'
const stageResultsSummary = stageResults
  .map(r => `${r.stage}${r.attempt ? `(#${r.attempt})` : ''}: ${r.success ? (r.verdict || 'OK') : 'FAILED'}`)
  .join(' → ')

log(`Wrap-up. Final verdict: ${finalVerdict}. Pipeline: ${stageResultsSummary}`)

// ----------------------------------------------------------------
// TASK LOG: write deferred STATUS/DEVLOG content — do NOT touch those files
// ----------------------------------------------------------------
log('Writing task log (STATUS/DEVLOG deferred to merge time)...')

const logResult = await agent(`${W}
You are the task-log agent for the SDLC pipeline.

Your job is to write a structured task log file that records what STATUS.md and DEVLOG.md
should be updated to. Do NOT modify planning/STATUS.md or DEVLOG.md directly — those files
are updated when the worktree branch is merged into main via /clean-worktree.

Target:
  Block:            ${blockId}
  Task:             ${taskNumber}
  Final verdict:    ${finalVerdict}
  Review attempts:  ${reviewAttempts}
  Pipeline summary: ${stageResultsSummary}
  Branch:           ${branchName}
  Log file:         ${logFile}
  Worktree root:    ${worktreePath}

Instructions:

1. Read the spec file to identify the NEXT task after ${taskNumber}:
   cd ${worktreePath} && cat ${specFile}
   Look for the section "### ${taskNumber + 1}." to get the next task's title.
   If no task ${taskNumber + 1} exists, note "block complete".

2. Read current STATUS.md to understand the block notes format:
   cd ${worktreePath} && head -30 planning/STATUS.md

3. Get the git log for this pipeline run:
   cd ${worktreePath} && git log --oneline main..HEAD 2>/dev/null || git log --oneline -8

4. Run to get today's date:
   date +%Y-%m-%d

5. Write the task log file: ${worktreePath}/${logFile}

   Use EXACTLY this format (fill in all bracketed values):

   # Task Log — ${blockId} task ${taskNumber}

   **Block:** ${blockId}
   **Task:** ${taskNumber}
   **Verdict:** ${finalVerdict}
   **Date:** [today's date from step 4]
   **Branch:** ${branchName}
   **Applied:** false

   ---

   ## STATUS.md — Block Status
   [Only include this section if the block was "Not started" when this task ran (blockStatus: ${scout.blockStatus}).
    Write: "In progress" to flip it. Omit this section entirely if block was already In progress or Done.]

   ## STATUS.md — Current Focus Line
   [The COMPLETE replacement string for the "Current focus:" line.
    If task ${taskNumber + 1} exists: "Phase N, Block X — Task ${taskNumber + 1}: [task title]"
    If block complete: the next block's focus line]

   ## STATUS.md — Last Updated Line
   [The COMPLETE replacement string for the "Last updated:" line.
    Format: "YYYY-MM-DD — Block X in progress (Tasks 1–${taskNumber} complete; Tasks ${taskNumber + 1}–N next — [brief description])"]

   ## STATUS.md — Block Notes Column
   [The updated Notes column text for this block's row in the progress table.
    Summarizes which tasks are done and which remain.]

   ---

   ## DEVLOG Entry

   ## [today's date] (task ${taskNumber} — [brief description matching the task])

   [One paragraph: what was implemented or tested, how review went (${finalVerdict} verdict${reviewAttempts > 1 ? ` after ${reviewAttempts} attempts` : ''}), notable findings. End with: "Next: Task ${taskNumber + 1} — [next task description]."]

   \`\`\`
   [paste the git log --oneline output from step 3]
   \`\`\`

6. Do NOT commit the log file — the finalize agent will commit it with all other reports.

Return using StructuredOutput:
  logFile: "${logFile}"
  applied: false
  nextFocus: the exact Current Focus Line string you wrote to the log
  notes: any settled decisions that should be added to DECISIONS.md
`, { label: 'task-log', schema: LOG_SCHEMA, phase: 'Wrap-up' })

if (logResult) {
  stageResults.push({ stage: 'task-log', ...logResult, success: true })
  log(`Task log written: ${logFile}`)
  if (logResult.notes) log(`Decisions to log manually: ${logResult.notes}`)
} else {
  stageResults.push({ stage: 'task-log', success: false, notes: 'Agent returned null' })
  log('Task-log agent returned null — log file may need manual creation')
}

// ----------------------------------------------------------------
// FINALIZE: workflow report + commit all reports + print merge instructions
// ----------------------------------------------------------------
log('Running finalize: workflow report + commit...')

const stageTable = stageResults.map(r => {
  const label  = r.stage + (r.attempt ? ` (attempt ${r.attempt})` : '')
  const status = r.verdict ? r.verdict : (r.success ? 'completed' : 'FAILED')
  const file   = r.reportFile || r.workflowReportFile || r.logFile || '—'
  const commit = r.commitHash ? r.commitHash.substring(0, 7) : '—'
  const notes  = (r.notes || '').substring(0, 60)
  return `| ${label} | ${status} | ${file} | ${commit} | ${notes} |`
}).join('\n')

const finalizeResult = await agent(`${W}
You are the finalize agent for the SDLC pipeline.

IMPORTANT: Do NOT modify planning/STATUS.md or DEVLOG.md. Those are applied at merge time.
Your chore commit includes ONLY: test report, review report, document report, task log,
and the workflow report you write here.

Target:
  Block:           ${blockId}
  Task:            Task ${taskNumber}
  Final verdict:   ${finalVerdict}
  Worktree root:   ${worktreePath}
  Branch:          ${branchName}
  Workflow report: ${workflowReport}

Stage results so far:
${stageResultsSummary}

STEP 1 — Get the commit history from this pipeline run:
  cd ${worktreePath} && git log --oneline -15

STEP 2 — Write the workflow report: ${worktreePath}/${workflowReport}

  Format:
  # SDLC Workflow Report — ${blockId} Task ${taskNumber}

  **Date:** [run: date +%Y-%m-%d]
  **Block:** ${blockId}
  **Task scope:** Task ${taskNumber}
  **Pipeline started from:** ${scout.startStage}
  **Review attempts:** ${reviewAttempts} of ${MAX_REVIEW_ATTEMPTS} max
  **Worktree:** ${worktreePath}
  **Branch:** ${branchName}

  ## Final Verdict
  ${finalVerdict} — [one sentence explanation]

  ## Stage Results

  | Stage | Status | Report | Commit | Notes |
  |---|---|---|---|---|
  ${stageTable}

  ## Key Findings
  [what was implemented, notable decisions, any known bugs touched]

  ## Files Modified
  [source files created or modified — from the implement report]

  ## Docs Updated
  [doc files patched — from the document report; NEEDS_REVIEW flags]

  ## Commits (this pipeline run)
  [relevant lines from git log --oneline]

  ## Next Step
  To merge this task into main and apply STATUS/DEVLOG updates:
    /clean-worktree ${branchName}

STEP 3 — Commit the report files. Never use git add -A or git add .

  Run: cd ${worktreePath} && git status
  Stage ONLY report files (NOT STATUS.md or DEVLOG.md — never touch those in the worktree):
    cd ${worktreePath} && git add ${testReport} 2>/dev/null || true
    cd ${worktreePath} && git add ${reviewReport} 2>/dev/null || true
    cd ${worktreePath} && git add ${documentReport} 2>/dev/null || true
    cd ${worktreePath} && git add ${logFile} 2>/dev/null || true
    cd ${worktreePath} && git add ${workflowReport}

  Commit using HEREDOC:
    cd ${worktreePath} && git commit -m "$(cat <<'EOF'
    chore: wrap up ${stem}
    EOF
    )"
  cd ${worktreePath} && git log --oneline -1

STEP 4 — Print the merge instructions EXACTLY as shown:

  ╔══════════════════════════════════════════════════════════════════╗
  ║  Pipeline complete: ${stem}
  ║  Verdict: ${finalVerdict}
  ║
  ║  Worktree: ${worktreePath}
  ║  Branch:   ${branchName}
  ║
  ║  To merge and apply STATUS/DEVLOG updates, run from main session:
  ║    /clean-worktree ${branchName}
  ╚══════════════════════════════════════════════════════════════════╝

Return using StructuredOutput:
  workflowReportFile: "${workflowReport}"
  commitMessage: "chore: wrap up ${stem}"
  commitHash: 7-character short hash from git log --oneline -1
  notes: any follow-up items (DECISIONS.md entries, NEEDS_REVIEW doc flags)
`, { label: 'finalize', schema: FINALIZE_SCHEMA, phase: 'Wrap-up' })

if (finalizeResult) {
  stageResults.push({ stage: 'finalize', ...finalizeResult, success: true })
  log(`Committed: ${finalizeResult.commitMessage}`)
  log(`Workflow report: ${finalizeResult.workflowReportFile}`)
} else {
  stageResults.push({ stage: 'finalize', success: false, notes: 'Finalize agent returned null' })
  log('Finalize agent returned null — manual commit may be needed')
}

log(`Pipeline complete. Verdict: ${finalVerdict} | Worktree: ${worktreePath} | Branch: ${branchName}`)
log(`To merge: /clean-worktree ${branchName}`)
log(`IMPORTANT: If running multiple tasks in parallel, merge them in task-number order.`)
log(`Merging out of order will cause STATUS.md "Current focus" to point to the wrong next task.`)

return {
  blockId,
  taskNumber,
  stem,
  branchName,
  worktreePath,
  finalVerdict,
  reviewAttempts,
  startStage: scout.startStage,
  workflowReport: finalizeResult?.workflowReportFile || workflowReport,
  logFile,
  mergeCommand: `/clean-worktree ${branchName}`,
  stageResults
}
