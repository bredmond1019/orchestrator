"""Unit tests for CompanyResearchNode in research_agent_workflow_nodes."""

from unittest.mock import MagicMock, patch

import pytest

from core.task import TaskContext
from schemas.research_agent_schema import ResearchBriefOutput
from workflows.research_agent_workflow_nodes.company_research_node import (
    CompanyResearchNode,
)

# The Anthropic client is instantiated in ToolUseNode.__init__ (core/nodes/tool_use.py).
# Patch there, not in the company_research_node module.
_ANTHROPIC_PATCH = "core.nodes.tool_use.anthropic.Anthropic"
_SEARCH_PATCH = (
    "workflows.research_agent_workflow_nodes.company_research_node.SearchService"
)
_PM_PATCH = (
    "workflows.research_agent_workflow_nodes.company_research_node.PromptManager.get_prompt"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(company_name: str = "Acme Corp") -> TaskContext:
    return TaskContext(event={"company_name": company_name})


def _end_turn_response():
    r = MagicMock()
    r.stop_reason = "end_turn"
    r.content = []
    r.usage = MagicMock(input_tokens=10, output_tokens=20)
    return r


def _tool_use_response(tool_id: str, name: str, tool_input: dict):
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = tool_input
    r = MagicMock()
    r.stop_reason = "tool_use"
    r.content = [block]
    r.usage = MagicMock(input_tokens=10, output_tokens=20)
    return r


def _sample_brief_input(company_name: str = "Acme Corp") -> dict:
    return {
        "company_name": company_name,
        "what_they_do": "A widget manufacturer",
        "likely_time_sinks": ["Manual inventory tracking", "Paper-based compliance"],
        "automation_hypothesis": "Automate inventory reconciliation to save 8 hours/week",
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_anthropic_client():
    with patch(_ANTHROPIC_PATCH) as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def node(mock_anthropic_client, monkeypatch):
    monkeypatch.setenv("TOOL_USE_MODEL", "claude-haiku-4-5-20251001")
    return CompanyResearchNode()


# ---------------------------------------------------------------------------
# System prompt sourced from .j2 (no inline literal)
# ---------------------------------------------------------------------------


class TestSystemPromptSourcedFromTemplate:
    def test_prompt_manager_invoked_for_system_prompt(
        self, node, mock_anthropic_client
    ):
        """The .j2 template is loaded via PromptManager — no hardcoded prompt text."""
        ctx = _make_ctx()

        with patch(_PM_PATCH) as mock_pm:
            mock_pm.return_value = "mocked system prompt"
            mock_anthropic_client.messages.create.return_value = _end_turn_response()
            node.process(ctx)

        mock_pm.assert_called_once_with(
            "research_agent_brief", company_name="Acme Corp"
        )


# ---------------------------------------------------------------------------
# Loop terminates on end_turn
# ---------------------------------------------------------------------------


class TestLoopTerminatesOnEndTurn:
    def test_single_end_turn_makes_exactly_one_api_call(
        self, node, mock_anthropic_client
    ):
        """Loop exits after one API call when the model returns end_turn."""
        with patch(_PM_PATCH, return_value="prompt"):
            mock_anthropic_client.messages.create.return_value = _end_turn_response()
            ctx = _make_ctx()
            result = node.process(ctx)
        assert mock_anthropic_client.messages.create.call_count == 1
        assert result is ctx


# ---------------------------------------------------------------------------
# Tool result injection
# ---------------------------------------------------------------------------


class TestToolResultInjection:
    def test_tool_results_injected_back_into_messages(
        self, node, mock_anthropic_client
    ):
        """After a tool_use response, the result is appended before the next call."""
        mock_anthropic_client.messages.create.side_effect = [
            _tool_use_response("id1", "web_search", {"query": "Acme Corp"}),
            _end_turn_response(),
        ]
        ctx = _make_ctx()

        with patch(_PM_PATCH, return_value="prompt"), patch(_SEARCH_PATCH) as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.search.return_value = []
            mock_svc_cls.return_value = mock_svc
            node.process(ctx)

        assert mock_anthropic_client.messages.create.call_count == 2
        second_call = mock_anthropic_client.messages.create.call_args_list[1]
        messages = second_call.kwargs.get("messages") or second_call[1]["messages"]
        user_msgs = [m for m in messages if m["role"] == "user"]
        last_user_content = user_msgs[-1]["content"]
        assert any(
            isinstance(r, dict) and r.get("type") == "tool_result"
            for r in last_user_content
        )


# ---------------------------------------------------------------------------
# web_search dispatch
# ---------------------------------------------------------------------------


class TestWebSearchDispatch:
    def test_web_search_dispatches_to_search_service(
        self, node, mock_anthropic_client
    ):
        """web_search tool call invokes SearchService.search with the query."""
        mock_anthropic_client.messages.create.side_effect = [
            _tool_use_response("id1", "web_search", {"query": "Acme Corp widgets"}),
            _end_turn_response(),
        ]
        ctx = _make_ctx()

        with patch(_PM_PATCH, return_value="prompt"), patch(_SEARCH_PATCH) as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.search.return_value = []
            mock_svc_cls.return_value = mock_svc
            node.process(ctx)

        mock_svc.search.assert_called_once_with("Acme Corp widgets")

    def test_web_search_formats_results_compactly(self, node, mock_anthropic_client):
        """Results from SearchService are formatted as title/url/snippet lines."""
        from services.search_service import SearchResult

        mock_result = SearchResult(
            title="Acme Corp Overview",
            url="https://acme.example.com",
            content="Acme makes widgets.",
        )
        mock_anthropic_client.messages.create.side_effect = [
            _tool_use_response("id1", "web_search", {"query": "Acme Corp"}),
            _end_turn_response(),
        ]
        ctx = _make_ctx()
        captured_result: list[str] = []

        original_handle = node._handle_web_search

        def _spy(tool_input: dict) -> str:
            result = original_handle(tool_input)
            captured_result.append(result)
            return result

        with patch(_PM_PATCH, return_value="prompt"), patch(_SEARCH_PATCH) as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.search.return_value = [mock_result]
            mock_svc_cls.return_value = mock_svc
            node._handle_web_search = _spy
            node.process(ctx)

        assert captured_result
        assert "Acme Corp Overview" in captured_result[0]
        assert "https://acme.example.com" in captured_result[0]
        assert "Acme makes widgets." in captured_result[0]


# ---------------------------------------------------------------------------
# submit_research_brief — structured brief capture
# ---------------------------------------------------------------------------


class TestSubmitResearchBrief:
    def test_submit_brief_stores_valid_research_brief_output(
        self, node, mock_anthropic_client
    ):
        """submit_research_brief validates into ResearchBriefOutput and stores it."""
        brief_input = _sample_brief_input()
        mock_anthropic_client.messages.create.side_effect = [
            _tool_use_response("id1", "submit_research_brief", brief_input),
            _end_turn_response(),
        ]
        ctx = _make_ctx()
        with patch(_PM_PATCH, return_value="prompt"):
            node.process(ctx)

        stored = ctx.get_node_output("CompanyResearchNode")
        assert stored is not None
        # The structured brief is stored under 'brief'; 'output' is the text
        # extracted by the parent ToolUseNode.process at loop end.
        assert "brief" in stored, f"Expected 'brief' key in stored output, got: {stored}"
        brief = ResearchBriefOutput(**stored["brief"])
        assert brief.company_name == "Acme Corp"
        assert len(brief.likely_time_sinks) >= 1
        assert brief.automation_hypothesis

    def test_submit_brief_returns_ack_string(self, node):
        """submit_research_brief tool call returns a short acknowledgment string."""
        brief_input = _sample_brief_input()
        result = node._handle_submit_brief(brief_input, _make_ctx())
        assert "Acme Corp" in result
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# max_iterations guard
# ---------------------------------------------------------------------------


class TestMaxIterationsGuard:
    def test_loop_exits_at_max_iterations(self, node, mock_anthropic_client):
        """Loop stops at max_iterations even with endless tool_use responses."""
        node.max_iterations = 3
        mock_anthropic_client.messages.create.return_value = _tool_use_response(
            "id1", "web_search", {"query": "runaway"}
        )
        ctx = _make_ctx()

        with patch(_PM_PATCH, return_value="prompt"), patch(_SEARCH_PATCH) as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.search.return_value = []
            mock_svc_cls.return_value = mock_svc
            node.process(ctx)

        assert mock_anthropic_client.messages.create.call_count == 3

    def test_does_not_raise_on_max_iterations(self, node, mock_anthropic_client):
        """Hitting max_iterations does not raise — returns the context."""
        node.max_iterations = 2
        mock_anthropic_client.messages.create.return_value = _tool_use_response(
            "id1", "web_search", {"query": "runaway"}
        )
        ctx = _make_ctx()

        with patch(_PM_PATCH, return_value="prompt"), patch(_SEARCH_PATCH) as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.search.return_value = []
            mock_svc_cls.return_value = mock_svc
            result = node.process(ctx)

        assert result is ctx
