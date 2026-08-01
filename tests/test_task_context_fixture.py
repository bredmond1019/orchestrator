"""Shape-conformance test for tests/fixtures/task_context/research_agent_task_context.json.

This fixture is a **frozen golden file** as of `OR.X` cut 2 (D51 divestment):
``scripts/emit_task_context_fixture.py`` (the generator, which required the now-removed
``RESEARCH_AGENT`` workflow to run) was deleted, and the fixture itself must stay
byte-identical — ``bastion`` and ``engine-rs``'s ``round_trip.rs`` pin these exact bytes.
This file only asserts the checked-in fixture still parses and carries the documented
data-contract §5 shape; it no longer re-runs generation to diff against a live
``TaskContext``. See ``docs/data-contract.md`` §5 for the frozen-golden-file note.
"""

import json
from pathlib import Path

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "task_context"
    / "research_agent_task_context.json"
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
