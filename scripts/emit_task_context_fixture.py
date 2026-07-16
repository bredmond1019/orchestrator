"""emit_task_context_fixture.py — capture a real task_context for cross-repo conformance.

Runs the ``research_agent`` workflow end-to-end (Anthropic client + prompt
loading mocked, no DB/Celery involved) and dumps the resulting
``TaskContext.model_dump(mode="json")`` to
``tests/fixtures/task_context/research_agent_task_context.json``.

This is the "counterparty produces the fixture" half of
planning/task-context-fixture/notes.md: engine-rs's round_trip.rs consumes
this file instead of a fixture it hand-authored about itself, and
tests/test_task_context_fixture.py asserts this repo's own TaskContext
serialization matches it too.

The event dict and every mocked response are fixed literals (no uuid4()/
datetime.now() defaults), so re-running this script is a no-op diff unless
the workflow's actual output shape changes — that determinism is what makes
the fixture reviewable and safe to regenerate.

Usage:
    # From the repo root
    uv run python scripts/emit_task_context_fixture.py
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "tests"
    / "fixtures"
    / "task_context"
    / "research_agent_task_context.json"
)

_ANTHROPIC_PATCH = "core.nodes.tool_use.anthropic.Anthropic"
_PM_PATCH = (
    "workflows.research_agent_workflow_nodes.company_research_node.PromptManager.get_prompt"
)

_BRIEF_PAYLOAD = {
    "company_name": "Initech",
    "what_they_do": "Mid-market B2B SaaS for project management",
    "likely_time_sinks": [
        "Manual weekly status report compilation",
        "Client onboarding spreadsheet handoff",
        "Ad-hoc invoice reconciliation",
    ],
    "automation_hypothesis": (
        "Automating the weekly status report aggregation via API integration "
        "could recover 6+ hours per PM per week"
    ),
}


def _tool_use_response() -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.id = "toolu_fixture_0001"
    block.name = "submit_research_brief"
    block.input = _BRIEF_PAYLOAD
    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [block]
    response.usage = MagicMock(input_tokens=10, output_tokens=20)
    return response


def _end_turn_response() -> MagicMock:
    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = []
    response.usage = MagicMock(input_tokens=5, output_tokens=5)
    return response


def emit() -> dict:
    """Run the workflow and return the captured task_context as a plain dict."""
    from workflows.research_agent_workflow import ResearchAgentWorkflow

    with patch(_ANTHROPIC_PATCH) as mock_cls, patch(_PM_PATCH, return_value="mocked prompt"):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.side_effect = [
            _tool_use_response(),
            _end_turn_response(),
        ]

        workflow = ResearchAgentWorkflow()
        # A fixed literal event — no uuid4()/datetime.now() defaults — keeps
        # re-emission deterministic (see module docstring).
        ctx = workflow.run(
            {
                "company_name": "Initech",
                "artifact_id": "00000000-0000-0000-0000-000000000000",
                "timestamp": "2026-07-16T00:00:00+00:00",
            }
        )

    return ctx.model_dump(mode="json")


def main() -> None:
    captured = emit()
    # Timestamps stamped by Workflow.node_context (started_at/completed_at)
    # come from datetime.now(UTC) and would churn the fixture on every
    # re-emission for no informational gain — redact only those, per the D2
    # precedent (redact identifying/non-deterministic fields, never values
    # that describe shape). Everything else — status, usage, node output — is
    # left verbatim.
    for run in captured.get("node_runs", {}).values():
        if run.get("started_at") is not None:
            run["started_at"] = "2026-07-16T00:00:00Z"
        if run.get("completed_at") is not None:
            run["completed_at"] = "2026-07-16T00:00:00Z"

    _FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(captured, indent=2, sort_keys=True) + "\n"
    _FIXTURE_PATH.write_text(content, encoding="utf-8")
    print(f"Wrote {_FIXTURE_PATH}")


if __name__ == "__main__":
    main()
