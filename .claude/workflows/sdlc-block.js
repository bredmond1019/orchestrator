// =============================================================================
// sdlc-block — Block-Level SDLC Orchestration (general, dependency-aware)
// =============================================================================
//
// Drives an ENTIRE block (any planning/tasks/<blockId>/tasks.md) to completion by
// orchestrating many parallel /sdlc-task pipelines across dependency-ordered waves,
// merging each wave before the next begins. Generic: every path derives from blockId,
// exactly like /sdlc-task. Nothing is hardcoded to a specific block.
//
// USAGE
//   /sdlc-block phase0-blockD                     run every task in the block
//   /sdlc-block phase0-blockD 1-7                  run only tasks 1–7 (range/list selection)
//   /sdlc-block phase0-blockD --tasks 1,3,5-7      same selection via explicit flag
//   /sdlc-block phase0-blockD --max-retries 2 --max-wave-width 4
//
//   ARGS
//     <blockId>            required — drives every path (planning/tasks/<blockId>/...)
//     [range]             optional 2nd positional, or --tasks — e.g. 1-7, 1,3,5, 1-3,7. Default: all.
//     --max-retries N     total /sdlc-task attempts per task before escalation (default 2)
//     --max-wave-width W   max full pipelines run concurrently per batch (default 3)
//
// DESIGN (see docs/agentic-workflows/sdlc-dynamic-workflows.md)
//   1. Analyze
//        - Resume-scout: which tasks are already done on main (skip them).
//        - Load planning/tasks/<blockId>/execution-plan.json if present & valid.
//        - Otherwise an agent reads tasks.md + breakdown.md and emits a DEPENDENCY
//          GRAPH WITH EVIDENCE (per task: filesCreated, filesModified, dependsOn,
//          and the quote that establishes each edge) plus an ADDITIVE-file allow-list.
//        - Deterministic JS computes the waves (topological layering + conflict
//          serialization). Agent proposes the graph; CODE computes the waves.
//        - The generated plan is written to execution-plan.json (hand-editable).
//   2. Per wave
//        - Run each task via workflow('sdlc-task', ...) with a RETRY + TRIAGE loop:
//            PASS                          -> merge it
//            RETRYABLE (infra/transient)   -> clean-slate re-run (up to MAX attempts)
//            MAJOR (structural / stuck)    -> ESCALATE: preserve worktree, surface to user
//        - Escalation poisons ONLY the dependent subtree (computed from the graph);
//          independent tasks keep running.
//   3. Merge (per wave, in task-number order)
//        - Plain git merge first; on conflict, union-merge ONLY if every conflicted
//          file is on the additive allow-list, else abort + escalate that task.
//        - STATUS.md / DEVLOG.md are NEVER touched inside worktrees.
//   4. Report
//        - Write block-workflow.md, apply DEVLOG entries + a SINGLE authoritative
//          STATUS.md update (block done/partial, focus -> next block), and print
//          escalations with their worktree paths + the resume command.
//
// RESUMPTION
//   Re-run /sdlc-block <blockId>. Git is the source of truth: a task is "done" if its
//   taskN-workflow.md is committed on main. Done tasks are skipped; escalated tasks are
//   retried (after you fix the blocker or edit execution-plan.json).
//
// =============================================================================

export const meta = {
  name: 'sdlc-block',
  description: 'Orchestrate a full block through dependency-ordered waves of parallel /sdlc-task pipelines, with bounded retries, failure triage, escalation, and ordered merges.',
  whenToUse: 'When driving a block (a tasks.md) to completion across many parallel tasks. Optional task range, e.g. /sdlc-block phase0-blockD 1-7. Usage: /sdlc-block phase0-blockD',
  phases: [
    { title: 'Analyze', detail: 'Resume-scout main, load or generate the dependency-ordered execution plan' },
    { title: 'Wave',    detail: 'Run wave tasks via /sdlc-task with retry + triage; escalate major failures' },
    { title: 'Merge',   detail: 'Merge passing branches in order (additive union only; else escalate)' },
    { title: 'Report',  detail: 'Write block report, apply STATUS/DEVLOG once, surface escalations' },
  ]
}

// ----------------------------------------------------------------
// Parse args: "<blockId> [--max-retries N] [--max-wave-width W]"
// ----------------------------------------------------------------
const rawArgs = typeof args === 'string' ? args.trim() : ''
if (!rawArgs) {
  log('ERROR: No block ID provided.')
  log('Usage: /sdlc-block phase0-blockD [--max-retries 2] [--max-wave-width 4]')
  return { error: 'Missing required argument: block ID' }
}

const tokens = rawArgs.split(/\s+/)
const blockId = tokens[0]

const DEFAULT_MAX_WAVE_WIDTH = 3   // conservative: 3 full pipelines in flight; bump with --max-wave-width

function flag(name, dflt) {
  const i = tokens.indexOf(name)
  if (i === -1 || i + 1 >= tokens.length) return dflt
  const v = parseInt(tokens[i + 1], 10)
  return isNaN(v) ? dflt : v
}
function flagStr(name) {
  const i = tokens.indexOf(name)
  return (i === -1 || i + 1 >= tokens.length) ? null : tokens[i + 1]
}
// Parse a task selection like "1-7", "1,3,5", "1-3,7", or "5" into a sorted int array.
function parseRange(spec) {
  const out = new Set()
  for (const part of spec.split(',')) {
    const m = part.trim().match(/^(\d+)(?:-(\d+))?$/)
    if (!m) return null
    const a = parseInt(m[1], 10), b = m[2] ? parseInt(m[2], 10) : a
    for (let i = Math.min(a, b); i <= Math.max(a, b); i++) out.add(i)
  }
  return [...out].sort((x, y) => x - y)
}

