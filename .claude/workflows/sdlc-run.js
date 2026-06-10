// =============================================================================
// sdlc-run — SDLC Pipeline Workflow
// =============================================================================
//
// Runs the full SDLC pipeline for a phase/block from the current stage to
// completion. Each stage is a separate agent with its own context window;
// agents communicate only through report files on disk.
//
// USAGE
//   /sdlc-run phase0-blockC      runs all tasks in the block
//   /sdlc-run phase0-blockC 2    scopes every stage to task 2 only
//
// PIPELINE STAGES (in order)
//   Scout      → detect current stage from report files + STATUS.md + DEVLOG
//   Plan       → generate task spec (skipped if spec file already exists)
//   Implement  → execute tasks from spec
//   Fix        → targeted fixes for FAIL/PARTIAL review (one pass per retry)
//   Test       → 8-check suite: imports, ruff, pylint, pytest collect + full
//   Review     → fresh pytest + acceptance criteria check; verdict gates next
//   Document   → surgical patches to docs/ (skipped if verdict is not PASS)
//   Wrap-up    → update STATUS.md + DEVLOG, commit planning files, write report
//
// COMMIT STRATEGY
//   Each agent commits its own work immediately after completing it:
//     feat: implement <stem>          implement agent (fix: if validation failed)
//     fix: fix pass N for <stem>      fix agent — one commit per pass
//     docs: update docs for <stem>    document agent
//     chore: wrap up <stem>           finalize agent (STATUS/DEVLOG/reports)
//
//   This ensures crash recovery: if the pipeline dies mid-run, all completed
//   work is already in git history and visible to future agents via git log.
//
// RESUMPTION
//   The scout checks which report files exist to determine where to resume.
//   Priority order:
//     no spec file      → generate-tasks
//     no implement.md   → implement
//     no test.md        → test
//     no review.md      → review
//     review = FAIL     → fix
//     no document.md    → document
//     document.md exists → wrap-up
//   Report files are authoritative; DEVLOG is a cross-reference sanity check.
//   Safe to re-run — the scout will pick up exactly where the pipeline stopped.
//
// RETRY LOOP (max 3 review attempts)
//   implement → test → review → [PASS: document] or [FAIL: fix → test → review]
//   Each fix pass is a separate commit so the diff from each pass is auditable.
//
// MODEL TIERING (token lever — see the MODEL map below)
//   Three tiers, matched to the work: Opus on PLANNING (generate-tasks fallback); Haiku on the
//   purely-mechanical stages (scout, start-block, test, finalize); Sonnet on the judgment work
//   (implement/fix/review/document/log-work). Without this map every stage inherits the SESSION
//   model — so launching from an Opus session would run scout/test/finalize on Opus too. Tune
//   one place: the MODEL map.
//
// STAGED MODEL ESCALATION (ESCALATION_MODEL)
//   The FINAL fix pass and FINAL review attempt before the loop gives up run on Opus. The cheap
//   path stays on Sonnet; a genuinely hard failure that has already failed twice gets one strong
//   shot. Set null to disable.
//
// REPORT FILES  (all written to planning/tasks/<block>/reports/)
//   [taskN-]implement.md  implement agent; overwritten by each fix pass
//   [taskN-]test.md       test agent
//   [taskN-]review.md     review agent
//   [taskN-]document.md   document agent
//   [taskN-]workflow.md   finalize agent (full pipeline run summary)
//
// =============================================================================

export const meta = {
  name: 'sdlc-run',
  description: 'Run the SDLC pipeline for a phase/block from current stage to completion',
  whenToUse: 'When starting or resuming a phase/block through the full implement→test→review→document→wrap-up cycle. Usage: /sdlc-run phase0-blockC or /sdlc-run phase0-blockC 2',
  phases: [
    { title: 'Scout',     detail: 'Determine current pipeline stage from files and DEVLOG' },
    { title: 'Plan',      detail: 'Generate task spec (only if spec file does not yet exist)' },
    { title: 'Implement', detail: 'Execute implementation tasks' },
    { title: 'Fix',       detail: 'Targeted fixes for FAIL/PARTIAL review — overwrites implement report' },
    { title: 'Test',      detail: 'Run 8-check validation suite' },
    { title: 'Review',    detail: 'Verify acceptance criteria; run fresh tests; issue verdict' },
    { title: 'Document',  detail: 'Surgically patch docs/ (gates on PASS verdict)' },
    { title: 'Wrap-up',   detail: 'Log work, chore commit (STATUS/DEVLOG/reports), write workflow report' },
  ]
}

// ----------------------------------------------------------------
// Parse args: "phase0-blockC" or "phase0-blockC 2"
// ----------------------------------------------------------------
const rawArgs = typeof args === 'string' ? args.trim() : ''
if (!rawArgs) {
  log('ERROR: No block ID provided.')
  log('Usage: /sdlc-run phase0-blockC')
  log('       /sdlc-run phase0-blockC 2')
  return { error: 'Missing required argument: block ID (e.g. "phase0-blockC" or "phase0-blockC 2")' }
}

const parts = rawArgs.split(/\s+/)
const blockId = parts[0]
const taskNumber = parts.length > 1 ? parseInt(parts[1], 10) : null
const specFile = `planning/tasks/${blockId}/tasks.md`
const stem = taskNumber !== null ? `${blockId}-task${taskNumber}` : blockId
const reportsDir = `planning/tasks/${blockId}/reports`
const taskPrefix = taskNumber !== null ? `task${taskNumber}-` : ''
const implementReport = `${reportsDir}/${taskPrefix}implement.md`
const testReport      = `${reportsDir}/${taskPrefix}test.md`
const reviewReport    = `${reportsDir}/${taskPrefix}review.md`
const documentReport  = `${reportsDir}/${taskPrefix}document.md`
const workflowReport  = `${reportsDir}/${taskPrefix}workflow.md`
const breakdownFile   = `planning/tasks/${blockId}/breakdown.md`

