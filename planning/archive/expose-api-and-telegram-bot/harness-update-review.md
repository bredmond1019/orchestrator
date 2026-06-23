---
type: HarnessReview
title: D23/D24 Harness Validation Review — expose-api-and-telegram-bot
description: Post-run analysis of the Plan F3 lean sdlc-block against the D23/D24 behavioral expectations, covering the restart incident, duplicate setup costs, and the emoji false gate.
---

# D23/D24 Harness Validation Review
**Spec:** expose-api-and-telegram-bot  
**Date:** 2026-06-23  
**Runs:** 2 (first PARTIAL, second PASS after manual recovery)  
**Overall implementation outcome:** PASS — all 5 tasks landed, 705 tests pass

---

## What This Run Was Supposed to Validate

The harness note specified five D23/D24 behavioral expectations:

| Expectation | Result |
|---|---|
| Shared setup (harness-config + baseline-snapshot) runs **once per block**, not per task | ⚠️ Ran once per *invocation* — ran twice total due to restart |
| Width-1 tasks run **in-place** (no worktree, no merge) | ✅ Tasks 4 and 5 ran in-place |
| Width-≥2 waves still use worktrees | ✅ Tasks 1, 2, 3 ran in parallel worktrees |
| One consolidated back-half fires at the end | ✅ One test → review → fix → document → wrap-up |
| Per-task review non-gating / off by default | ✅ No per-task review ran |

The in-place and back-half behaviors are confirmed working. The "once per block" property held within each invocation but was broken across invocations by the restart.

---

## What Went Wrong: Three Issues

### Issue 1 — Untracked Baseline File Blocked Worktree Merges (Root Cause of Restart)

**What happened:**  
The `baseline-snapshot` stage wrote `planning/expose-api-and-telegram-bot/sdlc/reports/net-new-lint-baseline.json` to the working tree but did not commit it. Later, when the merge step attempted to integrate the task-2 and task-3 worktree branches, it checked for a clean working tree first (standard git safety check). The untracked file triggered the blocker:

```
MERGE BLOCKED: main working tree has uncommitted changes.
Untracked file: planning/expose-api-and-telegram-bot/sdlc/reports/net-new-lint-baseline.json.
```

Tasks 2 and 3 escalated, task 4 and 5 were skipped. The block exited PARTIAL after run 1.

**Recovery:** Manual — committed the untracked file, re-ran `/sdlc-block`.

**Root cause:** The baseline-snapshot stage writes a file to the integration branch's working tree as a side effect of setup, but it is not committed. The merge step then has no way to proceed. The file needs to be either:
- Committed atomically as part of the setup phase (one commit: "chore: sdlc baseline"), or  
- Written outside the tracked working tree (e.g. a temp path or the `.claude/` session dir).

**Impact:** Required a full second invocation, losing all warm-path benefits.

---

### Issue 2 — No Cross-Invocation Resume: Duplicate Setup + Expensive Re-Analyze

**What happened:**  
`/sdlc-block` has no state persistence across invocations. When re-run, it started fresh: re-ran `harness-config` and `baseline-snapshot`, then re-ran `analyze` (on Opus) to figure out what was already done.

The second `analyze` was measurably more expensive than the first. It had to inspect git log, check for existing worktrees at `trees/expose-api-and-telegram-bot-task{2,3}`, and reconstruct task state — work the first run had already done and thrown away.

**Token waste (run 2 orchestrator-only, from block-workflow.md):**

| Stage | Model | OutTok | Notes |
|---|---|---|---|
| pre-flight | sonnet | 1,258 | Redundant with run 1 |
| harness-config | sonnet | 991 | Redundant — ran in run 1 |
| baseline-snapshot | haiku | 1,367 | Redundant — ran in run 1 |
| analyze | opus | 3,531 | Expensive re-derive; run 1 analyze also happened but its tokens aren't in the saved report |
| triage-2-1 + triage-3-1 | sonnet | 12,126 | Handling the already-implemented-but-stuck worktrees |
| teardown × 2 | haiku | 2,525 | Cleanup from escalations |

The triage stages (12k outTok combined) existed purely because the escalation from run 1 left tasks 2 and 3 in a "implemented but not merged" limbo — the second analyze had to route them through triage to attempt their merges again, rather than a direct merge path.

**Options for fixing:**
1. **Commit the baseline file in setup** (fixes Issue 1, which eliminates the restart that caused this).
2. **Persist block state** — write a `sdlc/state.json` (task status + worktree paths) that a resumed invocation reads before running analyze. Analyze then only needs to verify the snapshot rather than re-derive from git.
3. **Use `resumeFromRunId`** — the Workflow tool supports this but the sdlc-block script doesn't currently leverage it. A workflow-level resume would return cached agent results for all completed stages instantly.