const MAX_TASK_ATTEMPTS = Math.max(1, flag('--max-retries', 2))                 // total sdlc-task runs per task
const MAX_WAVE_WIDTH    = Math.max(1, flag('--max-wave-width', DEFAULT_MAX_WAVE_WIDTH)) // pipelines per batch

// Optional task selection: `--tasks 1-7` OR a positional range as the 2nd token (`/sdlc-block phase0-blockD 1-7`).
// Defaults to ALL tasks in the block.
const rangeSpec = flagStr('--tasks') || (tokens[1] && !tokens[1].startsWith('--') ? tokens[1] : null)
let selectedTasks = null
if (rangeSpec) {
  const parsed = parseRange(rangeSpec)
  if (!parsed || parsed.length === 0) {
    log(`ERROR: could not parse task selection "${rangeSpec}". Use forms like 1-7, 1,3,5, or 1-3,7.`)
    return { error: 'Invalid task selection', rangeSpec, blockId }
  }
  selectedTasks = new Set(parsed)
}

const blockDir    = `planning/tasks/${blockId}`
const tasksFile   = `${blockDir}/tasks.md`
const breakdownFile = `${blockDir}/breakdown.md`
const reportsDir  = `${blockDir}/reports`
const planFile    = `planning/tasks/${blockId}/execution-plan.json`
const blockReport = `${reportsDir}/block-workflow.md`

log(`Block: ${blockId} | plan: ${planFile}`)
log(`Max attempts/task: ${MAX_TASK_ATTEMPTS} | max wave width: ${MAX_WAVE_WIDTH}`)
if (selectedTasks) log(`Task selection: ${[...selectedTasks].sort((a, b) => a - b).join(', ')} (others skipped)`)

// ================================================================
// Schemas
// ================================================================
const ANALYZE_SCHEMA = {
  type: 'object',
  required: ['planExists', 'allTasks', 'doneTasks', 'tasks', 'additiveFiles'],
  properties: {
    planExists: { type: 'boolean', description: 'true if a valid execution-plan.json already existed' },
    allTasks:   { type: 'array', items: { type: 'integer' }, description: 'Every task number in tasks.md' },
    doneTasks:  { type: 'array', items: { type: 'integer' }, description: 'Tasks already completed on main (taskN-workflow.md present, PASS)' },
    preservedWorktrees: { type: 'array', items: { type: 'string' }, description: 'Worktree paths preserved from a prior escalated run' },
    additiveFiles: { type: 'array', items: { type: 'string' }, description: 'Shared files every touching task only APPENDS to (safe to union-merge), e.g. app/services/__init__.py' },
    tasks: {
      type: 'array',
      description: 'One entry per task — the dependency graph with evidence.',
      items: {
        type: 'object',
        required: ['num', 'title', 'dependsOn', 'filesCreated', 'filesModified'],
        properties: {
          num:           { type: 'integer' },
          title:         { type: 'string' },
          dependsOn:     { type: 'array', items: { type: 'integer' }, description: 'Task numbers this task logically depends on' },
          filesCreated:  { type: 'array', items: { type: 'string' } },
          filesModified: { type: 'array', items: { type: 'string' }, description: 'Existing shared files this task edits' },
          evidence:      { type: 'string', description: 'Quote(s) from tasks.md/breakdown.md establishing each dependsOn edge' }
        }
      }
    },
    waves: {
      type: 'array',
      description: 'Present ONLY when planExists: the pre-existing wave structure to use verbatim.',
      items: {
        type: 'object',
        required: ['tasks'],
        properties: {
          label:      { type: 'string' },
          parallel:   { type: 'boolean' },
          tasks:      { type: 'array', items: { type: 'integer' } },
          mergeOrder: { type: 'array', items: { type: 'integer' } }
        }
      }
    },
    notes: { type: 'string' }
  }
}

const TRIAGE_SCHEMA = {
  type: 'object',
  required: ['class', 'reason'],
  properties: {
    class:  { type: 'string', enum: ['RETRYABLE', 'MAJOR'] },
    reason: { type: 'string', description: 'One sentence: why retryable (transient/infra/progressing) or major (stuck/structural/needs user)' },
    sameCriteriaAsBefore: { type: 'boolean', description: 'true if the SAME acceptance criteria failed as the previous attempt' }
  }
}

const MERGE_SCHEMA = {
  type: 'object',
  required: ['taskNum', 'branchName', 'merged', 'strategy', 'escalated'],
  properties: {
    taskNum:        { type: 'integer' },
    branchName:     { type: 'string' },
    merged:         { type: 'boolean' },
    strategy:       { type: 'string', enum: ['auto', 'union', 'aborted'], description: 'auto = clean git merge; union = additive-only conflict; aborted = escalated' },
    conflictedFiles:{ type: 'array', items: { type: 'string' } },
    escalated:      { type: 'boolean', description: 'true if a non-additive conflict forced an abort (worktree preserved)' },
    commitHash:     { type: 'string' },
    notes:          { type: 'string' }
  }
}