log(`Target: ${blockId}${taskNumber !== null ? ` task ${taskNumber}` : ' (all tasks)'}`)
log(`Spec: ${specFile} | Stem: ${stem}`)

// ----------------------------------------------------------------
// Schemas
// ----------------------------------------------------------------
const SCOUT_SCHEMA = {
  type: 'object',
  required: ['startStage', 'specFileExists', 'blockStatus', 'existingReports', 'statusSummary'],
  properties: {
    startStage: {
      type: 'string',
      enum: ['generate-tasks', 'implement', 'fix', 'test', 'review', 'document', 'wrap-up'],
      description: 'The stage to start from, determined by which report files exist'
    },
    specFileExists: { type: 'boolean' },
    blockStatus: {
      type: 'string',
      enum: ['Not started', 'In progress', 'Done', 'Blocked', 'Skipped', 'Unknown'],
      description: 'Current status of this block in STATUS.md progress table'
    },
    existingReports: {
      type: 'array',
      items: { type: 'string' },
      description: 'List of report file paths that already exist'
    },
    reviewVerdict: {
      type: 'string',
      description: 'Verdict extracted from the review report if it exists: PASS, FAIL, PARTIAL, or empty string if no review report'
    },
    currentFocus: { type: 'string', description: 'The Current focus line from STATUS.md' },
    lastDevlogEntry: { type: 'string', description: 'Summary of the most recent DEVLOG entry (first 6 lines)' },
    statusSummary: { type: 'string', description: 'Human-readable summary of what the scout found and why it chose startStage' },
    discrepancies: { type: 'string', description: 'Any discrepancies between DEVLOG entries and report files, or empty string if none' }
  }
}

const STAGE_SCHEMA = {
  type: 'object',
  required: ['reportFile', 'success'],
  properties: {
    reportFile: { type: 'string', description: 'Path to the report file written' },
    success: { type: 'boolean' },
    filesModified: { type: 'array', items: { type: 'string' } },
    commitHash: { type: 'string', description: 'Short hash of the commit made by this agent, or empty string if no commit' },
    notes: { type: 'string' }
  }
}

const TEST_SCHEMA = {
  type: 'object',
  required: ['reportFile', 'allPassed', 'passCount', 'failCount'],
  properties: {
    reportFile: { type: 'string' },
    allPassed: { type: 'boolean' },
    passCount: { type: 'integer' },
    failCount: { type: 'integer' },
    failedTests: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' }
  }
}

const REVIEW_SCHEMA = {
  type: 'object',
  required: ['reportFile', 'verdict'],
  properties: {
    reportFile: { type: 'string' },
    verdict: { type: 'string', enum: ['PASS', 'FAIL', 'PARTIAL'] },
    failureReasons: { type: 'array', items: { type: 'string' } },
    unmetCriteria: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' }
  }
}

const WRAPUP_SCHEMA = {
  type: 'object',
  required: ['statusUpdated', 'devlogUpdated'],
  properties: {
    statusUpdated: { type: 'boolean' },
    devlogUpdated: { type: 'boolean' },
    nextFocus: { type: 'string' },
    notes: { type: 'string' }
  }
}

const FINALIZE_SCHEMA = {
  type: 'object',
  required: ['workflowReportFile', 'commitMessage'],
  properties: {
    workflowReportFile: { type: 'string' },
    commitMessage: { type: 'string' },
    commitHash: { type: 'string' },
    notes: { type: 'string' }
  }
}

// ----------------------------------------------------------------
// MODEL TIERING — the primary token lever for this pipeline.
//
// Without this map every stage would inherit the SESSION model — so launching /sdlc-run from an
// Opus session silently runs scout, test, and finalize on Opus too. This map fixes the cost per
// stage regardless of how the workflow was launched.
//
// Principle (mirrors sdlc-task): match the model to the work.
//   • Opus   — generate-tasks (authors the spec; fallback path only)
//   • Haiku  — scout / start-block / test / finalize. Fixed procedures, no real judgment.
//   • Sonnet — implement / fix / review / document / log-work (judgment work).
//
// To re-tier, change one value here — nothing else moves.
// Valid values: 'haiku' | 'sonnet' | 'opus' | undefined (inherit session model).
// ----------------------------------------------------------------
const MODEL = {
  scout:         'haiku',    // deterministic decision tree: ls a few files, apply a fixed 7-rule order
  startBlock:    'haiku',    // one surgical STATUS.md edit + a date stamp
  generateTasks: 'opus',     // PLANNING — authors the spec that drives everything (fallback path)
  implement:     'sonnet',   // writes code + tests against a scoped spec/breakdown
  fix:           'sonnet',   // targeted fixes; failures escalate, never silently ship
  test:          'haiku',    // run 8 fixed commands, read exit codes; review re-runs pytest authoritatively
  review:        'sonnet',   // verify criteria; gated by an authoritative fresh-test run
  document:      'sonnet',   // surgical doc patches, gated on PASS
  logWork:       'sonnet',   // authors the human-facing DEVLOG prose + edits STATUS — keep the quality
  finalize:      'haiku',    // assembles a JS-precomputed table + scripted git add; can't break the pipeline
}

// Merge an optional model override into an agent's opts (omits the key when undefined,
// so the agent inherits the session model rather than receiving model: undefined).
function withModel(base, model) {
  return model ? { ...base, model } : base
}

