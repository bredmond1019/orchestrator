# Init Worktree — Create an isolated git worktree for an SDLC block or task.

## Variables

$ARGUMENTS — block ID with optional task number.

Examples:
- `phase0-blockC`   → worktree name: `phase0-blockc`   at `trees/phase0-blockc/`
- `phase0-blockC 3` → worktree name: `phase0-blockc-task3` at `trees/phase0-blockc-task3/`

## Instructions

1. If `$ARGUMENTS` is not provided, stop and print usage:
   ```
   Usage: /init-worktree <block-id> [task-N]
   Examples:
     /init-worktree phase0-blockC
     /init-worktree phase0-blockC 3
   ```

2. **Parse arguments:** split `$ARGUMENTS` on whitespace. First token is `blockId`. If a second token exists and is a number, it is `taskNum`; otherwise no task number.

3. **Derive worktree name:** lowercase `blockId`, append `-task<taskNum>` if `taskNum` is set.
   - `phase0-blockC`    → `phase0-blockc`
   - `phase0-blockC 3`  → `phase0-blockc-task3`

4. **Verify CWD is repo root:**
   ```bash
   git rev-parse --show-toplevel
   ```
   If the output does not match the current directory, stop with: "Run this command from the repo root, not from inside a subdirectory."

5. **Check for name collision:**
   ```bash
   git worktree list
   git branch --list <worktreeName>
   ```
   - If `trees/<worktreeName>` appears in worktree list → stop: "Worktree '<worktreeName>' already exists. Run `/clean-worktree <args>` first."
   - If branch `<worktreeName>` exists but worktree directory does not → stop: "Branch '<worktreeName>' exists as an orphan. Delete it first with: `git branch -D <worktreeName>`"

6. **Create the trees directory:**
   ```bash
   mkdir -p trees
   ```

7. **Create the worktree without checkout:**
   ```bash
   git worktree add --no-checkout trees/<worktreeName> -b <worktreeName>
   ```

8. **Configure sparse checkout (cone mode):**
   ```bash
   git -C trees/<worktreeName> sparse-checkout init --cone
   git -C trees/<worktreeName> sparse-checkout set app tests docs planning .claude
   git -C trees/<worktreeName> checkout
   ```
   This checks out `app/`, `tests/`, `docs/`, `planning/`, and `.claude/`. Root-level files (`CLAUDE.md`, `pyproject.toml`, `pytest.ini`, `uv.lock`, etc.) are included automatically by cone mode.

9. **Copy `.env` if present:**
   ```bash
   if [ -f .env ]; then
     cp .env trees/<worktreeName>/.env
     echo "Copied .env"
   else
     echo ".env not found at repo root — skipping"
   fi
   ```

10. **Create initial empty commit to establish the branch head:**
    ```bash
    git -C trees/<worktreeName> commit --allow-empty -m "chore: init worktree <worktreeName>"
    ```

11. **Verify — run these and display the output:**
    ```bash
    git worktree list
    git -C trees/<worktreeName> sparse-checkout list
    ls trees/<worktreeName>/
    git -C trees/<worktreeName> log --oneline -1
    ```

12. **Report success** and print next-step instructions:
    ```
    Worktree '<worktreeName>' ready at trees/<worktreeName>/

    To run the SDLC pipeline in isolation:
      1. Open a new Claude Code session with working directory set to:
           <absolute-path-to-repo>/trees/<worktreeName>
      2. Run: /sdlc-run <blockId>[ <taskNum>]

    When the pipeline is done, return to the main repo session and run:
      /clean-worktree <original-args>
    ```

## Notes

- Sparse checkout includes `planning/` in full so the scout, plan, and wrap-up agents can read STATUS.md, MASTER_PLAN.md, and write report files.
- `.claude/` is included so all commands and workflows resolve correctly when the CWD is the worktree.
- Root-level files are included automatically by cone mode — no need to list them explicitly.
- `.env` is gitignored and must be copied manually (step 9).
- All `git commit` calls inside the pipeline will commit to branch `<worktreeName>`, not `main`, because git detects the worktree context automatically.
- When the pipeline finishes, run `/clean-worktree` from the main repo session to merge the branch and clean up.