const REPORT_SCHEMA = {
  type: 'object',
  required: ['reportFile', 'overallVerdict'],
  properties: {
    reportFile:     { type: 'string' },
    overallVerdict: { type: 'string', enum: ['PASS', 'PARTIAL', 'BLOCKED', 'ALREADY_COMPLETE'] },
    statusUpdated:  { type: 'boolean' },
    nextFocus:      { type: 'string' },
    needsReviewItems: {
      type: 'array',
      description: 'Files flagged NEEDS_REVIEW across all task workflow reports, deduplicated by file path',
      items: {
        type: 'object',
        properties: {
          file:           { type: 'string' },
          flaggedByTasks: { type: 'array', items: { type: 'integer' } },
          reasons:        { type: 'array', items: { type: 'string' } }
        }
      }
    },
    notes:          { type: 'string' }
  }
}

// ================================================================
// Pure helpers — waves & failure blast-radius are computed in CODE
// ================================================================

// Topological layering + conflict serialization. Agent supplies the graph; this turns
// it into ordered waves (one per topological layer — width is NOT baked in here; it's an
// execution-time batching knob, so the persisted plan stays width-independent). Tasks in
// the same wave are mutually independent and share no EXCLUSIVE (non-additive) file.
function computeWaves(taskMap, additiveSet) {
  const nums = Object.keys(taskMap).map(Number).sort((a, b) => a - b)
  const mustFollow = new Map(nums.map(n => [n, new Set()])) // n must run after every task in this set

  // logical dependency edges
  for (const n of nums) {
    for (const d of (taskMap[n].dependsOn || [])) {
      if (taskMap[d]) mustFollow.get(n).add(d)
    }
  }
  // conflict edges: two tasks editing the same EXCLUSIVE file are serialized (lower number first)
  for (let i = 0; i < nums.length; i++) {
    for (let j = i + 1; j < nums.length; j++) {
      const a = nums[i], b = nums[j]
      const modA = new Set(taskMap[a].filesModified || [])
      const clash = (taskMap[b].filesModified || []).some(f => modA.has(f) && !additiveSet.has(f))
      if (clash) mustFollow.get(b).add(a)
    }
  }

  const remaining = new Set(nums)
  const waves = []
  while (remaining.size) {
    const layer = [...remaining].filter(n => [...mustFollow.get(n)].every(d => !remaining.has(d)))
    if (!layer.length) throw new Error(`Dependency cycle among tasks: ${[...remaining].join(', ')}`)
    layer.sort((a, b) => a - b)
    waves.push({
      label: `Wave ${waves.length + 1}`,
      parallel: layer.length > 1,
      tasks: layer,
      mergeOrder: [...layer].sort((a, b) => a - b)
    })
    layer.forEach(n => remaining.delete(n))
  }
  return waves
}

// A task is poisoned if any task it depends on escalated or was itself poisoned.
function isPoisoned(taskNum, taskMap, badSet) {
  return (taskMap[taskNum]?.dependsOn || []).some(d => badSet.has(d))
}

// ================================================================
// PHASE 0: ANALYZE — resume-scout + load/generate the execution plan
// ================================================================
phase('Analyze')
log('Analyzing block: scouting completed tasks and resolving the dependency graph...')