// ----------------------------------------------------------------
// Stage results accumulator
// ----------------------------------------------------------------
const stageResults = []

// ================================================================
// PHASE 1: SCOUT — determine current pipeline stage
// ================================================================
phase('Scout')

const scout = await agent(`
You are the pipeline scout for the SDLC workflow system.

Target:
  Block ID:    ${blockId}
  Task number: ${taskNumber !== null ? taskNumber : 'none (full block)'}
  Spec file:   ${specFile}
  Report stem: ${stem}
  Reports dir: ${reportsDir}

Your job is to determine which SDLC stage to start from, based on which report files exist. Run these checks using the Bash tool:

STEP 1 — Check spec file:
  ls -la ${specFile} 2>/dev/null && echo "SPEC_EXISTS" || echo "SPEC_MISSING"

STEP 2 — Check report files (block directory: ${reportsDir}):
  ls ${implementReport} 2>/dev/null && echo "HAS_IMPLEMENT" || echo "NO_IMPLEMENT"
  ls ${testReport} 2>/dev/null && echo "HAS_TEST" || echo "NO_TEST"
  ls ${reviewReport} 2>/dev/null && echo "HAS_REVIEW" || echo "NO_REVIEW"
  ls ${documentReport} 2>/dev/null && echo "HAS_DOCUMENT" || echo "NO_DOCUMENT"
  ls ${reportsDir}/*.md 2>/dev/null | head -20 || echo "NO_BLOCK_REPORTS"

STEP 3 — Read STATUS.md to find this block's status and Current focus line:
  head -60 planning/STATUS.md

STEP 4 — Read the most recent DEVLOG entry (at repo root):
  head -60 DEVLOG.md

STEP 5 — If the review report exists, extract the verdict:
  grep -iE "\\*\\*Verdict|## Verdict|^Verdict:" ${reportsDir}/${stem}-review.md 2>/dev/null | head -5 || echo "NO_REVIEW_REPORT"

STEP 6 — Determine startStage using this EXACT priority order:
  1. Spec file MISSING → "generate-tasks"
  2. Spec exists, no implement report (and no variant) → "implement"
  3. Implement report exists, no test report → "test"
  4. Test report exists, no review report → "review"
  5. Review report exists with FAIL or PARTIAL verdict → "fix" (targeted fix cycle, not full re-implement)
  6. Review report exists with PASS verdict, no document report → "document"
  7. Document report exists → "wrap-up"

STEP 7 — Find the block's status in STATUS.md progress table. Look for a row containing "${blockId}" and extract its Status column value (Not started / In progress / Done / Blocked / Skipped).

STEP 8 — Note any discrepancy: if DEVLOG says a stage is done but the matching report file is missing, record that.

Collect the list of existing report files from the ls output in STEP 2 and STEP 6.

Return your findings using the StructuredOutput tool.
`, withModel({ label: 'scout', schema: SCOUT_SCHEMA, phase: 'Scout' }, MODEL.scout))

if (!scout) {
  log('Scout agent failed — cannot determine pipeline state, aborting')
  return { error: 'Scout failed', blockId, stem }
}

log(`Scout: start from "${scout.startStage}" | block status: "${scout.blockStatus}"`)
if (scout.discrepancies) log(`Discrepancies: ${scout.discrepancies}`)
if (scout.statusSummary) log(scout.statusSummary)

// Auto-flip block to "In progress" if it is "Not started"
if (scout.blockStatus === 'Not started') {
  log(`Block "${blockId}" is Not started — marking In progress in STATUS.md...`)
  await agent(`
You need to mark block "${blockId}" as "In progress" in planning/STATUS.md.

Instructions:
1. Read the file: planning/STATUS.md
2. Find the row in the Progress Table where the Block/Project column contains "${blockId}"
3. Change that row's Status cell from "Not started" to "In progress"
4. Update the "Current focus:" line near the top of the file to:
   "${blockId}${taskNumber !== null ? ` — Task ${taskNumber}` : ''}"
5. Update the "Last updated:" date — run this to get today: date +%Y-%m-%d
6. Use the Edit tool to make these changes surgically (do not rewrite the entire file)
7. Confirm the edits are correct by reading back the relevant lines
`, withModel({ label: 'start-block', phase: 'Scout' }, MODEL.startBlock))
}

let currentStage = scout.startStage
let reviewAttempts = 0
const MAX_REVIEW_ATTEMPTS = 3
let lastReviewResult = null

// STAGED MODEL ESCALATION — the FINAL fix pass and FINAL review attempt before the loop gives
// up run on a stronger model. The common path stays on Sonnet (MODEL.fix/review); only the
// genuinely-hard case that has already failed twice gets one Opus shot. Set to null to disable.
const ESCALATION_MODEL = 'opus'

