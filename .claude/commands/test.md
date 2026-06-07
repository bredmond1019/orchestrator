# Application Validation Test Suite

Execute comprehensive validation tests for the orchestration framework, returning results in a standardized JSON format for automated processing.

## Variables

$ARGUMENTS — optional path to the task spec and optional task number. Same format as `/implement`.

Examples:
- (no args) — run full suite; output JSON to chat only; no file written
- `planning/tasks/phase0-blockC.md` — run full suite; write report to `planning/tasks/reports/phase0-blockC-test.md`
- `planning/tasks/phase0-blockC.md 1` — run full suite; write report to `planning/tasks/reports/phase0-blockC-task1-test.md`

The task number N does NOT change which tests run — all 8 tests always run regardless. N only
determines the output file name so the snapshot is scoped to the right pipeline stage.

## Purpose

Proactively identify and fix issues before they impact the pipeline or downstream workflows. By running this suite you can:
- Detect syntax errors, import failures, and module misconfiguration
- Identify broken tests or regressions in core engine behavior
- Verify that all key modules construct cleanly without side effects
- Ensure the framework is in a healthy state before beginning new work

## Constants

TEST_COMMAND_TIMEOUT: 5 minutes

## Instructions

- **Step 0 — Parse `$ARGUMENTS`:** If provided, split on the last space. Trailing number = task N; remainder = spec path. Derive the report file path:
  - No args: no file will be written.
  - Spec only: `planning/tasks/phase0-blockC.md` → `planning/tasks/reports/phase0-blockC-test.md`
  - Spec + task N: `planning/tasks/phase0-blockC.md 1` → `planning/tasks/reports/phase0-blockC-task1-test.md`
- Run `/prime` to orient to the codebase before executing any tests.
- Execute each test in the sequence provided below
- Capture the result (passed/failed) and any error messages
- IMPORTANT: Return ONLY the JSON array with test results
  - IMPORTANT: Do not include any additional text, explanations, or markdown formatting
  - We'll immediately run JSON.parse() on the output, so make sure it's valid JSON
- If a test passes, omit the error field
- If a test fails, include the error message in the error field
- Execute all tests even if some fail
- Error Handling:
  - If a command returns a non-zero exit code, mark as failed
  - Capture stderr output for the error field
  - Timeout commands after `TEST_COMMAND_TIMEOUT`
- Test execution order is important — import checks must pass before running the full suite
- All commands are run from the repo root unless the command itself changes directory
- Always run `pwd` before each test to confirm you are in the repo root

## Test Execution Sequence

### Import / Construction Checks

1. **App Import Check**
   - Preparation Command: None
   - Command: `cd app && uv run python -c "from main import app"`
   - test_name: "app_import"
   - test_purpose: "Verifies that the FastAPI app object constructs cleanly — catches broken route registrations, missing env vars read at import time, and any module-level errors in api/ or main.py"

2. **Worker Import Check**
   - Preparation Command: None
   - Command: `cd app && uv run python -c "from worker.config import celery_app"`
   - test_name: "worker_import"
   - test_purpose: "Verifies that the Celery app constructs cleanly — catches misconfigured broker URLs, import-time side effects, and missing env vars in worker/config.py"

3. **Database Session Import Check**
   - Preparation Command: None
   - Command: `cd app && uv run python -c "from database.session import Base, db_session"`
   - test_name: "database_session_import"
   - test_purpose: "Verifies that database.session imports without triggering a live DB connection — catches the known import-time create_engine() side effect and any SQLAlchemy misconfiguration"

4. **Repository Import Check**
   - Preparation Command: None
   - Command: `cd app && uv run python -c "from database.repository import GenericRepository"`
   - test_name: "repository_import"
   - test_purpose: "Verifies that GenericRepository imports cleanly — catches missing model references, SQLAlchemy 2.x incompatibilities, and import-time errors in database/repository.py"

### Code Quality