const analysis = await agent(`
You are the analysis agent for a block-level SDLC orchestration. You run from the MAIN repo root.

Block:        ${blockId}
Tasks file:   ${tasksFile}
Breakdown:    ${breakdownFile} (optional)
Plan file:    ${planFile}
Reports dir:  ${reportsDir}

GOAL: produce a dependency graph for every task, list which tasks are already done, and report
whether a hand-written execution plan already exists.

STEP 1 — Check for an existing plan:
  cat ${planFile} 2>/dev/null && echo "PLAN_EXISTS" || echo "NO_PLAN"
  If it exists and is valid JSON with a "waves" array, set planExists=true and return its
  "tasks" graph and "waves" and "additiveFiles" VERBATIM (do not re-derive). Skip to STEP 4.

STEP 2 — Read the spec and (if present) the breakdown:
  cat ${tasksFile}
  ls ${breakdownFile} 2>/dev/null && cat ${breakdownFile} || echo "NO_BREAKDOWN"
  Enumerate every task by its "### N." heading. That set is "allTasks".

STEP 3 — Build the dependency graph. For EACH task determine:
  - filesCreated:  new files the task creates (e.g. app/services/chunking_service.py)
  - filesModified: EXISTING shared files the task edits (e.g. app/services/__init__.py,
                   app/workflows/workflow_registry.py, app/api/endpoint.py).
                   IMPORTANT: also include any docs/*.md file the task will edit. Any task that adds
                   a section to docs/api-reference.md or docs/app-architecture-overview.md MUST list
                   that file in filesModified — TOC renumbering is NOT additive (it changes existing
                   line numbers shared across tasks), so these files must be serialized, not union-merged.
  - dependsOn:     task numbers whose output this task consumes. A depends on B if A's text
                   references a symbol/file B creates (e.g. "delegates to ChunkingService (Task 7)").
  - evidence:      quote the exact phrase(s) from tasks.md/breakdown.md proving each dependsOn edge.
  Then classify shared files into "additiveFiles": a file belongs here if every task that touches it
  only CONTRIBUTES its own independent piece (an export line, a registry entry, a doc section for the
  component IT created) rather than rewriting another task's lines.
  ADDITIVE BY DEFAULT — include these whenever more than one task touches them:
    - Package aggregator __init__.py files (e.g. app/services/__init__.py, app/core/nodes/__init__.py)
      — each task adds an import + an __all__ entry for the symbol it created.
    - Registry files (e.g. app/workflows/workflow_registry.py) — each task appends one enum/registry entry.
    NOT ADDITIVE — do NOT include these in additiveFiles even if multiple tasks touch them:
    - docs/api-reference.md and docs/app-architecture-overview.md: TOC renumbering rewrites existing
      line numbers across every task's sections — parallel edits corrupt each other's numbering.
      These must appear in filesModified (exclusive) so computeWaves() serializes them. This was the
      root cause of blockD TOC corruption (tasks 3, 6, 7, 8 all ran in the same wave and each
      renumbered independently; sequential merges then produced a garbled TOC requiring task11 repair).
    These exact aggregator file kinds falsely serialized a prior block into a dependency CYCLE (an
    __init__.py treated as exclusive, combined with a real dependsOn edge, contradicted the numeric
    conflict-ordering) and then blocked its merges. Treating __init__.py and registry files as
    EXCLUSIVE is the common failure mode — default them to ADDITIVE. But docs/ TOC files are different.
  Stay CONSERVATIVE only for real source modules edited in place (e.g. app/api/endpoint.py, app/main.py,
  a shared node base): if unsure whether one of THOSE is additive, LEAVE IT OUT (treat as exclusive).
  For dependsOn edges: if unsure whether an edge exists, INCLUDE it. Over-serializing logical deps is
  safe; wrongly marking an in-place-edited source module additive is not.

STEP 4 — Resume scout: find tasks already completed on main:
  ls ${reportsDir}/task*-workflow.md 2>/dev/null || echo "NONE"
  For each task N with a task${'${N}'}-workflow.md present, read its Final Verdict; if PASS, add N to doneTasks.
  Additionally, for every task N in allTasks NOT already in doneTasks, check git log for a feat commit:
    git log main --oneline --grep="feat: implement ${blockId}-task<N>"
  If git log returns at least one line but no workflow file exists (or the file has a non-PASS verdict
  such as NOT_REACHED from a stale partial run), write a minimal ${reportsDir}/task<N>-workflow.md:
    echo "# Task <N> Workflow\\n\\nFinal Verdict: ALREADY_COMPLETE\\nCommit: <hash>\\n" > ${reportsDir}/task<N>-workflow.md
    git add ${reportsDir}/task<N>-workflow.md && git commit -m "chore: record ALREADY_COMPLETE for ${blockId}-task<N> (found on main)" || true
  Then add N to doneTasks. This prevents stale NOT_REACHED records from accumulating and gives future
  scouts a clear signal (blockC tasks 10 and 12 both re-initialized worktrees because stale NOT_REACHED
  workflow files misled the scout on resume).
  Also list any worktrees preserved from a prior escalated run:
  git worktree list | grep "trees/${blockId.toLowerCase()}" || echo "NO_WORKTREES"

Return using StructuredOutput:
  planExists:   true only if a valid execution-plan.json was loaded
  allTasks:     every task number
  doneTasks:    completed-on-main task numbers
  preservedWorktrees: paths from prior escalations (or [])
  additiveFiles: shared files safe to union-merge
  tasks:        the dependency graph (one entry per task, with evidence)
  waves:        ONLY if planExists — the loaded wave structure
  notes:        anything notable (ambiguous deps, suspected cycles)
`, { label: 'analyze', schema: ANALYZE_SCHEMA, phase: 'Analyze', model: 'opus' })  // dependency analysis is PLANNING — keep on Opus

if (!analysis) {
  log('Analysis agent returned null — cannot plan the block. Aborting.')
  return { error: 'Analysis failed', blockId }
}

// Build the task map and additive set
const taskMap = {}
for (const t of (analysis.tasks || [])) taskMap[t.num] = t
const additiveSet = new Set(analysis.additiveFiles || [])
const doneTasks = new Set(analysis.doneTasks || [])

if (Object.keys(taskMap).length === 0) {
  log('Analysis produced no tasks — aborting.')
  return { error: 'No tasks resolved from spec', blockId }
}

// Waves: use the loaded plan if present, else compute them deterministically
let waves
if (analysis.planExists && Array.isArray(analysis.waves) && analysis.waves.length) {
  waves = analysis.waves.map((w, i) => ({
    label: w.label || `Wave ${i + 1}`,
    parallel: w.parallel ?? (w.tasks.length > 1),
    tasks: w.tasks,
    mergeOrder: w.mergeOrder || [...w.tasks].sort((a, b) => a - b)
  }))
  log(`Loaded existing plan: ${waves.length} wave(s).`)
} else {
  try {
    waves = computeWaves(taskMap, additiveSet)
  } catch (e) {
    log(`Could not layer tasks into waves: ${e.message}`)
    return { error: 'Wave computation failed', detail: e.message, blockId, taskMap }
  }
  log(`Computed ${waves.length} wave(s) from the dependency graph.`)

  // Persist the generated plan so it is inspectable / hand-editable for re-runs
  const planJson = JSON.stringify({
    blockId,
    additiveFiles: [...additiveSet],
    tasks: taskMap,
    waves
  }, null, 2)

  await agent(`
You run from the MAIN repo root. Write this exact JSON to ${planFile} (create parent dirs if needed)
and commit it. Do not alter the content.

  mkdir -p ${reportsDir}
  Write the file ${planFile} with EXACTLY this content:
\`\`\`json
${planJson}
\`\`\`
  Then: git add ${planFile} && git commit -m "chore: add execution plan for ${blockId}" || echo "nothing to commit"

Return using StructuredOutput: reportFile="${planFile}", success=true.
`, { label: 'write-plan', schema: { type: 'object', required: ['success'], properties: { reportFile: { type: 'string' }, success: { type: 'boolean' } } }, phase: 'Analyze', model: 'haiku' })
}

