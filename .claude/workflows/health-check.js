// =============================================================================
// health-check — Daily SDLC Health Check Workflow
// =============================================================================
//
// Run manually once or twice a day (/health-check) to catch issues early in
// long SDLC runs. Completes in under 5 minutes.
//
// WHAT IT CHECKS
//   8 live code checks — run against the working tree right now:
//     1. ruff lint violation count + which codes (UP042/UP046/B904 = known baseline)
//     2. untracked .py files (deliverables created but not staged → invisible to git)
//     3. pylint: disable comment count (suppression vs genuine fix signal)
//     4. Pydantic field-shadowing warnings on import (silent data-loss risk)
//     5. pytest collected test count vs previous-block baseline
//     6. NEEDS_REVIEW flag count across all task reports
//     7. pytest warning count (≥5 = structural conftest/fixture problem)
//     8. open() calls without encoding= (CLAUDE.md standing rule)
//
//   6 silent failure mode scans — read recent task reports:
//     A. pytest_full PASS without baseline comparison (zero-test tasks passing silently)
//     B. app_import PASS swallowing Pydantic field-shadowing warnings
//     C. pylint score jump > 0.5 with no explanation (suppression not fix)
//     D. CHECK entries with missing output / exit_code fields
//     E. docs/api-reference.md structural corruption (unmatched fences, non-sequential TOC)
//     F. implement reports claiming files created that are still untracked in git
//
// TOP PATTERNS MONITORED
//   - Pre-existing lint used as permanent exemption (ruff/pylint FAILED → review PASS)
//   - CLAUDE.md standing rule violations deferred across an entire block
//   - Parallel worktrees amplifying shared-file write conflicts
//   - Untracked deliverables invisible in implement reports
//
// OUTPUT
//   Phase 1 — Scan:  Find active block, run all checks in parallel (two waves).
//   Phase 2 — Report: Synthesize into a STATUS REPORT with OK/WARNING/CRITICAL per
//                     category, an overall health verdict, and a prioritized action list.
//
// USAGE
//   /health-check
//
// =============================================================================

export const meta = {
  name: 'health-check',
  description: 'Daily SDLC health check — scans recent task reports for failure patterns and silent issues',
  whenToUse: 'Run manually once or twice a day (via /health-check) to catch issues early in long SDLC runs.',
  phases: [
    { title: 'Scan',   detail: 'Detect active block, run 8 live checks + 6 silent-failure-mode scans in parallel' },
    { title: 'Report', detail: 'Synthesize all results into a prioritized STATUS REPORT' },
  ],
}

const REPO_ROOT = '/Users/brandon/Dev/agentic-portfolio/python-orchestration-system'

// ─── Phase 1: Scan ────────────────────────────────────────────────────────────
phase('Scan')
log('Starting daily SDLC health check...')

// ── Step 1: Discover the active block ─────────────────────────────────────────
log('Finding most recently modified reports directory...')

const BLOCK_SCHEMA = {
  type: 'object',
  required: ['blockId', 'reportsDir', 'reportFiles', 'taskNums', 'previousTestCount'],
  properties: {
    blockId: {
      type: 'string',
      description: 'Block directory name, e.g. "phase0-blockD"',
    },
    reportsDir: {
      type: 'string',
      description: 'Absolute path to the most recently modified reports directory',
    },
    reportFiles: {
      type: 'array',
      items: { type: 'string' },
      description: 'All filenames found in the active reports directory (basenames only)',
    },
    taskNums: {
      type: 'array',
      items: { type: 'integer' },
      description: 'Sorted unique task numbers present (parsed from taskN-*.md filenames)',
    },
    maxTaskNum: {
      type: 'integer',
      description: 'Highest task number present in the block, or -1 if none',
    },
    previousTestCount: {
      type: 'integer',
      description: 'pytest collected count from the most recent test.md file, or -1 if not parseable',
    },
    blockWorkflowHasNeedsReview: {
      type: 'boolean',
      description: 'true if block-workflow.md contains a NEEDS_REVIEW acknowledgement section',
    },
  },
}

