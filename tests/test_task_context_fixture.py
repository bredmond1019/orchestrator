"""Conformance test for tests/fixtures/task_context/research_agent_task_context.json.

Re-runs scripts/emit_task_context_fixture.py's emission path and asserts the
result matches the checked-in fixture byte-for-byte. This is the Python-side
half of planning/task-context-fixture/notes.md step 5: it makes the fixture a
real two-way contract artifact — this repo notices if *it* drifts from the
fixture engine-rs's round_trip.rs also asserts against, instead of only the
Rust side being able to detect drift.
"""

import json
import sys
from pathlib import Path

# Ensure scripts/ and app/ are importable, mirroring tests/test_refresh_brain.py
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
APP_DIR = Path(__file__).resolve().parent.parent / "app"
for path in (SCRIPTS_DIR, APP_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from emit_task_context_fixture import (  # noqa: E402
    _FIXTURE_PATH,
    emit,
)


def test_emitted_task_context_matches_checked_in_fixture():
    """A freshly emitted task_context must match the checked-in fixture.

    The emission path is deterministic (fixed event literals, mocked
    Anthropic responses); only started_at/completed_at are non-deterministic
    and are redacted the same way scripts/emit_task_context_fixture.py's
    main() redacts them before comparing.
    """
    captured = emit()
    for run in captured.get("node_runs", {}).values():
        if run.get("started_at") is not None:
            run["started_at"] = "2026-07-16T00:00:00Z"
        if run.get("completed_at") is not None:
            run["completed_at"] = "2026-07-16T00:00:00Z"

    expected = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    assert captured == expected, (
        "Live TaskContext no longer matches the checked-in fixture at "
        f"{_FIXTURE_PATH} — this repo's task_context shape has drifted. "
        "Re-run `uv run python scripts/emit_task_context_fixture.py` to "
        "regenerate it, review the diff, and update engine-rs's copy too."
    )


def test_fixture_has_documented_shape():
    """The fixture itself carries the four data-contract §5 top-level keys."""
    fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    assert set(fixture.keys()) == {"event", "nodes", "metadata", "node_runs"}

    node_run = fixture["node_runs"]["CompanyResearchNode"]
    assert set(node_run.keys()) == {
        "status",
        "started_at",
        "completed_at",
        "error",
        "input",
        "usage",
    }
    assert set(node_run["usage"].keys()) == {"input_tokens", "output_tokens", "model"}