// Log the plan for visibility
for (const w of waves) {
  const skipped = w.tasks.filter(t => doneTasks.has(t))
  log(`${w.label}: tasks [${w.tasks.join(', ')}]${w.parallel ? ' (parallel)' : ' (sequential)'}${skipped.length ? ` — already done: ${skipped.join(', ')}` : ''}`)
}

// Pre-flight: if a selection was given, warn about prerequisites outside it that aren't done on main.
// These tasks will likely fail and escalate — surface it up front rather than mid-run.
if (selectedTasks) {
  const missingPrereqs = []
  for (const t of selectedTasks) {
    for (const d of (taskMap[t]?.dependsOn || [])) {
      if (!selectedTasks.has(d) && !doneTasks.has(d)) missingPrereqs.push(`task ${t} needs task ${d}`)
    }
  }
  if (missingPrereqs.length) {
    log(`WARNING: selected tasks have unmet prerequisites outside the range (not yet done on main):`)
    for (const m of missingPrereqs) log(`  - ${m}`)
    log(`These tasks may fail and escalate. Widen the range or run the prerequisites first.`)
  }
}

// ================================================================
// Per-task retry + triage state machine
// ================================================================
const badSet = new Set()        // escalated OR poisoned task numbers
const outcomes = []             // { taskNum, status, branchName, worktreePath, finalVerdict, reasons, attempts }
const passedBranches = []       // ready-to-merge: { taskNum, branchName, worktreePath }

async function teardownBranch(branchName, worktreePath) {
  await agent(`
You run from the MAIN repo root. Tear down a failed-attempt worktree so retries don't accumulate.
Run, ignoring errors:
  git worktree remove "${worktreePath}" --force 2>/dev/null || true
  git branch -D "${branchName}" 2>/dev/null || true
  git worktree prune
Confirm with: git worktree list
Return the final worktree list as plain text.
`, { label: `teardown-${branchName}`, phase: 'Analyze', model: 'haiku' })
}

async function runTask(taskNum) {
  let prevReasons = null
  for (let attempt = 1; attempt <= MAX_TASK_ATTEMPTS; attempt++) {
    log(`Task ${taskNum}: attempt ${attempt}/${MAX_TASK_ATTEMPTS} via /sdlc-task...`)
    const r = await workflow('sdlc-task', `${blockId} ${taskNum}`)

    if (r && r.finalVerdict === 'PASS') {
      return { taskNum, status: 'pass', branchName: r.branchName, worktreePath: r.worktreePath, finalVerdict: 'PASS', attempts: attempt }
    }

    // Classify the failure before deciding to retry
    const failBlob = JSON.stringify({
      finalVerdict: r?.finalVerdict ?? 'NULL_RESULT',
      reviewAttempts: r?.reviewAttempts,
      stageResults: r?.stageResults,
      previousFailureReasons: prevReasons
    }, null, 2)

    const triage = await agent(`
You are the failure-triage agent for a block orchestration. A single task's /sdlc-task pipeline did
NOT pass. /sdlc-task already ran up to 3 internal fix passes before returning, so a genuine, repeated
acceptance-criteria failure is unlikely to be fixed by another clean-slate run.

Task: ${blockId} task ${taskNum}, attempt ${attempt} of ${MAX_TASK_ATTEMPTS}.
Pipeline result:
${failBlob}

Classify:
  RETRYABLE — transient/infra (NULL_RESULT, worktree-setup crash, agent died, NOT_REACHED), OR the
              failing criteria CHANGED from the previous attempt (it is making progress).
  MAJOR     — the SAME acceptance criteria failed again, OR the failure is structural (references a
              missing upstream symbol/dependency, wrong wave ordering, or otherwise needs a human to
              re-plan or fix the blocker). When unsure, prefer MAJOR — escalation is cheap, a wasted
              clean-slate retry is not.

Return using StructuredOutput: class, reason, sameCriteriaAsBefore.
`, { label: `triage-${taskNum}-${attempt}`, schema: TRIAGE_SCHEMA, phase: 'Analyze', model: 'sonnet' })

    const reasons = (r?.stageResults || [])
      .filter(s => s.stage === 'review')
      .flatMap(s => s.unmetCriteria || s.failureReasons || [])

    if (!triage || triage.class === 'MAJOR' || attempt === MAX_TASK_ATTEMPTS) {
      const why = triage?.reason || (attempt === MAX_TASK_ATTEMPTS ? 'retries exhausted' : 'triage returned null')
      log(`Task ${taskNum}: ESCALATE — ${why}. Worktree preserved for inspection.`)
      return {
        taskNum, status: 'escalate',
        branchName: r?.branchName, worktreePath: r?.worktreePath,
        finalVerdict: r?.finalVerdict || 'NOT_REACHED',
        reasons, reviewReport: `${reportsDir}/task${taskNum}-review.md`,
        attempts: attempt, triage: triage?.reason
      }
    }

    // RETRYABLE → clean-slate: tear down this attempt's worktree, then loop
    log(`Task ${taskNum}: RETRYABLE — ${triage.reason}. Clean-slate retry.`)
    if (r?.branchName && r?.worktreePath) await teardownBranch(r.branchName, r.worktreePath)
    prevReasons = reasons
  }
  // unreachable, but keep the shape consistent
  return { taskNum, status: 'escalate', finalVerdict: 'NOT_REACHED', reasons: [], attempts: MAX_TASK_ATTEMPTS }
}