---

### Issue 3 — Emoji False Gate in Test Agent

**What happened:**  
The test stage FAILED on a check called `emoji-prohibition` that does not exist in `planning/harness.json`. The test agent invented it as a "universal harness gate" and hard-failed on the `✅` character in:
- `integrations/telegram/README.md` — documenting the bot reply
- `planning/expose-api-and-telegram-bot/sdlc/reports/task2-implement.md` — referencing the spec requirement

The `✅` is a functional spec requirement (tasks.md line 41: `reply "Queued ✅"`). It is not in any config file the test agent should be reading.

**Resolution:** The review agent correctly identified this as a false gate and ruled PASS. But it consumed an extra review pass that could have been avoided.

**Fix:** Harden the test agent prompt to enumerate only the checks present in `harness.json` and reject any check without a matching config entry. The phrase "universal harness gate" in the agent's reasoning is a red flag that it is synthesizing rules rather than reading them.

---

## Wave Structure (What the Analyze Agent Derived)

With no `execution-plan.json` present (spec was generated before D22), Analyze derived the plan from the spec's dependency notes and file-ownership comments:

| Wave | Tasks | Width | Mode | Correctness |
|---|---|---|---|---|
| 1 | 1, 2, 3 | 3 | Worktrees | ✅ Tasks have disjoint file ownership; spec explicitly says "run in parallel (wave 1)" |
| 2 | 4 | 1 | In-place | ✅ Docs task, depends on 1–3 |
| 3 | 5 | 1 | In-place | ✅ Validate gate, depends on 4 |

The width-1 in-place behavior (D23) fired correctly for waves 2 and 3. The fallback derivation was clean — no `execution-plan.json` is needed for this simple linear-then-parallel shape.

---

## Token Summary Across Both Runs

| Run | Agents | SubagentTokens | Tool Uses | Duration | Outcome |
|---|---|---|---|---|---|
| Run 1 (PARTIAL) | 21 | 531,325 | 335 | 19m 8s | Tasks 1 merged; 2+3 escalated; 4+5 skipped |
| Run 2 (PASS) | 47 | 1,344,140 | 689 | 70m 4s | All 5 tasks + back-half |
| **Total** | **68** | **1,875,465** | **1,024** | **~89m** | |

Had the baseline file been committed during setup, run 1 would have merged all three worktrees and proceeded to tasks 4 and 5 in-place, then the back-half — all in a single invocation. The restart cost roughly 531k subagent tokens and ~19 minutes of wall time, almost entirely wasted.

---

## D23/D24 Behavioral Confirmation (Happy Path)

Ignoring the restart, the in-invocation behavior confirmed the D23/D24 design:

- ✅ `harness-config` ran once at the start of run 2 (not once per task)
- ✅ `baseline-snapshot` ran once at the start of run 2 (not once per task)
- ✅ Tasks 4 and 5 — width-1 — ran in-place with no worktree setup or merge step
- ✅ Tasks 1, 2, 3 — width-3 — ran in parallel worktrees and merged cleanly
- ✅ One consolidated back-half fired over the integrated tree
- ✅ Per-task review was off; the back-half's single review pass was authoritative
- ✅ Back-half review correctly overrode the emoji false gate without a second attempt

The lean sdlc-block design is sound. The three issues above are fixable bugs, not design flaws.

---

## Recommendations (Prioritized)

| Priority | Fix | Effort |
|---|---|---|
| P0 | **Commit the baseline file in setup.** Add a `git add + git commit` for the baseline JSON immediately after `baseline-snapshot` writes it. This eliminates the root cause of both the restart and the duplicate setup/analyze costs. | Low — one shell command added to the baseline-snapshot stage |
| P1 | **Harden the test-agent prompt.** Enumerate checks from `harness.json` explicitly; fail if a check name doesn't appear in the config. Add a rule: "Do not invent universal gates. If a check is not in harness.json, skip it." | Low — prompt edit |
| P2 | **Persist block state for resume.** Write a `sdlc/state.json` after each task lands (task status, worktree path, commit hash). A re-invoked block reads this before analyze, skipping the re-derive and going straight to merge-pending or execute-next. | Medium — new state file + read path in analyze |
| P3 | **Consider Workflow `resumeFromRunId`** for the inner sdlc-run calls in the back-half if they are ever interrupted. Not needed now but useful if back-half grows longer. | Low — pass runId through |