const blockInfo = await agent(
  `You are a build health scanner for the Python orchestration project at ${REPO_ROOT}.

Your job: find the most recently active reports directory and extract key metadata.

STEP 1 — Find all reports directories:
  Run: find ${REPO_ROOT}/planning/tasks -maxdepth 2 -name "reports" -type d

STEP 2 — Identify the most recently modified one:
  For each reports directory, run: ls -lt <dir> 2>/dev/null | head -2
  Pick the directory whose most recently modified file has the latest timestamp.

STEP 3 — List its contents:
  Run: ls -1 <reportsDir>

STEP 4 — Parse task numbers:
  From the filenames, extract all unique task numbers N from "taskN-*.md" patterns.
  Sort them ascending.

STEP 5 — Find the highest-numbered test.md:
  Identify the test report for the highest task number, e.g. task11-test.md.
  Read it (use Read tool on the absolute path).
  Search the content for a pytest collected count: look for patterns like
    "N tests collected", "collected N items", "N passed", or a json field "collected".
  Extract the integer count. Return -1 if no count found.

STEP 6 — Check block-workflow.md for NEEDS_REVIEW acknowledgement:
  If <reportsDir>/block-workflow.md exists, read it and check whether it contains
  a section or heading that includes "NEEDS_REVIEW" and acknowledges flagged items.
  Return true if such a section exists, false if absent or file missing.

Return: blockId (directory name under planning/tasks/), reportsDir (absolute path),
reportFiles (basenames), taskNums (sorted integers), maxTaskNum, previousTestCount, blockWorkflowHasNeedsReview.`,
  { label: 'discover-block', phase: 'Scan', schema: BLOCK_SCHEMA }
)

if (!blockInfo) {
  log('CRITICAL: Could not discover active block. Aborting.')
  return { error: 'Block discovery failed — no reports directories found' }
}

log(`Active block: ${blockInfo.blockId}`)
log(`Reports dir:  ${blockInfo.reportsDir}`)
log(`Tasks found:  ${(blockInfo.taskNums || []).join(', ')} (max: ${blockInfo.maxTaskNum})`)
log(`Test baseline: ${blockInfo.previousTestCount === -1 ? 'unknown' : blockInfo.previousTestCount + ' tests'}`)

// ── Step 2: Live health checks (parallel) ─────────────────────────────────────
log('Running 8 live health checks in parallel...')

const CHECK_SCHEMA = {
  type: 'object',
  required: ['checkName', 'status', 'rawValue', 'detail', 'actionRequired'],
  properties: {
    checkName: {
      type: 'string',
      description: 'Short identifier for this check',
    },
    status: {
      type: 'string',
      enum: ['OK', 'WARNING', 'CRITICAL'],
      description: 'OK = clean state, WARNING = needs attention, CRITICAL = blocks pipeline or data-loss risk',
    },
    rawValue: {
      type: 'string',
      description: 'The exact output, count, or value returned by the command',
    },
    detail: {
      type: 'string',
      description: '1-3 sentences explaining what was found and why it matters',
    },
    actionRequired: {
      type: 'string',
      description: 'Specific action to take if WARNING or CRITICAL. Empty string if OK.',
    },
  },
}