// ================================================================
// WAVE LOOP
// ================================================================
for (let wi = 0; wi < waves.length; wi++) {
  const wave = waves[wi]
  const waveLabel = `Wave ${wi + 1}`
  phase(waveLabel)

  // Budget guard: if a token target is set and the remaining can't cover a wave, stop and report.
  // Rough estimate: a full sdlc-task pipeline is ~150k output tokens; size to this wave's width.
  if (budget.total) {
    const estPerTask = 150_000
    const waveCost = Math.min(wave.tasks.length, MAX_WAVE_WIDTH) * estPerTask
    if (budget.remaining() < waveCost) {
      log(`Budget guard: ~${Math.round(budget.remaining() / 1000)}k remaining < ~${Math.round(waveCost / 1000)}k needed for ${waveLabel}. Stopping before overrun — re-run /sdlc-block ${blockId} to resume.`)
      break
    }
  }

  // Decide which tasks actually run: honor selection, skip done (resume) and poisoned (dep escalated)
  const runnable = []
  for (const t of wave.tasks) {
    if (selectedTasks && !selectedTasks.has(t)) { continue }
    if (doneTasks.has(t)) { log(`Task ${t}: already done on main — skipping.`); continue }
    if (isPoisoned(t, taskMap, badSet)) {
      log(`Task ${t}: SKIPPED — depends on an escalated/failed task (${(taskMap[t].dependsOn || []).filter(d => badSet.has(d)).join(', ')}).`)
      badSet.add(t)
      outcomes.push({ taskNum: t, status: 'skipped', reasons: ['blocked by upstream escalation'] })
      continue
    }
    runnable.push(t)
  }

  if (runnable.length === 0) {
    log(`${waveLabel}: nothing runnable — moving on.`)
    continue
  }

  // Execute: parallel waves in batches of MAX_WAVE_WIDTH; sequential waves one at a time
  let waveOutcomes = []
  if (wave.parallel) {
    for (let k = 0; k < runnable.length; k += MAX_WAVE_WIDTH) {
      const batch = runnable.slice(k, k + MAX_WAVE_WIDTH)
      if (batch.length < runnable.length) log(`${waveLabel}: batch [${batch.join(', ')}]`)
      const batchResults = await parallel(batch.map(t => () => runTask(t)))
      waveOutcomes.push(...batchResults.filter(Boolean))
    }
  } else {
    for (const t of runnable) waveOutcomes.push(await runTask(t))
  }

  outcomes.push(...waveOutcomes)
  for (const o of waveOutcomes) {
    if (o.status === 'pass') {
      passedBranches.push({ taskNum: o.taskNum, branchName: o.branchName, worktreePath: o.worktreePath })
    } else if (o.status === 'escalate') {
      badSet.add(o.taskNum)
    }
  }

  // ---- Merge this wave's passing branches, in task-number order ----
  const toMerge = wave.mergeOrder
    .map(t => passedBranches.find(p => p.taskNum === t))
    .filter(Boolean)

  if (toMerge.length) {
    phase(`Merge ${wi + 1}`)
    for (const p of toMerge) {
      log(`Merging task ${p.taskNum} (branch: ${p.branchName})...`)
      const m = await agent(`
You are the merge agent. You run from the MAIN repo root (CWD = the main checkout, on main).
Merge branch "${p.branchName}" (task ${p.taskNum}) into main using a SELECTIVE-UNION strategy.

Additive files (safe to union-merge — every touching task only appends): ${JSON.stringify([...additiveSet])}

STEP 1 — Safety: cd to repo root, ensure clean tree:
  git rev-parse --show-toplevel ; git status --porcelain
  If there are uncommitted changes unrelated to merging, STOP and return merged=false, escalated=true.

STEP 2 — Attempt a normal merge (do NOT use --ff-only; parallel branches share a base):
  git merge --no-ff --no-edit ${p.branchName}
  If it exits 0 with no conflicts -> strategy="auto", merged=true. Go to STEP 4.

STEP 3 — Conflict handling:
  git diff --name-only --diff-filter=U   (the conflicted files)
  - If EVERY conflicted file is in the additive list above, resolve them with git's built-in "union"
    merge driver, which keeps BOTH sides of each conflict (both export lines, both doc sections).
    IMPORTANT: there is NO "git merge -X union" — union is a low-level merge DRIVER, not a strategy
    option. Activate it repo-locally via .git/info/attributes (NEVER the tracked .gitattributes — this
    must not be committed), re-merge, then ALWAYS remove the driver again:
        git merge --abort
        cp .git/info/attributes /tmp/sdlc-attrs.bak 2>/dev/null || rm -f /tmp/sdlc-attrs.bak
        # register a temporary union driver for EXACTLY the conflicted additive files:
        for each conflicted additive file F:  printf '%s merge=union\\n' "F" >> .git/info/attributes
        git merge --no-ff --no-edit ${p.branchName}
        git diff --name-only --diff-filter=U   (recheck — usually empty now)
        # restore the attributes file so the temp driver can't affect later waves:
        if [ -f /tmp/sdlc-attrs.bak ]; then cp /tmp/sdlc-attrs.bak .git/info/attributes; else rm -f .git/info/attributes; fi
    If no conflicts remain -> stage all, commit the merge if not already committed -> strategy="union",
    merged=true. Go to STEP 4.
    If conflicts STILL remain on an aggregator __init__.py (its single all-different hunk can leave a
    union artifact — a duplicated module docstring and a second __all__ that shadows the first), you MAY
    hand-resolve that ONE file: keep every "from ... import ..." line and merge all symbols into a single
    __all__ list (dedup, sorted), one docstring. Then "cd app && uv run python -c 'import <pkg>'" to
    confirm it imports; if it does -> strategy="union", merged=true. Otherwise:
        git merge --abort -> strategy="aborted", merged=false, escalated=true. Go to STEP 5.
  - If ANY conflicted file is NOT additive (a real code conflict):
        git merge --abort
        strategy="aborted", merged=false, escalated=true, conflictedFiles=<the non-additive ones>. Go to STEP 5.

STEP 4 — On success, capture the commit and clean up the worktree:
  git log --oneline -1   (commitHash = the short hash)
  git worktree remove "${p.worktreePath}" --force 2>/dev/null || true
  git branch -D ${p.branchName} 2>/dev/null || true
  git worktree prune
  (Do NOT touch planning/STATUS.md or DEVLOG.md — those are applied once in Report.)

STEP 4a — Post-merge integrity audits (run after cleanup, before returning):
  1. Docs fence audit: if docs/api-reference.md exists, verify balanced code fences:
       python3 -c "import re,sys; t=open('docs/api-reference.md').read(); fences=len(re.findall(r'^\`\`\`',t,re.M)); sys.exit(0 if fences%2==0 else 1)" 2>/dev/null \
         && echo "FENCE_OK" \
         || echo "FENCE_MISMATCH: docs/api-reference.md has unbalanced code fences after merging task ${p.taskNum} — TOC or section corruption suspected"
     Include any FENCE_MISMATCH message verbatim in the notes field.
  2. DEVLOG fix-pass audit: compare fix-pass claims in the task log against git history:
       FIX_DEVLOG=$(grep -ic "fix pass" ${reportsDir}/task${p.taskNum}-log.md 2>/dev/null || echo 0)
       FIX_COMMITS=$(git log --oneline --grep="fix:.*${blockId}-task${p.taskNum}" | wc -l | tr -d ' ')
       [ "$FIX_DEVLOG" -gt "$FIX_COMMITS" ] && echo "DEVLOG_MISMATCH: task${p.taskNum} claims $FIX_DEVLOG fix passes but git shows $FIX_COMMITS fix commits" || true
     Include any DEVLOG_MISMATCH message verbatim in the notes field.

STEP 5 — On escalation, PRESERVE the worktree and branch (the user will inspect them). Do not remove them.

Return using StructuredOutput: taskNum=${p.taskNum}, branchName="${p.branchName}", merged, strategy,
conflictedFiles, escalated, commitHash, notes.
`, { label: `merge-${p.taskNum}`, schema: MERGE_SCHEMA, phase: `Merge ${wi + 1}`, model: 'sonnet' })

      if (!m || !m.merged) {
        const note = m?.notes || 'merge agent returned null'
        log(`Task ${p.taskNum}: MERGE ESCALATED — ${note}. Branch preserved.`)
        badSet.add(p.taskNum)
        // reflect the merge failure in the outcome
        const o = outcomes.find(x => x.taskNum === p.taskNum)
        if (o) { o.status = 'escalate'; o.reasons = [...(o.reasons || []), `merge conflict: ${(m?.conflictedFiles || []).join(', ') || note}`] }
      } else {
        log(`Task ${p.taskNum}: merged (${m.strategy}) ${m.commitHash || ''}`)
        const o = outcomes.find(x => x.taskNum === p.taskNum)
        if (o) { o.merged = true; o.commitHash = m.commitHash; o.mergeStrategy = m.strategy; o.mergeNotes = m.notes }
        if (m.notes && m.notes.includes('DEVLOG_MISMATCH')) {
          log(`Task ${p.taskNum}: WARNING — DEVLOG_MISMATCH: ${m.notes}. Surfaced in block-workflow.md Observations.`)
        }
        if (m.notes && m.notes.includes('FENCE_MISMATCH')) {
          log(`Task ${p.taskNum}: WARNING — FENCE_MISMATCH: docs/api-reference.md has unbalanced code fences after this merge. Manual repair required before next wave.`)
        }
      }
    }
  }

  if (budget.total) log(`Budget: ~${Math.round(budget.remaining() / 1000)}k tokens remaining.`)
}

