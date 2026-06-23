# Test Report — phase1-projectB

**Date:** 2026-06-22
**Spec:** planning/phase1-projectB/tasks.md
**Scope:** Full spec

## Summary

| Test | Result | Error |
|---|---|---|
| standing-rules | PASSED | |
| app-import | PASSED | |
| worker-import | PASSED | |
| db-session-import | PASSED | |
| db-repository-import | PASSED | |
| net-new-lint | PASSED | |
| pylint | PASSED | |
| pytest-count | PASSED | |
| pytest | PASSED | |
| emoji-gate | PASSED | |

## Full Results (JSON)
```json
[
  {
    "test_name": "standing-rules",
    "passed": true,
    "execution_command": "grep -rn --include='*.py' app/ <pattern>",
    "test_purpose": "CLAUDE.md standing-rule scan (non-waivable) — rules, not pre-existing debt",
    "error": ""
  },
  {
    "test_name": "app-import",
    "passed": true,
    "execution_command": "cd app && uv run python -c 'import main'",
    "test_purpose": "App imports cleanly; surface Pydantic field-shadow warnings (advisory)",
    "error": ""
  },
  {
    "test_name": "worker-import",
    "passed": true,
    "execution_command": "cd app && uv run python -c 'import worker.config'",
    "test_purpose": "Worker config imports cleanly; surface Pydantic field-shadow warnings (advisory)",
    "error": ""
  },
  {
    "test_name": "db-session-import",
    "passed": true,
    "execution_command": "cd app && uv run python -c 'import database.session'",
    "test_purpose": "Database session imports",
    "error": ""
  },
  {
    "test_name": "db-repository-import",
    "passed": true,
    "execution_command": "cd app && uv run python -c 'import database.repository'",
    "test_purpose": "Repository imports",
    "error": ""
  },
  {
    "test_name": "net-new-lint",
    "passed": true,
    "execution_command": "uv run python -m ruff check app/ --output-format=json",
    "test_purpose": "Ruff — fail only on violations this task introduced (diff vs worktree-creation baseline)",
    "error": ""
  },
  {
    "test_name": "pylint",
    "passed": true,
    "execution_command": "uv run python -m pylint app/",
    "test_purpose": "Pylint",
    "error": ""
  },
  {
    "test_name": "pytest-count",
    "passed": true,
    "execution_command": "uv run python -m pytest --collect-only -q",
    "test_purpose": "Pytest collection count must not drop vs the previous task (catches silently-removed tests)",
    "error": ""
  },
  {
    "test_name": "pytest",
    "passed": true,
    "execution_command": "uv run python -m pytest",
    "test_purpose": "Full test suite — AUTHORITATIVE for verdict",
    "error": ""
  },
  {
    "test_name": "emoji-gate",
    "passed": true,
    "execution_command": "python3 -c 'check for emoji in modified .md/.mdx files'",
    "test_purpose": "Emoji prohibition (universal harness gate — always runs last)",
    "error": ""
  }
]
```