const liveChecks = await parallel([

  // CHECK 1 — ruff lint violations
  () => agent(
    `You are a build health scanner. Run this from ${REPO_ROOT}:

COMMAND A (preferred):
  cd ${REPO_ROOT} && uv run ruff check app/ --format=json 2>/dev/null | python3 -c "import json,sys; v=json.load(sys.stdin); codes=sorted(set(x['code'] for x in v)); print(len(v),'violations:',codes); sys.exit(0 if not v else 1)"

If the JSON pipe fails, fall back to:
  cd ${REPO_ROOT} && uv run ruff check app/ 2>&1 | tail -10

INTERPRETATION RULES:
  - 0 violations → OK
  - Violations ONLY in {UP042, UP046, B904} → WARNING
    (these are the known persistent non-auto-fixable violations from blockC/blockD;
     flag them so the engineer knows the baseline but do not escalate to CRITICAL)
  - Any violation NOT in {UP042, UP046, B904} → CRITICAL (new lint debt introduced)
  - More than 10 total violations regardless of codes → CRITICAL

Set checkName to "ruff-lint-violations".
rawValue: the exact violation summary line (e.g. "3 violations: ['B904', 'UP042']").`,
    { label: 'check-ruff', phase: 'Scan', schema: CHECK_SCHEMA }
  ),

  // CHECK 2 — untracked Python files
  () => agent(
    `You are a build health scanner. Run this from ${REPO_ROOT}:

COMMAND:
  cd ${REPO_ROOT} && git status --short | grep '^??' | grep '\\.py$'

If the output is empty, also run:
  cd ${REPO_ROOT} && git status --short | grep '^??' | grep -E '\\.(md|json)$' | head -5

INTERPRETATION RULES:
  - No untracked .py files → OK
  - Any untracked .py files → CRITICAL
    (deliverables created but not staged are invisible to git; they will be absent
     from any merge, indistinguishable from a clean merge; this is a documented
     silent failure mode from blockC-task6 through blockD)

Set checkName to "untracked-python-files".
rawValue: the raw command output, or "none" if empty.`,
    { label: 'check-untracked', phase: 'Scan', schema: CHECK_SCHEMA }
  ),

  // CHECK 3 — pylint: disable count
  () => agent(
    `You are a build health scanner. Run this from ${REPO_ROOT}:

COMMAND A — count:
  cd ${REPO_ROOT} && grep -rn 'pylint: disable' app/ 2>/dev/null | wc -l

COMMAND B — detail (which files):
  cd ${REPO_ROOT} && grep -rn 'pylint: disable' app/ 2>/dev/null | head -20

INTERPRETATION RULES:
  - Count 0–3 → OK (minimal suppression, acceptable)
  - Count 4–8 → WARNING (accumulating; an increase without a pylint score improvement
    is a suppression signal; document which files own the disables)
  - Count > 8 → CRITICAL (systemic suppression pattern; cross-reference with pylint
    score: if score is 10.00/10 with this many disables, that is suppression not quality)

Set checkName to "pylint-disable-count".
rawValue: the integer count as a string.
detail: include the files that contain the most disable comments.`,
    { label: 'check-pylint-disable', phase: 'Scan', schema: CHECK_SCHEMA }
  ),

  // CHECK 4 — Pydantic field-shadowing on import
  () => agent(
    `You are a build health scanner. Run this from ${REPO_ROOT}:

COMMAND (capture stderr — that is where Python/Pydantic warnings appear):
  cd ${REPO_ROOT} && python3 -c "import sys; sys.path.insert(0, 'app'); import app.main" 2>&1 | grep -cE 'UserWarning|shadows an attribute'

If the above import fails due to missing runtime deps (DB not running, etc.), try:
  cd ${REPO_ROOT} && python3 -c "import sys; sys.path.insert(0, 'app'); import app.core.workflow" 2>&1 | grep -cE 'UserWarning|shadows an attribute'

Then also run the full import to capture the raw warning text:
  cd ${REPO_ROOT} && python3 -c "import sys; sys.path.insert(0, 'app'); import app.main" 2>&1 | grep -E 'UserWarning|shadows an attribute' | head -10

INTERPRETATION RULES:
  - Count 0 → OK
  - Count > 0 → CRITICAL
    (Pydantic field shadowing means the child field silently wins over the parent
     field during serialization; callers receive wrong data with no error raised;
     this is a documented data-loss bug from blockD-task4 and task5 affecting
     MonitorPageDiff and MonitorPageSnapshot; any recurrence must be fixed before
     the next implement stage)

Set checkName to "pydantic-field-shadowing".
rawValue: the count as a string, plus any model names visible in the warning text.`,
    { label: 'check-pydantic', phase: 'Scan', schema: CHECK_SCHEMA }
  ),

  // CHECK 5 — pytest test count vs baseline
  () => agent(
    `You are a build health scanner. Run this from ${REPO_ROOT}:

COMMAND:
  cd ${REPO_ROOT} && uv run pytest --collect-only -q 2>/dev/null | tail -3

Parse the collected count from a line like "N tests collected" or "N selected".

BASELINE: ${blockInfo.previousTestCount}

INTERPRETATION RULES:
  - Baseline is -1 (unknown) → return the count as informational with status WARNING
    (no baseline to compare; record this count for the next run)
  - Current count > baseline → OK (tests were added; note how many)
  - Current count === baseline → WARNING
    (the most recent task added no tests; acceptable only if the task was infrastructure-only;
     flag so the engineer can confirm intentionality)
  - Current count < baseline → CRITICAL
    (tests were removed or a collection error is silently filtering modules;
     a drop from 110 to 97 went unreported in blockC-task10; this must not repeat)

Set checkName to "pytest-test-count".
rawValue: the collected count as a string (e.g. "182 tests collected").
detail: explicitly state the comparison: "current=N, baseline=${blockInfo.previousTestCount}, delta=+/-X".`,
    { label: 'check-test-count', phase: 'Scan', schema: CHECK_SCHEMA }
  ),

  // CHECK 6 — NEEDS_REVIEW flags
  () => agent(
    `You are a build health scanner. Run this from ${REPO_ROOT}:

COMMAND A — total count across all blocks:
  cd ${REPO_ROOT} && grep -rn 'NEEDS_REVIEW' planning/tasks/*/reports/*.md 2>/dev/null | wc -l

COMMAND B — which files have the flags:
  cd ${REPO_ROOT} && grep -rn 'NEEDS_REVIEW' planning/tasks/*/reports/*.md 2>/dev/null | head -20

COMMAND C — check if block-workflow.md acknowledges them:
  grep -l 'NEEDS_REVIEW' ${blockInfo.reportsDir}/block-workflow.md 2>/dev/null

blockWorkflowHasNeedsReview from discovery: ${blockInfo.blockWorkflowHasNeedsReview}

INTERPRETATION RULES:
  - Count 0–5 → OK
  - Count 6–10 → WARNING (accumulating flags; review if they are being tracked)
  - Count > 10 AND block-workflow.md has no NEEDS_REVIEW acknowledgement → CRITICAL
    (flags are accumulating without any block-level acknowledgement; this converts
     a review gate into a silent advisory that agents routinely ignore)
  - Count > 10 AND block-workflow.md DOES acknowledge them → WARNING (not CRITICAL)

Set checkName to "needs-review-flags".
rawValue: the total count as a string.
detail: break down which blocks/tasks own the flags.`,
    { label: 'check-needs-review', phase: 'Scan', schema: CHECK_SCHEMA }
  ),

  // CHECK 7 — pytest warning count
  () => agent(
    `You are a build health scanner. Run this from ${REPO_ROOT}:

COMMAND:
  cd ${REPO_ROOT} && uv run pytest -x --tb=no -q 2>&1 | grep -E '^[0-9]+ warning'

If that returns nothing, also try:
  cd ${REPO_ROOT} && uv run pytest --tb=no -q 2>&1 | grep -E 'warning' | tail -5

INTERPRETATION RULES:
  - 0 warnings → OK
  - 1–4 warnings → WARNING (monitor; single-test-run warnings may be transient)
  - 5 or more warnings → CRITICAL
    (5+ is the documented threshold; this count appeared consistently across independent
     worktrees in blockD tasks 4 and 11, indicating structural conftest or fixture
     warnings that need investigation rather than silent acceptance; transient warnings
     do not persist across isolation boundaries)

Set checkName to "pytest-warnings".
rawValue: the matched line (e.g. "7 warnings") or "0 warnings" if nothing matched.`,
    { label: 'check-pytest-warnings', phase: 'Scan', schema: CHECK_SCHEMA }
  ),

  // CHECK 8 — open() without encoding=
  () => agent(
    `You are a build health scanner. Run this from ${REPO_ROOT}:

COMMAND A — count:
  cd ${REPO_ROOT} && grep -rn 'open(' app/ 2>/dev/null | grep -v 'encoding=' | grep '\\.py:' | grep -v '__pycache__' | wc -l

COMMAND B — exact locations:
  cd ${REPO_ROOT} && grep -rn 'open(' app/ 2>/dev/null | grep -v 'encoding=' | grep '\\.py:' | grep -v '__pycache__'

INTERPRETATION RULES:
  - Count 0 → OK (CLAUDE.md standing rule satisfied)
  - Count > 0 → CRITICAL
    (CLAUDE.md mandates encoding='utf-8' on ALL open() calls; this is a non-waivable
     standing rule; reviewers consistently phrased these as "follow-up work" throughout
     blockC and blockD even though the rule is explicit; the known offender is
     app/services/prompt_loader.py lines 75 and 104; any recurrence is a regression)

Set checkName to "open-without-encoding".
rawValue: the count as a string.
detail: list every file:line that has open() without encoding=.`,
    { label: 'check-open-encoding', phase: 'Scan', schema: CHECK_SCHEMA }
  ),

])