// ================================================================
// REPORT — block report + single STATUS/DEVLOG update + escalations
// ================================================================
phase('Report')

const merged    = outcomes.filter(o => o.merged)
const escalated = outcomes.filter(o => o.status === 'escalate')
const skipped   = outcomes.filter(o => o.status === 'skipped')
const overall = escalated.length === 0 && skipped.length === 0 ? 'PASS'
              : merged.length > 0 ? 'PARTIAL' : 'BLOCKED'

const outcomeTable = outcomes
  .sort((a, b) => a.taskNum - b.taskNum)
  .map(o => `| ${o.taskNum} | ${o.merged ? 'merged' : o.status} | ${o.finalVerdict || '—'} | ${o.mergeStrategy || '—'} | ${o.commitHash || '—'} | ${(o.reasons || []).join('; ').substring(0, 80) || '—'} |`)
  .join('\n')

const escalationBlock = escalated.length
  ? escalated.map(o => `- **Task ${o.taskNum}** — verdict ${o.finalVerdict}. ${o.triage || ''}\n    - Review: \`${o.reviewReport || `${reportsDir}/task${o.taskNum}-review.md`}\`\n    - Worktree (preserved): \`${o.worktreePath || 'n/a'}\` (branch \`${o.branchName || 'n/a'}\`)\n    - Reasons: ${(o.reasons || []).join('; ') || 'see review report'}`).join('\n')
  : '_None._'