// ================================================================
// PHASE 2: PLAN — generate-tasks (only if spec file missing)
// ================================================================
if (currentStage === 'generate-tasks') {
  phase('Plan')
  log('Spec file not found — running generate-tasks...')

  const genResult = await agent(`
You need to generate the task spec for block "${blockId}".

Spec file to create: ${specFile}

Instructions:

1. Read planning/MASTER_PLAN.md — find the section covering "${blockId}". Look for phase/block headers. Read that entire section.

2. Read planning/Agentic_Engineering_Projects_and_Learning_Plan.md — find the matching section for "${blockId}".

3. Read CLAUDE.md — note all standing rules (especially Rule 1: every task ships with tests, no exceptions) and the known bugs table.

4. Read an existing spec as format reference: planning/tasks/phase0-blockC/tasks.md
   Study its structure carefully: Goal, Context Pointers, Step-by-Step Tasks (numbered ### sections with sub-steps), Acceptance Criteria, Validation Commands, Notes section.

   Also create the block directory structure now if it does not yet exist:
   mkdir -p planning/tasks/${blockId}/reports

5. Write ${specFile} following that exact format:
   ## Goal
   [one-sentence purpose]

   ## Context Pointers
   [links to master plan sections, relevant code files, relevant DECISIONS entries]

   ## Step-by-Step Tasks
   ### 1. [Task Name]
   [sub-steps with exact file paths and class/method names]

   ### 2. [Task Name]
   ...

   ### N. Validate
   [validation steps — always the final task]

   ## Acceptance Criteria
   [bullet list of what "done" looks like, testable and specific]

   ## Validation Commands
   [bash commands to verify completion]

   ## Notes
   [empty section for in-progress updates]

   Rules:
   - Every workflow task must include writing tests (CLAUDE.md Rule 1)
   - The final task must always be "Validate"
   - Tasks should be sized for the 21 hrs/week schedule
   - Include exact file paths and class/method names

Return your result using the StructuredOutput tool with fields:
  reportFile: path to the spec file written (${specFile})
  success: true if written successfully
  filesModified: ["${specFile}"]
  notes: brief note about what was generated
`, withModel({ label: 'generate-tasks', schema: STAGE_SCHEMA, phase: 'Plan' }, MODEL.generateTasks))

  if (!genResult || !genResult.success) {
    log('generate-tasks failed — aborting pipeline')
    stageResults.push({ stage: 'generate-tasks', success: false })
    return { error: 'generate-tasks failed', blockId, stem, stageResults }
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
  // IMPLEMENT (first pass only — retries go through fix instead)
  // ----------------------------------------------------------
  if (currentStage === 'implement') {
    phase('Implement')
    log('Running implement...')

    const implResult = await agent(`
You are the implementation agent for the SDLC pipeline.

Target:
  Block:         ${blockId}
  Task:          ${taskNumber !== null ? `Task ${taskNumber} only` : 'all tasks'}
  Spec file:     ${specFile}
  Report to write: ${implementReport}

Instructions:

1. Read CLAUDE.md — internalize all standing rules and the known bugs table before writing any code.

2. Read the spec file: ${specFile}
   ${taskNumber !== null
     ? `Focus ONLY on the "### ${taskNumber}." section. Do not implement other tasks.`
     : 'Read all tasks and execute them in order from first to last.'}

2.5. Check for an optional breakdown file (more granular sub-steps written by /breakdown):
   Run: ls ${breakdownFile} 2>/dev/null && echo "BREAKDOWN_EXISTS" || echo "NO_BREAKDOWN"

   If BREAKDOWN_EXISTS:
     Read ${breakdownFile}
     ${taskNumber !== null
       ? `Find the section "### Step ${taskNumber}:" (may include a title after the colon).
     Use its atomic sub-steps (numbered N.1, N.2, …) as your primary execution guide.
     The inline "Verify:" commands are live checkpoints — run each one before moving to the next sub-step.`
       : `Read all "### Step N:" sections in order and use their atomic sub-steps as your execution guide.
     The inline "Verify:" commands are live checkpoints — run each one before moving to the next step.`}
     The breakdown's "## Acceptance Criteria" and "## Validation Commands" match the spec.
     tasks.md is still authoritative for scope and acceptance criteria; breakdown.md is authoritative
     for HOW to execute each step.

   If NO_BREAKDOWN: proceed using tasks.md only (normal behavior).

3. Execute each step in the task(s) methodically — use Read, Edit, Write, and Bash tools as needed.

4. As you implement:
   - Follow every CLAUDE.md rule (no hardcoded prompts, no deployment logic in nodes, etc.)
   - Check the CLAUDE.md known bugs table — if your change touches those files, fix those bugs too
   - Write tests for all new code (CLAUDE.md Rule 1 — no exceptions)
   - Never hardcode system prompts in Python — use .j2 files in app/prompts/ via PromptManager

5. Run the Validation Commands from the spec to confirm correctness before writing the report.

6. Write the implementation report to: ${implementReport}

   Use EXACTLY this format:

   # Implementation Report — ${stem}

   **Date:** [run: date +%Y-%m-%d]
   **Plan:** ${specFile}
   **Scope:** ${taskNumber !== null ? `Task ${taskNumber}` : 'Full block'}

   ## What Was Built or Changed
   - [bullet list of changes, each with file path]

   ## Files Created or Modified
   | File | Action |
   |---|---|
   | path/to/file.py | created / modified |

   ## Validation Output
   **Commands run:**
   \`\`\`
   [paste commands from spec]
   \`\`\`
   **Results:**
   \`\`\`
   [paste actual output]
   \`\`\`
   Status: PASSED / FAILED

   ## Decisions and Trade-offs
   [explain any non-obvious choices; reference CLAUDE.md DECISIONS entries if applicable]

   ## Follow-up Work
   [anything intentionally deferred to later tasks]

   ## git diff --stat
   \`\`\`
   [run: git diff --stat]
   \`\`\`

7. Commit your changes now. Never use git add -A or git add . — stage files explicitly by name.

   Run: git status
   Identify all changed/new files under app/, tests/, and the implement report.

   Stage code files first, then the report:
     git add app/file1.py tests/file2.py ${implementReport}  (list each file explicitly)

   Commit using HEREDOC:
     git commit -m "$(cat <<'EOF'
     feat: implement ${stem}

     
     EOF
     )"

   If validation failed (Status: FAILED above), use "fix:" prefix instead of "feat:".
   Run: git log --oneline -1
   Capture the short hash from that output.

Return your result using the StructuredOutput tool:
  reportFile: "${implementReport}"
  success: true if implementation completed without critical errors
  filesModified: array of every source file you created or modified
  commitHash: the 7-character short hash from git log --oneline -1 (empty string if commit failed)
  notes: one-line summary
`, withModel({ label: 'implement', schema: STAGE_SCHEMA, phase: 'Implement' }, MODEL.implement))

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
  // FIX (review retry path — targeted fix, overwrites implement report)
  // ----------------------------------------------------------
  if (currentStage === 'fix') {
    phase('Fix')
    const fixPass = reviewAttempts + 1
    log(`Running fix (pass ${fixPass}) — targeting review failures...`)

    // Last fix pass before the loop can give up → escalate the model.
    const fixModel = (ESCALATION_MODEL && fixPass === MAX_REVIEW_ATTEMPTS) ? ESCALATION_MODEL : MODEL.fix
    if (fixModel !== MODEL.fix) log(`Final fix pass — escalating model to ${fixModel}.`)

    const fixResult = await agent(`
You are the fix agent for the SDLC pipeline. Your job is to make targeted fixes for the failures identified
in the last review — NOT to re-implement the entire spec from scratch.

Target:
  Block:            ${blockId}
  Task:             ${taskNumber !== null ? `Task ${taskNumber}` : 'all tasks'}
  Spec file:        ${specFile}
  Review report:    ${reviewReport}
  Prior implement report: ${implementReport}
  Report to write:  ${implementReport}  ← overwrites this slot (Fix Pass ${fixPass})

GATE CHECKS (do these first):
1. Run: ls ${reviewReport} 2>/dev/null && echo EXISTS || echo MISSING
   If the review report does not exist → stop immediately, return success: false, notes: "No review report found."
2. Read ${reviewReport} and extract the verdict line.
   If verdict is PASS → stop, return success: false, notes: "Review verdict is already PASS — run /document instead."

Instructions:

1. Read the review report: ${reviewReport}
   Extract ONLY:
   - The failing rows from "## Acceptance Criteria Check" (PARTIAL or NOT_MET rows)
   - The entire "## Issues Found" section
   - The "## Fresh Test Results" section (to understand test failures)

2. Read the prior implement report: ${implementReport}
   Extract:
   - The "## Files Created or Modified" table — this is the baseline file list
   - Look for "Fix Pass" in the title to determine the current fix pass count (starts at 1 if none)

3. If a breakdown file exists, check the relevant sub-steps for original intent:
   Run: ls ${breakdownFile} 2>/dev/null && echo EXISTS || echo MISSING
   If EXISTS: read ${breakdownFile} and find the "### Step ${taskNumber !== null ? taskNumber : 'N'}:" section.
   Use it to understand what the original implementation was supposed to do for the failing criterion.
   Do NOT re-implement from scratch — use it only as context for the targeted fix.

4. Read the source files that are relevant to the failing criteria only.
   Do NOT read files unrelated to the issues found.

5. Make the MINIMUM targeted changes required to address the failing criteria and issues.
   - Fix ONLY what the review identified as failing
   - Do not modify passing criteria or unrelated code
   - Follow all CLAUDE.md standing rules

6. Run ONLY the Validation Commands from the spec (not the full 8-test suite — that belongs to /test):
   Find the "## Validation Commands" section of ${specFile} and run those commands.

7. Build the complete file list: union of the prior implement table PLUS any new files you touched.

8. Overwrite the implement report at: ${implementReport}
   This overwrites the slot. Downstream commands (/test, /review-task, /document) all read this slot.

   Use EXACTLY this format:

   # Fix Pass ${fixPass} — ${stem}

   **Date:** [run: date +%Y-%m-%d]
   **Plan:** ${specFile}
   **Scope:** ${taskNumber !== null ? `Task ${taskNumber}` : 'Full block'}
   **Fix pass:** ${fixPass}

   ## Failures Addressed
   [list each failing criterion or issue from the review report, and how it was fixed]

   ## Changes Made
   - [bullet list of targeted changes with file paths — only what was changed this pass]

   ## Files Created or Modified
   | File | Action |
   |---|---|
   | path/to/file.py | created / modified |
   [IMPORTANT: include ALL files from the prior implement report PLUS any newly touched files]

   ## Validation Output
   **Commands run:**
   \`\`\`
   [spec validation commands]
   \`\`\`
   **Results:**
   \`\`\`
   [actual output]
   \`\`\`
   Status: PASSED / FAILED

   ## Decisions and Trade-offs
   [explain any non-obvious choices]

   ## git diff --stat
   \`\`\`
   [run: git diff --stat]
   \`\`\`

9. Commit your changes now. Never use git add -A or git add . — stage files explicitly by name.

   Run: git status
   Identify all changed/new files under app/, tests/, and the updated implement report.

   Stage targeted changes and the updated report:
     git add app/file1.py tests/file2.py ${implementReport}  (list each file explicitly)

   Commit using HEREDOC:
     git commit -m "$(cat <<'EOF'
     fix: fix pass ${fixPass} for ${stem}


     EOF
     )"

   Run: git log --oneline -1
   Capture the short hash from that output.

Return your result using the StructuredOutput tool:
  reportFile: "${implementReport}"
  success: true if fixes were applied and validation passed
  filesModified: array of source files you actually changed this pass (not the full accumulated list)
  commitHash: the 7-character short hash from git log --oneline -1 (empty string if commit failed)
  notes: one-line summary of what was fixed
`, withModel({ label: `fix-${fixPass}`, schema: STAGE_SCHEMA, phase: 'Fix' }, fixModel))

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

    const testResult = await agent(`
You are the test agent for the SDLC pipeline. Run the 8-check validation suite and write a test report.

Target:
  Spec:            ${specFile}
  Report to write: ${testReport}

Run ALL 8 checks IN ORDER using the Bash tool. Capture the full output (stdout + stderr) for each.

Run from the repo root unless stated otherwise.

CHECK 1 — App import (run from app/ directory):
  cd app && uv run python -c "import main" 2>&1
  echo "CHECK1_EXIT:$?"

CHECK 2 — Worker import (run from app/ directory):
  cd app && uv run python -c "import worker.config" 2>&1
  echo "CHECK2_EXIT:$?"

CHECK 3 — Database session import (run from app/ directory):
  cd app && uv run python -c "import database.session" 2>&1
  echo "CHECK3_EXIT:$?"

CHECK 4 — Repository import (run from app/ directory):
  cd app && uv run python -c "import database.repository" 2>&1
  echo "CHECK4_EXIT:$?"

CHECK 5 — Ruff lint (run from repo root):
  uv run ruff check app/ 2>&1
  echo "CHECK5_EXIT:$?"

CHECK 6 — Pylint (run from repo root):
  uv run pylint app/ 2>&1
  echo "CHECK6_EXIT:$?"

CHECK 7 — Pytest collect (run from repo root):
  uv run pytest --collect-only -q 2>&1
  echo "CHECK7_EXIT:$?"

CHECK 8 — Pytest full (run from repo root):
  uv run pytest 2>&1
  echo "CHECK8_EXIT:$?"

For each check record:
  test_name: descriptive name
  passed: true if exit code was 0
  execution_command: exact command run
  test_purpose: what this check verifies
  error: full error output if failed, empty string if passed

Write the test report to: ${testReport}

Use EXACTLY this format:

# Test Report — ${stem}

**Date:** [run: date +%Y-%m-%d]
**Spec:** ${specFile}
**Scope:** ${taskNumber !== null ? `Task ${taskNumber}` : 'Full block'}

## Summary

| Test | Result | Error |
|---|---|---|
[FAILED rows first, then PASSED rows]

## Full Results (JSON)
\`\`\`json
[
  {
    "test_name": "...",
    "passed": true/false,
    "execution_command": "...",
    "test_purpose": "...",
    "error": "..."
  },
  ...
]
\`\`\`

Return your result using the StructuredOutput tool:
  reportFile: "${testReport}"
  allPassed: true only if ALL 8 checks passed (exit code 0)
  passCount: integer count of checks that passed
  failCount: integer count of checks that failed
  failedTests: array of test_name strings for failed checks
  notes: one-line summary
`, withModel({ label: 'test', schema: TEST_SCHEMA, phase: 'Test' }, MODEL.test))

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

    // Final review attempt before the loop can give up → escalate the model.
    const reviewModel = (ESCALATION_MODEL && reviewAttempts === MAX_REVIEW_ATTEMPTS) ? ESCALATION_MODEL : MODEL.review
    if (reviewModel !== MODEL.review) log(`Final review attempt — escalating model to ${reviewModel}.`)

    const reviewResult = await agent(`
You are the review agent for the SDLC pipeline. Verify the implementation against the spec and issue a verdict.

Target:
  Block:            ${blockId}
  Task:             ${taskNumber !== null ? `Task ${taskNumber}` : 'all tasks'}
  Spec file:        ${specFile}
  Implement report: ${implementReport}
  Test report:      ${testReport}
  Report to write:  ${reviewReport}

Instructions:

1. Read the spec file: ${specFile}
   Extract the COMPLETE "## Acceptance Criteria" section — this is your checklist.

2. Read the implement report: ${implementReport}
   Understand what was changed and the decisions made.

3. Read the test report: ${testReport}
   This is historical context. You will run your own fresh tests below.

4. Run the FRESH authoritative test suite (this result determines the verdict, not the test report):
   uv run pytest 2>&1

5. For each acceptance criterion, read the relevant source files and determine one of:
   MET — criterion is fully satisfied by the current code
   PARTIAL — criterion is partially satisfied
   NOT_MET — criterion is not satisfied

6. Determine the verdict:
   PASS — ALL criteria are MET AND fresh pytest passes (exit 0)
   PARTIAL — some criteria are PARTIAL, OR tests pass but some criteria are not fully met
   FAIL — any criterion is NOT_MET, OR fresh pytest fails

   A fresh test failure ALWAYS prevents PASS — even if all acceptance criteria appear met from reading the code.

7. Write the review report to: ${reviewReport}

   Use EXACTLY this format:

   # Review Report — ${stem}

   **Date:** [run: date +%Y-%m-%d]
   **Spec:** ${specFile}
   **Scope:** ${taskNumber !== null ? `Task ${taskNumber}` : 'Full block'}
   **Verdict:** PASS / PARTIAL / FAIL

   ## Acceptance Criteria Check
   | Criterion | Status | Evidence |
   |---|---|---|
   | [criterion text] | MET / PARTIAL / NOT_MET | [file:line or test name] |

   ## Fresh Test Results
   [paste pytest summary — pass/fail counts, any failure output]

   ## Verdict: PASS / PARTIAL / FAIL
   [one paragraph explaining the verdict]

   ## Issues Found
   [list of specific problems — empty section if PASS]

   ## Next Steps
   [what to do based on the verdict]

Return your result using the StructuredOutput tool:
  reportFile: "${reviewReport}"
  verdict: "PASS", "FAIL", or "PARTIAL"
  failureReasons: array of strings describing what failed (empty array if PASS)
  unmetCriteria: array of criterion texts that were NOT_MET or PARTIAL (empty if PASS)
  notes: one-line summary
`, withModel({ label: `review-${reviewAttempts}`, schema: REVIEW_SCHEMA, phase: 'Review' }, reviewModel))

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

  const docResult = await agent(`
You are the documentation agent for the SDLC pipeline. Surgically patch docs/ to reflect the completed implementation.

Target:
  Block:            ${blockId}
  Task:             ${taskNumber !== null ? `Task ${taskNumber}` : 'all tasks'}
  Review report:    ${reviewReport}
  Implement report: ${implementReport}
  Report to write:  ${documentReport}

Instructions:

1. Read the review report: ${reviewReport}
   GATE CHECK: If the verdict is FAIL or PARTIAL, stop immediately.
   Return: success: false, notes: "Blocked — review verdict was not PASS".

2. Read the implement report: ${implementReport}
   Find the "## Files Created or Modified" table. This scopes which source files changed.

3. For each source file in that table, identify which docs/*.md files reference it.
   Search for the filename and the key class/function/method names that changed.
   Use Bash: grep -rl "ClassName\\|function_name\\|filename" docs/ 2>/dev/null

4. Read each relevant doc file (use the Read tool).

5. Surgically patch ONLY the affected sections:
   - Update class signatures, method lists, parameter tables, descriptions that changed
   - Add documentation for any new public APIs
   - Never delete documented items that still exist in the code
   - Keep surrounding unchanged content intact
   - Use the Edit tool — never rewrite entire doc files

6. IMPORTANT: If docs/app-architecture-overview.md needs updating, add it to the
   "NEEDS_REVIEW" section of the document report but do NOT edit that file directly.

7. Write the document report to: ${documentReport}

   Use EXACTLY this format:

   # Documentation Report — ${stem}

   **Date:** [run: date +%Y-%m-%d]
   **Spec:** ${specFile}
   **Verdict gate:** PASS (confirmed)

   ## Docs Patched
   | Doc File | Section Updated | Change Summary |
   |---|---|---|

   ## Docs Flagged NEEDS_REVIEW
   [list any docs that need human review — always include app-architecture-overview.md if it references changed files]

   ## Docs Clean (checked, no changes needed)
   [list any docs checked but requiring no updates]

7. Commit your changes now. Never use git add -A or git add . — stage files explicitly by name.

   Run: git status
   Identify all changed doc files under docs/ and the document report.

   If no doc files were actually patched (only the report was written), commit just the report:
     git add ${documentReport}

   If docs were patched, stage them and the report:
     git add docs/file1.md docs/file2.md ${documentReport}  (list each file explicitly)

   Commit using HEREDOC:
     git commit -m "$(cat <<'EOF'
     docs: update docs for ${stem}

     
     EOF
     )"

   Run: git log --oneline -1
   Capture the short hash from that output.

Return your result using the StructuredOutput tool:
  reportFile: "${documentReport}"
  success: true if docs were checked and report written (even if no changes were needed)
  filesModified: array of doc files that were actually patched (empty array if none needed changes)
  commitHash: the 7-character short hash from git log --oneline -1 (empty string if commit failed)
  notes: one-line summary
`, withModel({ label: 'document', schema: STAGE_SCHEMA, phase: 'Document' }, MODEL.document))

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
// PHASE 7: WRAP-UP — log-work + commit + workflow report
// ================================================================
phase('Wrap-up')

const finalVerdict = lastReviewResult?.verdict || 'NOT_REACHED'
const stageResultsSummary = stageResults
  .map(r => `${r.stage}${r.attempt ? `(#${r.attempt})` : ''}: ${r.success ? (r.verdict || 'OK') : 'FAILED'}`)
  .join(' → ')

log(`Wrap-up. Final verdict: ${finalVerdict}. Pipeline: ${stageResultsSummary}`)

// ----------------------------------------------------------------
// LOG-WORK: update STATUS.md + append DEVLOG entry
// ----------------------------------------------------------------
log('Running log-work...')

const wrapupResult = await agent(`
You are the log-work agent for the SDLC pipeline. Update STATUS.md and append a DEVLOG entry.

Target:
  Block:           ${blockId}
  Task:            ${taskNumber !== null ? `Task ${taskNumber}` : 'all tasks (full block)'}
  Final verdict:   ${finalVerdict}
  Review attempts: ${reviewAttempts}
  Pipeline summary: ${stageResultsSummary}

Instructions:

1. Read planning/STATUS.md
2. Read ${specFile}
3. Read DEVLOG.md (at the repo root — NOT in planning/)
4. Run: git log --oneline -10
   (Code and doc changes are already committed by their respective agents — git log shows the full picture)

6. Update planning/STATUS.md using the Edit tool:
   ${taskNumber !== null
     ? `- Task ${taskNumber} is done. Check if there are more tasks in the block.
        - If more tasks remain: keep block status as "In progress", update "Current focus" to the next task.
        - If this was the last task: flip block status to "Done", update "Current focus" to the next block.`
     : `- Full block "${blockId}" is done. Flip its Status to "Done" in the Progress Table.
        - Update "Current focus" to the next block or phase.`}
   - Update "Last updated" — run: date +%Y-%m-%d

7. Append a new entry to DEVLOG.md (prepend at the TOP, newest entries first).
   The entry must follow this format:

   ## [YYYY-MM-DD — run date +%Y-%m-%d to get this]
   [One paragraph: what was implemented, how the review went (${finalVerdict} verdict${reviewAttempts > 1 ? ` after ${reviewAttempts} attempts` : ''}), any notable findings, decisions made. End with: "Next: [next task or block]."]

   \`\`\`
   [git log --oneline -5 output — shows the commits made during this pipeline run]
   \`\`\`

8. If the implement report's "Decisions and Trade-offs" section contains any settled architectural choices, mention them in your notes — but do NOT edit DECISIONS.md yourself (that is a manual step).

Return your result using the StructuredOutput tool:
  statusUpdated: true if STATUS.md was successfully updated
  devlogUpdated: true if DEVLOG.md was successfully updated
  nextFocus: the new "Current focus" value written to STATUS.md
  notes: any settled decisions that should be added to DECISIONS.md
`, withModel({ label: 'log-work', schema: WRAPUP_SCHEMA, phase: 'Wrap-up' }, MODEL.logWork))

if (wrapupResult) {
  stageResults.push({ stage: 'log-work', ...wrapupResult, success: wrapupResult.statusUpdated && wrapupResult.devlogUpdated })
  if (wrapupResult.notes) log(`Decisions to log: ${wrapupResult.notes}`)
} else {
  stageResults.push({ stage: 'log-work', success: false, notes: 'Agent returned null' })
}

// ----------------------------------------------------------------
// FINALIZE: commit + write workflow report
// ----------------------------------------------------------------
log('Running finalize: commit + workflow report...')

const stageTable = stageResults.map(r => {
  const label = r.stage + (r.attempt ? ` (attempt ${r.attempt})` : '')
  const status = r.verdict ? r.verdict : (r.success ? 'completed' : 'FAILED')
  const file = r.reportFile || r.workflowReportFile || '—'
  const commit = r.commitHash ? r.commitHash.substring(0, 7) : '—'
  const notes = (r.notes || '').substring(0, 60)
  return `| ${label} | ${status} | ${file} | ${commit} | ${notes} |`
}).join('\n')

const finalizeResult = await agent(`
You are the finalize agent for the SDLC pipeline. Write the workflow report and make the final wrap-up commit.

Context: Code, doc, and fix changes have already been committed by their respective agents during the pipeline run.
Your job is to write the workflow report, then commit the remaining planning files (STATUS.md, DEVLOG.md,
test/review reports, and the workflow report itself) as a single chore: commit.

Target:
  Block:          ${blockId}
  Task:           ${taskNumber !== null ? `Task ${taskNumber}` : 'all tasks'}
  Final verdict:  ${finalVerdict}
  Review attempts: ${reviewAttempts}
  Workflow report to write: ${workflowReport}

Stage results so far:
${stageResultsSummary}

STEP 1 — Get the full commit history from this pipeline run:
  Run: git log --oneline -15
  These are the commits made during this run (implement, fix passes, docs).

STEP 2 — Write the workflow report to: ${workflowReport}

  Use EXACTLY this format:

  # SDLC Workflow Report — ${blockId}${taskNumber !== null ? ` Task ${taskNumber}` : ''}

  **Date:** [run: date +%Y-%m-%d]
  **Block:** ${blockId}
  **Task scope:** ${taskNumber !== null ? `Task ${taskNumber}` : 'All tasks'}
  **Pipeline started from:** ${scout.startStage}
  **Review attempts:** ${reviewAttempts} of ${MAX_REVIEW_ATTEMPTS} max

  ## Final Verdict
  ${finalVerdict} — [one sentence explanation]

  ## Stage Results

  | Stage | Status | Report | Commit | Notes |
  |---|---|---|---|---|
  ${stageTable}

  ## Key Findings
  [Summarize: what was implemented, any known bugs from CLAUDE.md that were touched, notable decisions]

  ## Files Modified
  [List source files that were created or modified — from the implement report]

  ## Docs Updated
  [List doc files patched — from the document report; list any NEEDS_REVIEW flags]

  ## Commits (this pipeline run)
  [Paste the relevant lines from git log --oneline — the implement, fix, docs commits made during this run]

STEP 3 — Commit the remaining planning files as a single chore: commit.
  Never use git add -A or git add . — stage files explicitly by name.

  Run: git status
  Look for any uncommitted files in: planning/STATUS.md, DEVLOG.md,
  ${testReport}, ${reviewReport},
  and ${workflowReport} (which you just wrote).

  Stage them:
    git add planning/STATUS.md DEVLOG.md ${workflowReport}
    git add ${testReport} 2>/dev/null || true
    git add ${reviewReport} 2>/dev/null || true
    (only add files that actually exist and are untracked/modified)

  Commit using HEREDOC:
    git commit -m "$(cat <<'EOF'
    chore: wrap up ${stem}

    
    EOF
    )"

  Run: git log --oneline -1
  Capture the short hash.

Return your result using the StructuredOutput tool:
  workflowReportFile: "${workflowReport}"
  commitMessage: "chore: wrap up ${stem}"
  commitHash: the 7-character short hash from git log --oneline -1
  notes: any follow-up items (decisions to add to DECISIONS.md, NEEDS_REVIEW doc flags)
`, withModel({ label: 'finalize', schema: FINALIZE_SCHEMA, phase: 'Wrap-up' }, MODEL.finalize))

if (finalizeResult) {
  stageResults.push({ stage: 'finalize', ...finalizeResult, success: true })
  log(`Committed: ${finalizeResult.commitMessage}`)
  log(`Workflow report: ${finalizeResult.workflowReportFile}`)
} else {
  stageResults.push({ stage: 'finalize', success: false, notes: 'Agent returned null' })
  log('Finalize agent returned null — manual commit and workflow report may be needed')
}

log(`Pipeline complete. Verdict: ${finalVerdict} | Attempts: ${reviewAttempts} | Report: ${workflowReport}`)

return {
  blockId,
  taskNumber,
  stem,
  finalVerdict,
  reviewAttempts,
  startStage: scout.startStage,
  workflowReport: finalizeResult?.workflowReportFile || workflowReport,
  commitMessage: finalizeResult?.commitMessage,
  stageResults
}
