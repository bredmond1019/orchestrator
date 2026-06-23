# Implementation Report — phase0-blockC-task11

**Date:** 2026-06-08
**Plan:** planning/tasks/phase0-blockC/tasks.md
**Scope:** Task 11

## What Was Built or Changed

- Created `tests/services/test_prompt_loader.py` — 20 unit tests for `PromptManager` covering:
  - Basic rendering: single variable, multiple variables, no variables, multiline templates
  - YAML frontmatter: body-only returned, markers stripped, frontmatter keys absent from output
  - Error cases: missing template raises `TemplateNotFound`, missing variable raises `ValueError`, `StrictUndefined` confirmed (no silent empty string)
  - `get_template_info`: name matches argument, `description`/`author` parsed, raw frontmatter dict exposed, defaults when keys absent, variable list extraction, empty variables for static templates, missing template error

## Files Created or Modified

| File | Action |
|---|---|
| `tests/services/test_prompt_loader.py` | created |

## Validation Output

**Commands run:**
```
uv run pytest tests/services/test_prompt_loader.py -v
uv run pytest -v (full suite)
uv run ruff check tests/services/test_prompt_loader.py
```

**Results:**
```
============================= test session starts ==============================
collected 20 items

tests/services/test_prompt_loader.py::TestGetPromptRendering::test_renders_single_variable PASSED
tests/services/test_prompt_loader.py::TestGetPromptRendering::test_renders_multiple_variables PASSED
tests/services/test_prompt_loader.py::TestGetPromptRendering::test_renders_template_with_no_variables PASSED
tests/services/test_prompt_loader.py::TestGetPromptRendering::test_renders_multiline_template PASSED
tests/services/test_prompt_loader.py::TestGetPromptFrontmatter::test_body_only_is_returned_when_frontmatter_present PASSED
tests/services/test_prompt_loader.py::TestGetPromptFrontmatter::test_frontmatter_markers_are_not_in_output PASSED
tests/services/test_prompt_loader.py::TestGetPromptFrontmatter::test_frontmatter_keys_are_not_in_output PASSED
tests/services/test_prompt_loader.py::TestGetPromptErrors::test_missing_template_raises_template_not_found PASSED
tests/services/test_prompt_loader.py::TestGetPromptErrors::test_missing_required_variable_raises_value_error PASSED
tests/services/test_prompt_loader.py::TestGetPromptErrors::test_missing_variable_error_is_not_silent_empty_string PASSED
tests/services/test_prompt_loader.py::TestGetTemplateInfo::test_returns_name_matching_template_argument PASSED
tests/services/test_prompt_loader.py::TestGetTemplateInfo::test_parses_description_from_frontmatter PASSED
tests/services/test_prompt_loader.py::TestGetTemplateInfo::test_parses_author_from_frontmatter PASSED
tests/services/test_prompt_loader.py::TestGetTemplateInfo::test_returns_raw_frontmatter_dict PASSED
tests/services/test_prompt_loader.py::TestGetTemplateInfo::test_default_description_when_frontmatter_absent PASSED
tests/services/test_prompt_loader.py::TestGetTemplateInfo::test_default_author_when_frontmatter_absent PASSED
tests/services/test_prompt_loader.py::TestGetTemplateInfo::test_lists_single_variable PASSED
tests/services/test_prompt_loader.py::TestGetTemplateInfo::test_lists_all_variables PASSED
tests/services/test_prompt_loader.py::TestGetTemplateInfo::test_variables_empty_for_static_template PASSED
tests/services/test_prompt_loader.py::TestGetTemplateInfo::test_missing_template_raises_template_not_found PASSED

20 passed in 0.05s

Full suite: 107 passed in 2.40s

ruff check: All checks passed!
```

Status: PASSED

## Decisions and Trade-offs

- **Singleton isolation via `reset_prompt_manager_env` autouse fixture:** `PromptManager._env` is a class-level singleton. Each test that uses `prompt_dir` installs a custom `Jinja2 Environment` pointing at `tmp_path`. The autouse fixture saves and restores `_env` so tests never leak state into each other.

- **`jinja2.TemplateNotFound` not `FileNotFoundError`:** The docstring on `get_prompt` claims `FileNotFoundError` but the actual exception raised by `env.loader.get_source()` is `jinja2.TemplateNotFound` (inherits from `OSError` and `LookupError`). Tests use `TemplateNotFound` to match reality. The mismatch in the docstring is noted but not fixed here (out of scope for Task 11).

- **`ValueError` for missing variables, not `UndefinedError`:** The spec says "assert Jinja2 raises `UndefinedError`". The implementation catches `TemplateError` (parent of `UndefinedError`) and wraps it as `ValueError` with a message prefix. Tests assert `ValueError` to match the actual interface. The `StrictUndefined` behavior (no silent empty string) is verified separately.

- **No modifications to `prompt_loader.py`:** There is a CLAUDE.md violation in `prompt_loader.py` — `open()` calls on lines 75 and 104 lack `encoding="utf-8"`. This was not fixed as modifying `prompt_loader.py` is outside Task 11's scope.

## Follow-up Work

- Fix `open()` calls in `app/services/prompt_loader.py` (lines 75, 104) to pass `encoding="utf-8"` per CLAUDE.md rules.
- Fix `prompt_loader.py` docstring: change `FileNotFoundError` to `jinja2.TemplateNotFound` for accuracy.

## git diff --stat

```
(new untracked file — no diff against HEAD)
tests/services/test_prompt_loader.py  |  227 lines created
```