const validLiveChecks = liveChecks.filter(Boolean)
log(`Live checks: ${validLiveChecks.length}/8 completed`)
log(validLiveChecks.map(c => `  ${c.status.padEnd(8)} ${c.checkName}: ${c.rawValue}`).join('\n'))

// ── Step 3: Silent failure mode scans (parallel) ──────────────────────────────
log('Scanning task reports for silent failure mode patterns...')

const PATTERN_SCHEMA = {
  type: 'object',
  required: ['patternName', 'status', 'evidence', 'detail', 'actionRequired'],
  properties: {
    patternName: {
      type: 'string',
      description: 'Short identifier for this failure pattern',
    },
    status: {
      type: 'string',
      enum: ['OK', 'WARNING', 'CRITICAL'],
    },
    evidence: {
      type: 'array',
      items: { type: 'string' },
      description: 'Specific file names and quoted text excerpts that triggered this finding',
    },
    detail: {
      type: 'string',
      description: 'What was found, why it matters, and what downstream effect it could have',
    },
    actionRequired: {
      type: 'string',
      description: 'What to do. Empty string if status is OK.',
    },
  },
}

const silentModeScans = await parallel([

  // PATTERN A — pytest_full PASS without baseline comparison
  () => agent(
    `You are an SDLC audit agent reading task report files at ${blockInfo.reportsDir}.

PATTERN: "pytest_full PASS without baseline comparison"
RISK: A task that added zero tests still shows pytest_full: PASS if the inherited suite passes.
      Test count drops (e.g. 110→97) go unreported because no report compares to the prior count.

WHAT TO CHECK:
1. List the test reports: ls -1t ${blockInfo.reportsDir}/*-test.md 2>/dev/null | head -6
2. Read the 2–3 most recent test.md files (Read tool, absolute paths).
3. For each, look for:
   - Does it reference a previous test count or baseline?
   - Does it say how many NEW tests were added (not just the total)?
   - Does the count differ from prior reports and is that difference explained?
4. If baseline comparison is consistently absent → WARNING.
   If you can find an unexplained count drop (current < prior with no explanation) → CRITICAL.

Set patternName to "pytest-no-baseline-comparison".
evidence: include specific quotes from the reports and the counts you observed.`,
    { label: 'pattern-test-baseline', phase: 'Scan', schema: PATTERN_SCHEMA }
  ),

  // PATTERN B — app_import PASS swallowing Pydantic warnings
  () => agent(
    `You are an SDLC audit agent reading task report files at ${blockInfo.reportsDir}.

PATTERN: "app_import PASS swallowing Pydantic field-shadowing warnings"
RISK: CHECK 1 (app_import) returns exit code 0 and is marked PASS even when Pydantic
      emits field-shadowing UserWarnings. This masks a data-loss serialization bug
      (child field silently wins over parent field with no runtime error).

WHAT TO CHECK:
1. Run: grep -rl 'shadows\|UserWarning\|field.shadow\|non.fatal\|non-fatal' ${blockInfo.reportsDir}/*-test.md 2>/dev/null
2. Read any matching files.
3. Look for: app_import or CHECK 1 recorded as PASS/passed: true WHILE the same report
   also mentions "field shadowing", "shadows an attribute", "UserWarning", or "non-fatal".
4. If any test.md shows this pattern → CRITICAL.
   If the current live import check (from the live checks phase) is clean → WARNING (historical only).

Set patternName to "import-swallowing-pydantic-warnings".
evidence: quote the specific lines that show the contradiction (PASS + shadowing mention).`,
    { label: 'pattern-pydantic-import', phase: 'Scan', schema: PATTERN_SCHEMA }
  ),

  // PATTERN C — pylint sudden score jump with no explanation
  () => agent(
    `You are an SDLC audit agent reading task report files at ${blockInfo.reportsDir}.

PATTERN: "pylint sudden PASS with no explanation of what changed"
RISK: A score jump > 0.5 points between tasks, or a sudden 10.00/10, without any
      explanation of which violations were fixed. This is the signature of suppression
      via inline # pylint: disable comments or .pylintrc changes rather than genuine fixes.
      (Documented: blockC ran at 9.29/10 through task13; task14 suddenly showed PASS with
      all 14 recurring issues gone simultaneously and no explanation.)

WHAT TO CHECK:
1. Run: grep -h 'pylint\|score\|10\.00\|9\.[0-9]\|8\.[0-9]' ${blockInfo.reportsDir}/*-test.md 2>/dev/null | head -30
2. Extract pylint scores per task and check for jumps > 0.5.
3. For any jump found, check the corresponding workflow.md for an explanation.
4. Also run: grep -c 'pylint: disable' ${REPO_ROOT}/app/ -r 2>/dev/null  (or check the live checks result)

INTERPRETATION:
  - Scores consistent across tasks (±0.3) → OK
  - Jump 0.5–1.0 with a clear explanation in workflow.md → WARNING (verify the explanation)
  - Jump > 1.0 OR score reached 10.00 with no explanation → CRITICAL

Set patternName to "pylint-unexplained-score-jump".
evidence: include the score values per task and any explanation text found (or its absence).`,
    { label: 'pattern-pylint-jump', phase: 'Scan', schema: PATTERN_SCHEMA }
  ),

  // PATTERN D — CHECK entries with missing output/exit_code
  () => agent(
    `You are an SDLC audit agent reading task report files at ${blockInfo.reportsDir}.

PATTERN: "CHECK result entries with missing output and exit_code fields"
RISK: A test.md with CHECK entries that have only a test_purpose/description and no
      structured exit_code or output field provides zero evidence the check actually ran.
      Prose claims like "collected 174 tests" in free text are not parseable and produce
      invalid baselines for cross-task comparison.
      (Documented: blockD-task10 CHECK 7 and CHECK 8 had only test_purpose; the 174-test
      claim appeared only in conclusion prose, not in a structured field.)

WHAT TO CHECK:
1. List the 3 most recent test.md files: ls -1t ${blockInfo.reportsDir}/*-test.md 2>/dev/null | head -3
2. Read each one.
3. For each CHECK entry (look for "CHECK 1" through "CHECK 8" headings or similar patterns):
   - Does it have a field clearly labeled exit_code with an integer?
   - Does it have a field clearly labeled output with a non-empty string?
   - Or does it only have a purpose/description and prose conclusions?
4. If recent test.md files have CHECK entries with no structured exit_code/output → CRITICAL.

Set patternName to "check-entries-missing-fields".
evidence: name the specific files and CHECK numbers that lack structured output.`,
    { label: 'pattern-missing-fields', phase: 'Scan', schema: PATTERN_SCHEMA }
  ),

  // PATTERN E — docs/api-reference.md structural corruption
  () => agent(
    `You are an SDLC audit agent checking for documentation structural corruption.

PATTERN: "Document stage TOC edits from parallel worktrees corrupting shared docs"
RISK: Multiple tasks independently renumber the TOC in docs/api-reference.md then merge
      sequentially. This produces duplicate entries, non-sequential section numbers, and
      mismatched code fences. (Documented: blockD tasks 3, 6, 7, 8 each passed their
      document stage but sequential merges corrupted the TOC; task11 had to repair it.)

WHAT TO CHECK:
1. Count code fences (must be even — each opening \`\`\` needs a closing \`\`\`):
   Run: grep -c '^\`\`\`' ${REPO_ROOT}/docs/api-reference.md 2>/dev/null
   Odd count → code fence not closed → CRITICAL.

2. Check for duplicate TOC entries (same number appearing twice):
   Run: grep -n '^[[:space:]]*[0-9]\+\\.' ${REPO_ROOT}/docs/api-reference.md 2>/dev/null | head -50
   Look for repeated numbers.

3. Check for non-sequential numbering (e.g. 1, 2, 4 — skipping 3):
   Examine the same output for gaps.

4. Check for "<<<" merge conflict markers:
   Run: grep -c '^<<<<<<' ${REPO_ROOT}/docs/api-reference.md 2>/dev/null

INTERPRETATION:
  - Even fence count + sequential TOC + no conflicts → OK
  - Odd fence count OR conflict markers → CRITICAL
  - Duplicate/non-sequential TOC numbers → WARNING

Set patternName to "doc-toc-structural-corruption".
evidence: include the fence count, any duplicate TOC line numbers, and conflict marker count.`,
    { label: 'pattern-doc-corruption', phase: 'Scan', schema: PATTERN_SCHEMA }
  ),

  // PATTERN F — implement reports claiming untracked deliverables
  () => agent(
    `You are an SDLC audit agent checking for a gap between implement reports and git state.

PATTERN: "Implement report claiming files were created when files are untracked"
RISK: An implement report lists files under "Files Created" or "Deliverables" or
      "filesCreated" that do not appear in git as tracked (they show as '??' in git status).
      The implement stage declares success while the deliverable is invisible to git.
      A merge of the worktree branch then produces no implementation of the feature.
      (Documented: at least 11 tasks across blockC and blockD showed this pattern.)

WHAT TO CHECK:
1. Get current untracked Python and test files:
   Run: cd ${REPO_ROOT} && git status --short | grep '^??' | grep -E '\\.(py|md)$'

2. Find the most recent implement.md:
   Run: ls -1t ${blockInfo.reportsDir}/*-implement.md 2>/dev/null | head -1

3. Read that implement.md and extract any file paths listed under sections titled
   "Files Created", "Deliverables", "filesCreated", or similar.

4. Cross-reference: if any file listed as created in the implement report appears in
   git status as untracked ('??') → CRITICAL.
   If git status is clean but older sessions left untracked files → WARNING.
   If git status is clean and implement report lists files that ARE tracked → OK.

Set patternName to "implement-untracked-deliverables".
evidence: list the untracked file paths found and which implement report claimed them.`,
    { label: 'pattern-untracked-deliverables', phase: 'Scan', schema: PATTERN_SCHEMA }
  ),

])