5. **Ruff**
   - Preparation Command: None
   - Command: `uv run ruff check app/`
   - test_name: "ruff"
   - test_purpose: "Fast Rust-based linter — checks pyflakes (unused imports, undefined names), pycodestyle, isort ordering, pyupgrade (modern syntax), and flake8-bugbear (likely bugs). Runs in milliseconds; catches the common class of issues before the slower pylint pass"

6. **Pylint**
   - Preparation Command: None
   - Command: `uv run pylint app/`
   - test_name: "pylint"
   - test_purpose: "Deep semantic analysis across the entire app/ directory — catches type-aware issues, attribute access errors, and design problems that ruff's AST-only pass cannot detect. Excludes app/core/commands/ and app/alembic/ per project rules"

### Test Suite

7. **Pytest Collection**
   - Preparation Command: None
   - Command: `uv run pytest --collect-only`
   - test_name: "pytest_collect"
   - test_purpose: "Verifies that pytest can discover and collect all tests without import errors — a collection failure means tests can't run at all, usually caused by a broken import in a test file or fixture"

8. **Full Test Suite**
   - Preparation Command: None
   - Command: `uv run pytest -v`
   - test_name: "pytest_full"
   - test_purpose: "Runs every test in the suite with verbose output — validates core engine behavior (Workflow, TaskContext, WorkflowValidator, nodes), database layer (GenericRepository CRUD), API endpoint (ghost-row regression), and services (PromptManager). customer_care workflow is excluded from tests per project standing rules"

## Report

- IMPORTANT: Return results exclusively as a JSON array based on the `Output Structure` section below.
- Sort the JSON array with failed tests (passed: false) at the top
- Include all tests in the output, both passed and failed
- The execution_command field should contain the exact command that can be run to reproduce the test
- This allows subsequent agents to quickly identify and resolve errors

### Output Structure

```json
[
  {
    "test_name": "string",
    "passed": boolean,
    "execution_command": "string",
    "test_purpose": "string",
    "error": "optional string"
  }
]
```

### Example Output

```json
[
  {
    "test_name": "ruff",
    "passed": false,
    "execution_command": "uv run ruff check app/",
    "test_purpose": "Fast Rust-based linter — checks pyflakes, pycodestyle, isort, pyupgrade, and flake8-bugbear",
    "error": "app/database/repository.py:3:1: F401 `sqlalchemy.orm` imported but unused"
  },
  {
    "test_name": "app_import",
    "passed": true,
    "execution_command": "cd app && uv run python -c \"from main import app\"",
    "test_purpose": "Verifies that the FastAPI app object constructs cleanly — catches broken route registrations, missing env vars read at import time, and any module-level errors in api/ or main.py"
  }
]
```

## File Output

If `$ARGUMENTS` was provided, after returning the JSON array to chat, write a report file to the
derived path. Create `planning/tasks/reports/` if it does not exist.

**Write the report file in this exact format:**

```markdown
# Test Report — <spec filename> [Task <N> | All Tasks]

**Date:** <YYYY-MM-DD>
**Plan:** <spec file path, or "ad-hoc">
**Scope:** Task <N> | All tasks
**Overall result:** PASS (<n>/8 passed) | FAIL (<n>/8 passed)

## Summary

| Test | Result | Error |
|---|---|---|
| app_import | PASS / FAIL | <error snippet or blank> |
| worker_import | PASS / FAIL | |
| database_session_import | PASS / FAIL | |
| repository_import | PASS / FAIL | |
| ruff | PASS / FAIL | |
| pylint | PASS / FAIL | |
| pytest_collect | PASS / FAIL | |
| pytest_full | PASS / FAIL | |

## Full Results (JSON)

\`\`\`json
<the full JSON array, verbatim>
\`\`\`

## Next Step

`/review-task <spec file path> [N]`
```

After writing the file, output one line to chat:
```
Next: /review-task <spec file path> [N]
```
