"""TestTaskNode — runs the ``planning/harness.json`` validation suite.

Deterministic node (no LLM). Reads ``worktree_path`` from
``SetupWorktreeNode``'s output, loads the worktree's ``planning/harness.json``
(if present), and dispatches each check by ``kind``:

- ``command`` (or no ``kind``): run the shell command, pass on exit code 0.
- ``forbidden-pattern-scan``: grep for each rule's pattern, fail on any
  unexcluded match.
- ``baseline-diff``: diff the command's JSON output against a baseline,
  fail on net-new entries.
- ``count-delta``: regex-extract a count from stdout, fail if it moved in the
  configured ``failOn`` direction relative to the baseline.
- ``warning-scan``: scan stdout/stderr for warning patterns; only fails the
  overall result if the check also ``gates``.

Output: ``result = TestTaskResult(...).model_dump()``.
"""

import json
import logging
import re
import subprocess
from pathlib import Path

from core.nodes.base import Node
from core.task import TaskContext
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CheckResult(BaseModel):
    """Outcome of a single harness check."""

    name: str
    kind: str
    passed: bool
    output: str = ""
    message: str = ""


class TestTaskResult(BaseModel):
    """Aggregate outcome of running the full harness suite."""

    all_passed: bool
    check_results: list[CheckResult]
    failure_summary: str = ""


def _run_command(command: str, cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_command_check(check: dict, worktree_path: str) -> CheckResult:
    name = check["name"]
    kind = check.get("kind") or "command"
    result = _run_command(check["command"], worktree_path)
    passed = result.returncode == 0
    output = result.stdout + result.stderr
    message = "" if passed else f"exit code {result.returncode}"
    return CheckResult(name=name, kind=kind, passed=passed, output=output, message=message)


def _run_forbidden_pattern_scan(check: dict, worktree_path: str) -> CheckResult:
    name = check["name"]
    violations: list[str] = []
    output_parts: list[str] = []
    for rule in check.get("rules", []):
        grep_command = f"grep -rnE '{rule['pattern']}' {rule['paths']}"
        result = _run_command(grep_command, worktree_path)
        matches = [line for line in result.stdout.splitlines() if line.strip()]
        allowlist_pattern = rule.get("allowlistPattern")
        if allowlist_pattern:
            allowlist_re = re.compile(allowlist_pattern)
            matches = [line for line in matches if not allowlist_re.search(line)]
        if matches:
            violations.extend(matches)
        output_parts.append(result.stdout)

    passed = not violations
    message = "" if passed else f"{len(violations)} forbidden-pattern match(es)"
    return CheckResult(
        name=name,
        kind="forbidden-pattern-scan",
        passed=passed,
        output="\n".join(output_parts),
        message=message,
    )


def _run_baseline_diff(check: dict, worktree_path: str) -> CheckResult:
    name = check["name"]
    compare_keys = check.get("compareKeys", [])

    baseline_result = _run_command(check["baselineCommand"], worktree_path)
    current_result = _run_command(check["command"], worktree_path)

    try:
        baseline_entries = json.loads(baseline_result.stdout or "[]")
    except json.JSONDecodeError:
        baseline_entries = []
    try:
        current_entries = json.loads(current_result.stdout or "[]")
    except json.JSONDecodeError:
        current_entries = []

    def _key(entry: dict) -> tuple:
        return tuple(entry.get(k) for k in compare_keys)

    baseline_keys = {_key(entry) for entry in baseline_entries}
    new_entries = [entry for entry in current_entries if _key(entry) not in baseline_keys]

    passed = not new_entries
    message = "" if passed else f"{len(new_entries)} net-new violation(s)"
    return CheckResult(
        name=name,
        kind="baseline-diff",
        passed=passed,
        output=current_result.stdout,
        message=message,
    )


def _run_count_delta(check: dict, worktree_path: str) -> CheckResult:
    name = check["name"]
    baseline_count = check.get("baseline", 0)
    result = _run_command(check["command"], worktree_path)
    match = re.search(check["countPattern"], result.stdout)
    current_count = int(match.group(0).split()[0]) if match else 0

    fail_on = check.get("failOn", "decrease")
    if fail_on == "decrease":
        passed = current_count >= baseline_count
    else:
        passed = current_count <= baseline_count

    message = "" if passed else f"count {current_count} vs baseline {baseline_count} ({fail_on})"
    return CheckResult(
        name=name,
        kind="count-delta",
        passed=passed,
        output=result.stdout,
        message=message,
    )


def _run_warning_scan(check: dict, worktree_path: str) -> CheckResult:
    name = check["name"]
    result = _run_command(check["command"], worktree_path)
    combined = result.stdout + result.stderr
    warning_patterns = check.get("warningPatterns", [])
    found = [pattern for pattern in warning_patterns if re.search(pattern, combined)]

    gates = check.get("gates", False)
    passed = not (gates and found)
    message = "" if not found else f"warning pattern(s) matched: {found}"
    return CheckResult(
        name=name,
        kind="warning-scan",
        passed=passed,
        output=combined,
        message=message,
    )


_DISPATCH = {
    "command": _run_command_check,
    "forbidden-pattern-scan": _run_forbidden_pattern_scan,
    "baseline-diff": _run_baseline_diff,
    "count-delta": _run_count_delta,
    "warning-scan": _run_warning_scan,
}


def _run_checks(checks: list[dict], worktree_path: str) -> tuple[list[CheckResult], list[str]]:
    """Run every enabled check and return (results, names of gating failures)."""
    check_results: list[CheckResult] = []
    failed_names: list[str] = []

    for check in checks:
        if check.get("enabled") is False:
            continue

        handler = _DISPATCH.get(check.get("kind") or "command", _run_command_check)
        check_result = handler(check, worktree_path)
        check_results.append(check_result)

        if check.get("gates", True) and not check_result.passed:
            failed_names.append(check_result.name)

    return check_results, failed_names


class TestTaskNode(Node):
    """Run the harness.json validation suite against the worktree."""

    def process(self, task_context: TaskContext) -> TaskContext:
        worktree_path = task_context.get_node_output("SetupWorktreeNode")["result"][
            "worktree_path"
        ]
        harness_path = Path(worktree_path) / "planning" / "harness.json"

        if not harness_path.exists():
            logger.info("No harness.json found at %s; nothing to validate", harness_path)
            result = TestTaskResult(all_passed=True, check_results=[])
            task_context.update_node(node_name=self.node_name, result=result.model_dump())
            return task_context

        harness = json.loads(harness_path.read_text(encoding="utf-8"))
        checks = harness.get("validation", {}).get("checks", [])

        check_results, failed_names = _run_checks(checks, worktree_path)
        all_passed = not failed_names
        failure_summary = "" if all_passed else f"Failed checks: {', '.join(failed_names)}"

        result = TestTaskResult(
            all_passed=all_passed,
            check_results=check_results,
            failure_summary=failure_summary,
        )
        task_context.update_node(node_name=self.node_name, result=result.model_dump())
        return task_context
