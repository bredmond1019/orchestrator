# Clean Worktree — Merge a completed SDLC worktree branch into main and remove it.

## Variables

$ARGUMENTS — block ID with optional task number. Same format as `/init-worktree`.

Examples:
- `phase0-blockC`   → worktree name: `phase0-blockc`
- `phase0-blockC 3` → worktree name: `phase0-blockc-task3`

## Instructions

1. If `$ARGUMENTS` is not provided, stop and print usage:
   ```
   Usage: /clean-worktree <block-id> [task-N]
   Examples:
     /clean-worktree phase0-blockC
     /clean-worktree phase0-blockC 3
   ```

2. **Parse arguments** using the same transform as `/init-worktree`: lowercase `blockId`, append `-task<taskNum>` if a task number is given. Derive `worktreeName` and `worktreePath = trees/<worktreeName>`.

3. **Check if the worktree exists:**
   ```bash
   git worktree list | grep <worktreePath>
   ```
   If not found, skip to step 8 (branch-only cleanup).

4. **SAFETY — Show uncommitted changes in the worktree:**
   ```bash
   git -C <worktreePath> status --short
   git -C <worktreePath> diff --stat
   ```
   If there are uncommitted changes, print:
   ```
   WARNING: The worktree has uncommitted changes (shown above).
   These will be permanently lost if the worktree is removed.
   Proceed anyway? (yes/no)
   ```
   Stop and wait for user confirmation. If the user says anything other than "yes", abort.

5. **SAFETY — Show unpushed commits on the worktree branch:**
   ```bash
   git -C <worktreePath> log --oneline main..HEAD
   ```
   Display this list clearly. These are the commits that will be merged into `main`.

6. **Merge the branch into main (fast-forward only):**

   Run from the main working tree (not from within the worktree):
   ```bash
   git merge --ff-only <worktreeName>
   ```

   **If fast-forward succeeds:** continue to step 7.

   **If fast-forward fails** (main has advanced since the worktree was created):
   - Print the divergence: `git log --oneline <worktreeName>..main` to show which commits on main are not in the worktree branch.
   - Stop. Do NOT delete the worktree or branch.
   - Print resolution options:
     ```
     Fast-forward merge failed. The worktree branch is behind main.
     The worktree at <worktreePath> has been left intact.

     To resolve, choose one of:
       Option A — Create a merge commit:
         git merge <worktreeName>

       Option B — Rebase the worktree branch onto main (from inside the worktree):
         cd <worktreePath>
         git rebase main
         cd <back to repo root>
         /clean-worktree <original-args>   ← retry after rebasing
     ```

7. **Remove the worktree and delete the branch:**
   ```bash
   git worktree remove <worktreePath> --force
   git worktree prune
   git branch -D <worktreeName>
   ```

8. **Branch-only cleanup** (worktree directory not found, but branch may still exist):
   ```bash
   git branch --list <worktreeName>
   ```
   If the branch exists:
   - Show any commits not yet on main: `git log --oneline main..<worktreeName>`
   - Delete the branch: `git branch -D <worktreeName>`
   If neither worktree nor branch exists, report: "Nothing to clean — '<worktreeName>' does not exist."

9. **Verify cleanup — run these and display output:**
   ```bash
   git worktree list
   git branch --list <worktreeName>
   git log --oneline -6
   ```

10. **Report one of:**
    - **Success:** "Worktree '<worktreeName>' merged and cleaned. Branch deleted. Pipeline commits are now on main."
    - **Merge failed:** "Fast-forward failed. Worktree left intact at <worktreePath>. See options above."
    - **Branch-only cleanup:** "Worktree directory not found. Branch '<worktreeName>' deleted (if it existed)."
    - **Already clean:** "Nothing to clean — '<worktreeName>' does not exist."

## Notes

- **Merge before delete.** This command never deletes the worktree or branch until the merge succeeds. Work is preserved until confirmed safe.
- **Fast-forward only** is the correct default for this pipeline: worktrees branch from `main` at init time, run the full pipeline, and then merge back. If `main` has advanced concurrently (e.g., a hotfix), `--ff-only` fails with a clear error rather than silently creating a merge commit.
- **Uncommitted changes** in the worktree are unusual — the SDLC pipeline commits after each stage. If they appear, it likely means the pipeline was interrupted mid-stage.
- Run this command from the **main repo session** (CWD: repo root), not from inside the worktree.
