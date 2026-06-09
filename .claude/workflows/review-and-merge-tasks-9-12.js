
export const meta = {
  name: 'review-and-merge-tasks-9-12',
  description: 'Review completed sdlc-task worktrees for phase0-blockC tasks 9-12, then merge them in order',
  phases: [
    { title: 'Review', detail: 'Parallel review-workflow for tasks 9, 10, 11, 12' },
    { title: 'Merge', detail: 'Sequential clean-worktree in task-number order (9→10→11→12)' },
  ]
}

const TASKS = [9, 10, 11, 12]
const BLOCK = 'phase0-blockC'

// ================================================================
// PHASE 1: PARALLEL REVIEWS
// ================================================================
phase('Review')
log('Running review-workflow for tasks 9, 10, 11, 12 in parallel...')

const REVIEW_SCHEMA = {
  type: 'object',
  required: ['taskNumber', 'verdict', 'summary'],
  properties: {
    taskNumber: { type: 'integer' },
    verdict: { type: 'string', description: 'PASS, FAIL, PARTIAL, or BLOCKED' },
    summary: { type: 'string', description: 'One-paragraph summary of the review findings' },
    issues: { type: 'array', items: { type: 'string' }, description: 'Any issues or blockers found' },
    readyToMerge: { type: 'boolean', description: 'true if the task is ready to clean-worktree' }
  }
}

const reviewResults = await parallel(TASKS.map(taskNum => () =>
  agent(`
You are reviewing the completed SDLC pipeline for ${BLOCK} task ${taskNum}.

Your job is to invoke the /review-workflow skill for this task, then summarize the findings.

Run the skill:
  Invoke the Skill tool with:
    skill: "review-workflow"
    args: "${BLOCK}-task${taskNum}"

Wait for it to complete, then read the workflow report to understand what happened.

The workflow report should be at:
  planning/tasks/${BLOCK}/reports/task${taskNum}-workflow.md

If the skill is not available, fall back to reading the workflow report directly:
  Read: planning/tasks/${BLOCK}/reports/task${taskNum}-workflow.md
  Read: planning/tasks/${BLOCK}/reports/task${taskNum}-review.md

Based on your findings, return a structured summary using StructuredOutput:
  taskNumber: ${taskNum}
  verdict: the final verdict from the review report (PASS/FAIL/PARTIAL) or BLOCKED if files missing
  summary: one paragraph describing what was implemented, test results, and review outcome
  issues: list of any issues, failures, or concerns
  readyToMerge: true if verdict is PASS and pipeline completed normally
`, { label: `review-task-${taskNum}`, schema: REVIEW_SCHEMA, phase: 'Review' })
))

// Log review outcomes
const validReviews = reviewResults.filter(Boolean)
for (const r of validReviews) {
  log(`Task ${r.taskNumber}: ${r.verdict} — ready=${r.readyToMerge} — ${r.summary.substring(0, 80)}...`)
}

const failedReviews = validReviews.filter(r => !r.readyToMerge)
if (failedReviews.length > 0) {
  log(`WARNING: ${failedReviews.length} task(s) not ready to merge: ${failedReviews.map(r => r.taskNumber).join(', ')}`)
  log('Proceeding with merge for all tasks — /clean-worktree will surface any blocking issues.')
}

// ================================================================
// PHASE 2: SEQUENTIAL MERGES (task-number order is mandatory)
// ================================================================
phase('Merge')
log('Merging worktrees in order: 9 → 10 → 11 → 12 (order matters for STATUS.md correctness)')

const MERGE_SCHEMA = {
  type: 'object',
  required: ['taskNumber', 'branchName', 'success'],
  properties: {
    taskNumber: { type: 'integer' },
    branchName: { type: 'string' },
    success: { type: 'boolean' },
    summary: { type: 'string' },
    issues: { type: 'array', items: { type: 'string' } }
  }
}

const mergeResults = []

for (const taskNum of TASKS) {
  const branchName = `${BLOCK}-task${taskNum}`.toLowerCase().replace(/[^a-z0-9-]/g, '-')
  log(`Merging task ${taskNum} (branch: ${branchName})...`)

  const mergeResult = await agent(`
You are merging the completed worktree for ${BLOCK} task ${taskNum} into main.

Branch name: ${branchName}

Your job is to invoke the /clean-worktree skill for this branch, then confirm the merge succeeded.

Run the skill:
  Invoke the Skill tool with:
    skill: "clean-worktree"
    args: "${branchName}"

Wait for it to complete. The skill will:
1. Merge the branch into main
2. Apply the task log (STATUS.md + DEVLOG.md updates)
3. Commit those changes
4. Remove the worktree
5. Delete the branch

After the skill completes, verify the merge by running:
  git log --oneline -5
  git branch -a | grep ${branchName} || echo "BRANCH_DELETED"
  git worktree list | grep ${branchName} || echo "WORKTREE_REMOVED"

Return a structured summary using StructuredOutput:
  taskNumber: ${taskNum}
  branchName: "${branchName}"
  success: true if the merge completed and branch/worktree were removed
  summary: one sentence describing what happened
  issues: list of any errors or unexpected behavior
`, { label: `merge-task-${taskNum}`, schema: MERGE_SCHEMA, phase: 'Merge' })

  if (mergeResult) {
    mergeResults.push(mergeResult)
    log(`Task ${taskNum} merge: ${mergeResult.success ? 'OK' : 'FAILED'} — ${mergeResult.summary}`)
  } else {
    mergeResults.push({ taskNumber: taskNum, branchName, success: false, summary: 'Agent returned null' })
    log(`Task ${taskNum} merge: agent returned null — manual intervention may be needed`)
  }
}

// ================================================================
// FINAL SUMMARY
// ================================================================
const reviewSummary = validReviews.map(r => `  Task ${r.taskNumber}: ${r.verdict}`).join('\n')
const mergeSummary = mergeResults.map(r => `  Task ${r.taskNumber}: ${r.success ? 'merged' : 'FAILED'}`).join('\n')

log('=== FINAL SUMMARY ===')
log('Reviews:\n' + reviewSummary)
log('Merges:\n' + mergeSummary)

return {
  block: BLOCK,
  tasks: TASKS,
  reviews: validReviews,
  merges: mergeResults,
  allReviewsPassed: validReviews.every(r => r.readyToMerge),
  allMergesSucceeded: mergeResults.every(r => r.success)
}
