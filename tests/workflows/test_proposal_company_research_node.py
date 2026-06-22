"""Unit tests for ProposalCompanyResearchNode in proposal_generator_workflow_nodes.

Covers:
- Subclass identity — ProposalCompanyResearchNode is a subclass of Project B's
  CompanyResearchNode without modifying its file.
- Prompt sourced from proposal_research_brief.j2 (not research_agent_brief.j2).
- Initial messages include industry/description/intake_notes context.
- Research evidence is written to TaskContext under the node's output key.
- Loop terminates on end_turn (inherited loop behaviour).
- Works with both dict events and ProposalGeneratorEventSchema Pydantic events.
"""

from unittest.mock import MagicMock, patch

import pytest

from core.task import TaskContext
from schemas.proposal_generator_schema import ProposalGeneratorEventSchema
from schemas.research_agent_schema import ResearchBriefOutput
from workflows.proposal_generator_workflow_nodes.company_research_node import (
    ProposalCompanyResearchNode,
)
from workflows.research_agent_workflow_nodes.company_research_node import (
    CompanyResearchNode as BaseCompanyResearchNode,
)

# Patch paths
_ANTHROPIC_PATCH = "core.nodes.tool_use.anthropic.Anthropic"
_PM_PATCH = (
    "workflows.proposal_generator_workflow_nodes.company_research_node"
    ".PromptManager.get_prompt"
)
_SEARCH_PATCH = (
    "workflows.research_agent_workflow_nodes.company_research_node.SearchService"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dict_ctx(
    company_name: str = "Acme Ltda",
    industry: str = "Agronegócio",
    description: str = "Produtora de grãos",
    intake_notes: str | None = None,
) -> TaskContext:
    return TaskContext(
        event={
            "company_name": company_name,
            "industry": industry,
            "description": description,
            "intake_notes": intake_notes,
        }
    )


def _make_pydantic_ctx(
    company_name: str = "Acme Ltda",
    industry: str = "Agronegócio",
    description: str = "Produtora de grãos",
    intake_notes: str | None = None,
) -> TaskContext:
    event = ProposalGeneratorEventSchema(
        company_name=company_name,
        industry=industry,
        description=description,
        intake_notes=intake_notes,
    )
    return TaskContext(event=event)


def _end_turn_response() -> MagicMock:
    r = MagicMock()
    r.stop_reason = "end_turn"
    r.content = []
    r.usage = MagicMock(input_tokens=10, output_tokens=20)
    return r


def _tool_use_response(tool_id: str, name: str, tool_input: dict) -> MagicMock:
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


def _sample_brief_input(company_name: str = "Acme Ltda") -> dict:
    return {
        "company_name": company_name,
        "what_they_do": "Produtora de grãos com distribuição nacional",
        "likely_time_sinks": [
            "Controle manual de estoque",
            "Emissão de notas fiscais em planilha",
        ],
        "automation_hypothesis": (
            "Automatizar a reconciliação de estoque para economizar 10h/semana"
        ),
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
    return ProposalCompanyResearchNode()


# ---------------------------------------------------------------------------
# Subclass identity — no modification to Project B's file
# ---------------------------------------------------------------------------


class TestSubclassIdentity:
    def test_is_subclass_of_base_company_research_node(self, mock_anthropic_client):
        """ProposalCompanyResearchNode must subclass Project B's CompanyResearchNode."""
        assert issubclass(ProposalCompanyResearchNode, BaseCompanyResearchNode)

    def test_node_name_is_class_name(self, node):
        """node_name returns the concrete class name."""
        assert node.node_name == "ProposalCompanyResearchNode"


# ---------------------------------------------------------------------------
# Prompt sourced from proposal_research_brief.j2
# ---------------------------------------------------------------------------


class TestPromptTemplate:
    def test_proposal_prompt_template_used_not_base_template(
        self, node, mock_anthropic_client
    ):
        """proposal_research_brief.j2 is loaded, not research_agent_brief.j2."""
        ctx = _make_dict_ctx()
        with patch(_PM_PATCH) as mock_pm:
            mock_pm.return_value = "mocked proposal prompt"
            mock_anthropic_client.messages.create.return_value = _end_turn_response()
            node.process(ctx)

        mock_pm.assert_called_once()
        call_args = mock_pm.call_args
        template_name = call_args[0][0] if call_args[0] else call_args[1].get("template_name", "")
        # First positional arg is the template name
        assert call_args[0][0] == "proposal_research_brief"

    def test_prompt_receives_industry_and_description(
        self, node, mock_anthropic_client
    ):
        """PromptManager.get_prompt is called with industry and description kwargs."""
        ctx = _make_dict_ctx(industry="Varejo", description="Loja de roupas")
        with patch(_PM_PATCH) as mock_pm:
            mock_pm.return_value = "prompt"
            mock_anthropic_client.messages.create.return_value = _end_turn_response()
            node.process(ctx)

        call_kwargs = mock_pm.call_args[1]
        assert call_kwargs.get("industry") == "Varejo"
        assert call_kwargs.get("description") == "Loja de roupas"

    def test_prompt_receives_intake_notes_when_provided(
        self, node, mock_anthropic_client
    ):
        """intake_notes is forwarded to PromptManager when present."""
        ctx = _make_dict_ctx(intake_notes="Cliente mencionou 3 sistemas legados")
        with patch(_PM_PATCH) as mock_pm:
            mock_pm.return_value = "prompt"
            mock_anthropic_client.messages.create.return_value = _end_turn_response()
            node.process(ctx)

        call_kwargs = mock_pm.call_args[1]
        assert call_kwargs.get("intake_notes") == "Cliente mencionou 3 sistemas legados"

    def test_prompt_receives_empty_intake_notes_when_absent(
        self, node, mock_anthropic_client
    ):
        """When intake_notes is None, an empty string is forwarded (not None)."""
        ctx = _make_dict_ctx(intake_notes=None)
        with patch(_PM_PATCH) as mock_pm:
            mock_pm.return_value = "prompt"
            mock_anthropic_client.messages.create.return_value = _end_turn_response()
            node.process(ctx)

        call_kwargs = mock_pm.call_args[1]
        assert call_kwargs.get("intake_notes") == ""


# ---------------------------------------------------------------------------
# Initial messages include richer context
# ---------------------------------------------------------------------------


class TestInitialMessagesContent:
    def test_initial_message_includes_company_name(self, node, mock_anthropic_client):
        """The user message seeded into the loop includes the company name."""
        ctx = _make_dict_ctx(company_name="Fazenda Sol Nascente")
        with patch(_PM_PATCH, return_value="prompt"):
            mock_anthropic_client.messages.create.return_value = _end_turn_response()
            node.process(ctx)

        first_call = mock_anthropic_client.messages.create.call_args_list[0]
        messages = first_call.kwargs.get("messages") or first_call[1]["messages"]
        user_content = messages[0]["content"]
        assert "Fazenda Sol Nascente" in user_content

    def test_initial_message_includes_industry(self, node, mock_anthropic_client):
        """The user message includes the industry field."""
        ctx = _make_dict_ctx(industry="Saúde")
        with patch(_PM_PATCH, return_value="prompt"):
            mock_anthropic_client.messages.create.return_value = _end_turn_response()
            node.process(ctx)

        first_call = mock_anthropic_client.messages.create.call_args_list[0]
        messages = first_call.kwargs.get("messages") or first_call[1]["messages"]
        user_content = messages[0]["content"]
        assert "Saúde" in user_content

    def test_initial_message_includes_intake_notes_when_provided(
        self, node, mock_anthropic_client
    ):
        """When intake_notes is set, they appear in the seeded user message."""
        notes = "Usa ERP SAP; equipe de 50 pessoas"
        ctx = _make_dict_ctx(intake_notes=notes)
        with patch(_PM_PATCH, return_value="prompt"):
            mock_anthropic_client.messages.create.return_value = _end_turn_response()
            node.process(ctx)

        first_call = mock_anthropic_client.messages.create.call_args_list[0]
        messages = first_call.kwargs.get("messages") or first_call[1]["messages"]
        user_content = messages[0]["content"]
        assert notes in user_content


# ---------------------------------------------------------------------------
# Works with ProposalGeneratorEventSchema (Pydantic event path)
# ---------------------------------------------------------------------------


class TestPydanticEventPath:
    def test_company_name_extracted_from_pydantic_event(
        self, node, mock_anthropic_client
    ):
        """ProposalGeneratorEventSchema attributes are read correctly via getattr."""
        ctx = _make_pydantic_ctx(
            company_name="Indústria Digital Ltda",
            industry="Tecnologia",
        )
        with patch(_PM_PATCH) as mock_pm:
            mock_pm.return_value = "prompt"
            mock_anthropic_client.messages.create.return_value = _end_turn_response()
            node.process(ctx)

        call_kwargs = mock_pm.call_args[1]
        assert call_kwargs.get("company_name") == "Indústria Digital Ltda"
        assert call_kwargs.get("industry") == "Tecnologia"

    def test_pydantic_event_intake_notes_forwarded(
        self, node, mock_anthropic_client
    ):
        """Optional intake_notes from a Pydantic event are forwarded correctly."""
        ctx = _make_pydantic_ctx(intake_notes="Processo de vendas todo manual")
        with patch(_PM_PATCH) as mock_pm:
            mock_pm.return_value = "prompt"
            mock_anthropic_client.messages.create.return_value = _end_turn_response()
            node.process(ctx)

        call_kwargs = mock_pm.call_args[1]
        assert call_kwargs.get("intake_notes") == "Processo de vendas todo manual"

    def test_pydantic_event_none_intake_notes_becomes_empty_string(
        self, node, mock_anthropic_client
    ):
        """None intake_notes from a Pydantic event is normalised to empty string."""
        ctx = _make_pydantic_ctx(intake_notes=None)
        with patch(_PM_PATCH) as mock_pm:
            mock_pm.return_value = "prompt"
            mock_anthropic_client.messages.create.return_value = _end_turn_response()
            node.process(ctx)

        call_kwargs = mock_pm.call_args[1]
        assert call_kwargs.get("intake_notes") == ""


# ---------------------------------------------------------------------------
# Loop terminates and evidence written to context
# ---------------------------------------------------------------------------


class TestLoopAndContextOutput:
    def test_loop_terminates_on_end_turn(self, node, mock_anthropic_client):
        """Loop exits after one API call when end_turn is returned."""
        with patch(_PM_PATCH, return_value="prompt"):
            mock_anthropic_client.messages.create.return_value = _end_turn_response()
            ctx = _make_dict_ctx()
            result = node.process(ctx)
        assert mock_anthropic_client.messages.create.call_count == 1
        assert result is ctx

    def test_submit_brief_writes_evidence_to_context(
        self, node, mock_anthropic_client
    ):
        """Calling submit_research_brief stores a ResearchBriefOutput on TaskContext."""
        brief_input = _sample_brief_input()
        mock_anthropic_client.messages.create.side_effect = [
            _tool_use_response("id1", "submit_research_brief", brief_input),
            _end_turn_response(),
        ]
        ctx = _make_dict_ctx()
        with patch(_PM_PATCH, return_value="prompt"):
            node.process(ctx)

        stored = ctx.get_node_output("ProposalCompanyResearchNode")
        assert stored is not None
        assert "brief" in stored, f"Expected 'brief' key; got keys: {list(stored.keys())}"
        brief = ResearchBriefOutput(**stored["brief"])
        assert brief.company_name == "Acme Ltda"
        assert len(brief.likely_time_sinks) >= 1

    def test_loop_terminates_after_submit_brief(self, node, mock_anthropic_client):
        """After a valid submit_research_brief, the model can end the loop cleanly."""
        brief_input = _sample_brief_input()
        mock_anthropic_client.messages.create.side_effect = [
            _tool_use_response("id1", "submit_research_brief", brief_input),
            _end_turn_response(),
        ]
        ctx = _make_dict_ctx()
        with patch(_PM_PATCH, return_value="prompt"):
            result = node.process(ctx)
        assert result is ctx
        assert mock_anthropic_client.messages.create.call_count == 2

    def test_no_brief_submitted_context_returns_same_context(
        self, node, mock_anthropic_client
    ):
        """Even when no brief is submitted (end_turn directly), process() returns the context."""
        with patch(_PM_PATCH, return_value="prompt"):
            mock_anthropic_client.messages.create.return_value = _end_turn_response()
            ctx = _make_dict_ctx()
            result = node.process(ctx)

        # process() always returns the same TaskContext object
        assert result is ctx

    def test_web_search_dispatched_during_loop(self, node, mock_anthropic_client):
        """A web_search tool call is dispatched via the inherited SearchService path."""
        mock_anthropic_client.messages.create.side_effect = [
            _tool_use_response("id1", "web_search", {"query": "Acme Ltda Agronegócio"}),
            _end_turn_response(),
        ]
        ctx = _make_dict_ctx()
        with patch(_PM_PATCH, return_value="prompt"), patch(_SEARCH_PATCH) as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.search.return_value = []
            mock_svc_cls.return_value = mock_svc
            node.process(ctx)

        mock_svc.search.assert_called_once_with("Acme Ltda Agronegócio")