const mergedTaskNums = merged.map(o => o.taskNum)

const reportResult = await agent(`
You are the finalize/report agent for the block orchestration. You run from the MAIN repo root.

Block: ${blockId}
Overall verdict: ${overall}
Merged tasks (applied to main): ${JSON.stringify(mergedTaskNums)}
Escalated tasks (NOT merged): ${JSON.stringify(escalated.map(o => o.taskNum))}
Skipped (blocked by upstream): ${JSON.stringify(skipped.map(o => o.taskNum))}

DO THIS, IN ORDER:

0. Scan all task workflow reports for NEEDS_REVIEW flags (before writing the block report):
   ls ${reportsDir}/task*-workflow.md 2>/dev/null || echo "NONE"
   For each file found, grep for lines containing "NEEDS_REVIEW":
     grep -n "NEEDS_REVIEW" ${reportsDir}/task*-workflow.md 2>/dev/null || echo "NONE"
   Extract the file path and reason from each match. Parse the task number from the filename
   (task<N>-workflow.md). Deduplicate by file path: for the same file flagged by multiple tasks,
   combine all task numbers into flaggedByTasks[] and all distinct reasons into reasons[].
   Store the result as needsReviewItems in the StructuredOutput. If none found, return [].

1. Write the block report to ${blockReport}:

   # Block Orchestration Report — ${blockId}

   **Date:** [run: date +%Y-%m-%d]
   **Overall verdict:** ${overall}
   **Tasks merged:** ${mergedTaskNums.length}  |  **Escalated:** ${escalated.length}  |  **Skipped:** ${skipped.length}

   ## Outcome by Task
   | Task | Result | Verdict | Merge | Commit | Notes |
   |---|---|---|---|---|---|
${outcomeTable}

   ## Escalations (need your attention)
${escalationBlock}

   ## Outstanding NEEDS_REVIEW Items
   [From step 0: if needsReviewItems is non-empty, write a table:
    | File | Flagged By | Reason |
    |---|---|---|
    | <file> | tasks <N, M, ...> | <combined reasons> |
    If needsReviewItems is empty, write: None.]

   ## Observations
   [Any DEVLOG_MISMATCH or FENCE_MISMATCH warnings surfaced during merge audits.]

   ## Resume
   After fixing any blocker (or editing ${planFile}), re-run:  /sdlc-block ${blockId}
   Completed tasks are detected on main and skipped; escalated tasks are retried.

2. Apply DEVLOG + STATUS ONCE (the per-task logs deferred these). The merged branches each carry a
   planning/tasks/${blockId}/reports/task<N>-log.md committed on main with "Applied: false".
   For EACH merged task N in ${JSON.stringify(mergedTaskNums)} (ascending):
     - cat ${reportsDir}/task${'${N}'}-log.md
     - Prepend its "## DEVLOG Entry" content directly below the YAML frontmatter and main header block of DEVLOG.md (most-recent-first, keeping the frontmatter at the top), once.
     - Flip that log's "Applied: false" -> "Applied: true".
   Then update planning/STATUS.md ONCE:
     - If ALL tasks in the block are now merged: mark the block "Done" in the progress table and set
       "Current focus:" to the NEXT block; otherwise mark it "In progress" and set Current focus to the
       lowest not-yet-merged task.
     - Bump the "Last updated:" line (today's date + one-line summary).
   Do NOT apply STATUS/DEVLOG for escalated or skipped tasks.

3. Commit:
   git add ${blockReport} DEVLOG.md planning/STATUS.md ${reportsDir}/task*-log.md
   git commit -m "chore: block orchestration report + status for ${blockId}"
   git log --oneline -1

Return using StructuredOutput: reportFile="${blockReport}", overallVerdict="${overall}",
statusUpdated (true if STATUS.md was updated), nextFocus (the Current focus string you wrote), notes.
`, { label: 'report', schema: REPORT_SCHEMA, phase: 'Report', model: 'sonnet' })

// ----------------------------------------------------------------
// Final console summary
// ----------------------------------------------------------------
log('=== BLOCK ORCHESTRATION COMPLETE ===')
log(`Overall: ${overall} | merged: ${merged.map(o => o.taskNum).join(', ') || 'none'} | escalated: ${escalated.map(o => o.taskNum).join(', ') || 'none'} | skipped: ${skipped.map(o => o.taskNum).join(', ') || 'none'}`)
if (escalated.length) {
  log('Escalations need your analysis:')
  for (const o of escalated) {
    log(`  Task ${o.taskNum}: ${o.triage || (o.reasons || []).join('; ')} | worktree: ${o.worktreePath || 'n/a'} | review: ${o.reviewReport || `${reportsDir}/task${o.taskNum}-review.md`}`)
  }
  log(`After fixing, resume with: /sdlc-block ${blockId}`)
}
log(`Block report: ${reportResult?.reportFile || blockReport}`)

return {
  blockId,
  overallVerdict: overall,
  waves: waves.length,
  merged: merged.map(o => ({ taskNum: o.taskNum, commitHash: o.commitHash, mergeStrategy: o.mergeStrategy })),
  escalated: escalated.map(o => ({ taskNum: o.taskNum, finalVerdict: o.finalVerdict, worktreePath: o.worktreePath, branchName: o.branchName, reviewReport: o.reviewReport, reasons: o.reasons, triage: o.triage })),
  skipped: skipped.map(o => o.taskNum),
  blockReport: reportResult?.reportFile || blockReport,
  resumeCommand: `/sdlc-block ${blockId}`,
  outcomes
}