const validPatterns = silentModeScans.filter(Boolean)
log(`Silent failure scans: ${validPatterns.length}/6 completed`)
log(validPatterns.map(p => `  ${p.status.padEnd(8)} ${p.patternName}`).join('\n'))

// ─── Phase 2: Report ──────────────────────────────────────────────────────────
phase('Report')
log('Synthesizing findings into STATUS REPORT...')

const allFindings = [...validLiveChecks, ...validPatterns]
const criticalItems = allFindings.filter(f => f.status === 'CRITICAL')
const warningItems  = allFindings.filter(f => f.status === 'WARNING')
const okItems       = allFindings.filter(f => f.status === 'OK')
const overallVerdict = criticalItems.length > 0 ? 'CRITICAL'
  : warningItems.length > 0 ? 'WARNING'
  : 'HEALTHY'

log(`Overall verdict: ${overallVerdict} — ${criticalItems.length} CRITICAL, ${warningItems.length} WARNING, ${okItems.length} OK`)

const report = await agent(
  `You are an SDLC health analyst. Produce a clear, actionable STATUS REPORT from these findings.

CONTEXT
  Active block:  ${blockInfo.blockId}
  Reports dir:   ${blockInfo.reportsDir}
  Tasks in block: ${(blockInfo.taskNums || []).join(', ')}
  Test baseline:  ${blockInfo.previousTestCount === -1 ? 'unknown' : blockInfo.previousTestCount + ' tests'}
  Verdict:        ${overallVerdict} (${criticalItems.length} CRITICAL, ${warningItems.length} WARNING, ${okItems.length} OK)

LIVE HEALTH CHECK RESULTS (8 checks run against working tree)
${JSON.stringify(validLiveChecks, null, 2)}

SILENT FAILURE MODE SCAN RESULTS (6 patterns checked in task reports)
${JSON.stringify(validPatterns, null, 2)}

TOP PATTERNS TO WATCH (from known SDLC failure history):
  1. Pre-existing lint used as permanent exemption — ruff/pylint FAILED → review overrides to PASS
  2. CLAUDE.md standing rule violations deferred across an entire block (f-strings in logging,
     open() without encoding, parameter named "id")
  3. Parallel worktrees amplifying shared-file write conflicts in docs/ files
  4. Untracked deliverables invisible in implement reports (the deliverable was never git-added)

Produce the STATUS REPORT in this exact format:

---
## SDLC Health Check — ${blockInfo.blockId}
**Overall Verdict: ${overallVerdict}**
*${criticalItems.length} CRITICAL | ${warningItems.length} WARNING | ${okItems.length} OK*

### Live Code Checks
| Check | Status | Value | Notes |
|---|---|---|---|
[one row per check; use emoji ✓ OK ⚠ WARNING ✗ CRITICAL in the Status column if helpful, but status text is mandatory]

### Silent Failure Mode Scan
| Pattern | Status | Finding |
|---|---|---|
[one row per pattern]

### Issues to Address (prioritized)
[Numbered list. CRITICAL first, then WARNING. Each item must name:
  (1) the specific file or metric,
  (2) what to run or check to confirm,
  (3) what to do to fix it.
No vague "improve X" items — be surgical.]

### What Is Healthy
[Bullet list of checks/patterns that passed cleanly. Be brief.]

### Recommended Next Action
[One sentence: the single highest-priority thing to do before the next SDLC pipeline run.]
---

Be direct. Use exact file names and line numbers from the evidence. Do not soften CRITICAL findings.
Do not invent issues that are not supported by the evidence.`,
  { label: 'synthesize-report', phase: 'Report' }
)

log('Health check complete.')

return {
  blockId: blockInfo.blockId,
  overallVerdict,
  criticalCount: criticalItems.length,
  warningCount: warningItems.length,
  okCount: okItems.length,
  liveChecks: validLiveChecks,
  silentModeScans: validPatterns,
  report,
}
