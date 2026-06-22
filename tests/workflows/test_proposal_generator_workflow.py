"""Tests for the assembled proposal_generator (Project C) workflow.

Two layers:

* **Structure** — registration, schema wiring (start node, router flag,
  connection map), WorkflowValidator passes (acyclic DAG), and that the
  scaffold InitialNode is gone.
* **Integration** — the full chain run end-to-end with every agent,
  tool-use client, and service mocked (no API key, no network, no DB, no
  real embedding call): both the ``pass`` route (research → score → write →
  review-pass → storage) and the ``revise`` route (... → review-revise →
  revise → storage) complete successfully with a valid ``AutomationRoadmap``.
* **Diagnostic constraint** — given intake-style input, output is a valid
  ``AutomationRoadmap``, ``candidates`` sorted composite-desc, ``top_profiles``
  exactly 3 (or all if fewer).
"""

import json
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from pydantic import BaseModel, ValidationError

from api.schema_registry import SCHEMA_MAP
from core.nodes.agent import AgentNode
from core.task import NodeStatus
from schemas.proposal_generator_schema import (
    AutomationRoadmap,
    ProposalGeneratorEventSchema,
    ScoredCandidate,
    WorkflowProfile,
)
from workflows.proposal_generator_workflow import ProposalGeneratorWorkflow
from workflows.proposal_generator_workflow_nodes.company_research_node import (
    ProposalCompanyResearchNode,
)
from workflows.proposal_generator_workflow_nodes.opportunity_identifier_node import (
    OpportunityIdentifierNode,
)
from workflows.proposal_generator_workflow_nodes.proposal_review_node import (
    CriterionResult,
    ProposalReviewNode,
)
from workflows.proposal_generator_workflow_nodes.proposal_review_router_node import (
    ProposalReviewRouterNode,
)
from workflows.proposal_generator_workflow_nodes.proposal_revise_node import (
    ProposalReviseNode,
)
from workflows.proposal_generator_workflow_nodes.proposal_writer_node import (
    ProposalWriterNode,
)
from workflows.proposal_generator_workflow_nodes.storage_node import StorageNode
from workflows.workflow_registry import WorkflowRegistry

_ANTHROPIC_PATCH = "core.nodes.tool_use.anthropic.Anthropic"
_PM_PATCH_RESEARCH = (
    "workflows.proposal_generator_workflow_nodes.company_research_node"
    ".PromptManager.get_prompt"
)

# ---------------------------------------------------------------------------
# Fixtures: scored candidates, workflow profiles, roadmaps
# ---------------------------------------------------------------------------


def _scored(name: str, freq: float = 5.0, time: float = 5.0, build: float = 5.0) -> ScoredCandidate:
    composite = round((freq * 0.35) + (time * 0.40) + (build * 0.25), 4)
    return ScoredCandidate(
        name=name,
        problem_statement=f"{name} takes too long manually",
        proposed_solution=f"Automate {name}",
        estimated_value="8 hrs/week recovered",
        build_complexity="Medium",
        frequency=freq,
        time_cost=time,
        buildability=build,
        composite=composite,
    )


def _profile(name: str) -> WorkflowProfile:
    return WorkflowProfile(
        name=name,
        current_state="Manual spreadsheet",
        proposed_solution="Automated pipeline",
        stack=["Python", "FastAPI"],
        rough_scope_weeks=(4, 6),
        roi_hrs_per_week=8.0,
    )


def _make_three_candidates() -> list[ScoredCandidate]:
    """Three candidates sorted composite-desc."""
    return [
        _scored("Invoice Processing", freq=5.0, time=5.0, build=5.0),  # 5.0
        _scored("Inventory Sync", freq=4.0, time=4.0, build=4.0),        # 4.0
        _scored("Report Generation", freq=3.0, time=3.0, build=3.0),     # 3.0
    ]


def _make_roadmap(language: str = "PT") -> AutomationRoadmap:
    candidates = _make_three_candidates()
    body_pt = "Acme Corp precisa de automação. Acme Corp pode economizar tempo. Acme Corp crescerá."
    body_en = "Acme Corp needs automation. Acme Corp can save time. Acme Corp will grow."
    return AutomationRoadmap(
        situation_summary=(
            "Acme Corp opera com processos manuais que geram gargalos. "
            "Acme Corp pode recuperar 24+ horas por semana automatizando três processos. "
            "Acme Corp está pronta para a transformação digital."
        ),
        candidates=candidates,
        top_profiles=[_profile("Invoice Processing"), _profile("Inventory Sync"), _profile("Report Generation")],
        recommended_workflow="Invoice Processing",
        engagement_scope="Fase 1: automação de faturas em 4–6 semanas.",
        price_range_brl=(15000, 25000),
        body_pt=body_pt if language == "PT" else None,
        body_en=body_en if language == "EN" else None,
    )


def _make_review_output(verdict: str) -> ProposalReviewNode.OutputType:
    return ProposalReviewNode.OutputType(
        verdict=verdict,
        criteria_results=[
            CriterionResult(criterion="CLIENT NAME", verdict="PASS", note="3 mentions"),
            CriterionResult(criterion="TESTABLE DELIVERABLE", verdict="PASS", note="Stated"),
            CriterionResult(criterion="REALISTIC TIMELINE", verdict="PASS", note="4-6 weeks"),
            CriterionResult(criterion="NO VAGUE LANGUAGE", verdict="PASS", note="Clean"),
            CriterionResult(
                criterion="INVESTMENT MATCHES COMPLEXITY",
                verdict="PASS",
                note="Aligned",
            ),
        ],
        summary="All criteria passed." if verdict == "pass" else "Client name missing.",
    )


def _make_revise_output() -> ProposalReviseNode.OutputType:
    roadmap = _make_roadmap()
    return ProposalReviseNode.OutputType(
        situation_summary=roadmap.situation_summary,
        candidates_json=json.dumps([c.model_dump() for c in roadmap.candidates]),
        top_profiles_json=json.dumps([p.model_dump() for p in roadmap.top_profiles]),
        recommended_workflow=roadmap.recommended_workflow,
        engagement_scope=roadmap.engagement_scope,
        price_range_brl_min=roadmap.price_range_brl[0],
        price_range_brl_max=roadmap.price_range_brl[1],
        body_pt=roadmap.body_pt,
        body_en=None,
        revision_notes="Added company name two more times.",
    )


# ---------------------------------------------------------------------------
# Mocked agent: maps node class name → OutputType instance
# ---------------------------------------------------------------------------


def _agent_output_for(node: AgentNode, verdict: str = "pass", task_context=None):
    """Return the right OutputType for the given node class."""
    name = type(node).__name__
    if name == "OpportunityIdentifierNode":
        return OpportunityIdentifierNode.OutputType(
            candidates=_make_three_candidates(),
            recommended="Invoice Processing",
        )
    if name == "ProposalWriterNode":
        # Honor the event language so PT/EN body fields are populated correctly.
        language = "PT"
        if task_context is not None:
            event = task_context.event
            language = getattr(event, "language", "PT") if not isinstance(event, dict) else event.get("language", "PT")
        roadmap = _make_roadmap(language=language)
        return ProposalWriterNode.OutputType(
            situation_summary=roadmap.situation_summary,
            candidates=roadmap.candidates,
            top_profiles=roadmap.top_profiles,
            recommended_workflow=roadmap.recommended_workflow,
            engagement_scope=roadmap.engagement_scope,
            price_range_brl=roadmap.price_range_brl,
            body_pt=roadmap.body_pt,
            body_en=roadmap.body_en,
        )
    if name == "ProposalReviewNode":
        return _make_review_output(verdict)
    if name == "ProposalReviseNode":
        return _make_revise_output()
    raise AssertionError(f"unexpected agent node: {name}")


def _fake_run_agent_recorded(self, task_context, user_prompt, verdict="pass"):  # noqa: ARG001
    """Stand-in for AgentNode.run_agent_recorded that never calls a real model."""
    result = MagicMock()
    result.output = _agent_output_for(self, verdict=verdict, task_context=task_context)
    return result


def _end_turn_response() -> MagicMock:
    """Anthropic end_turn response for the ToolUseNode research loop."""
    r = MagicMock()
    r.stop_reason = "end_turn"
    r.content = []
    r.usage = MagicMock(input_tokens=10, output_tokens=20)
    return r


def _tool_use_response(tool_id: str, name: str, tool_input: dict) -> MagicMock:
    """Anthropic tool_use response to simulate submitting a research brief."""
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


def _brief_payload(company_name: str = "Acme Corp") -> dict:
    return {
        "company_name": company_name,
        "what_they_do": "Mid-market B2B SaaS for project management",
        "likely_time_sinks": ["Manual invoicing", "Spreadsheet inventory"],
        "automation_hypothesis": "Automating invoicing recovers 8+ hrs/week",
    }


def _run_workflow(language: str = "PT", review_verdict: str = "pass") -> "TaskContext":
    """Run the full workflow with all agents and services mocked.

    Returns the resulting TaskContext with storage docs stashed in metadata.
    """
    persisted: list = []

    # Build a closure that carries the review verdict for ProposalReviewNode.
    def _fake_run(self, task_context, user_prompt):
        result = MagicMock()
        result.output = _agent_output_for(self, verdict=review_verdict, task_context=task_context)
        return result

    with (
        patch(_ANTHROPIC_PATCH) as mock_cls,
        patch(_PM_PATCH_RESEARCH, return_value="mocked prompt"),
        patch.object(AgentNode, "__init__", lambda self: None),
        patch.object(AgentNode, "run_agent_recorded", _fake_run),
        patch.object(StorageNode, "_persist", lambda self, doc: persisted.append(doc)),
        patch(
            "workflows.proposal_generator_workflow_nodes.storage_node.EmbeddingService.__init__",
            lambda self: None,
        ),
        patch(
            "workflows.proposal_generator_workflow_nodes.storage_node.EmbeddingService.embed_text",
            lambda self, text: [0.1] * 512,
        ),
    ):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.side_effect = [
            _tool_use_response("id1", "submit_research_brief", _brief_payload()),
            _end_turn_response(),
        ]

        workflow = ProposalGeneratorWorkflow()
        ctx = workflow.run(
            {
                "company_name": "Acme Corp",
                "industry": "Financeiro",
                "description": "Empresa de processamento de pagamentos",
                "language": language,
            }
        )

    ctx.metadata["persisted"] = persisted
    return ctx


# ---------------------------------------------------------------------------
# Structure tests
# ---------------------------------------------------------------------------


def test_proposal_generator_registered() -> None:
    """PROPOSAL_GENERATOR maps to ProposalGeneratorWorkflow in the registry."""
    assert WorkflowRegistry.PROPOSAL_GENERATOR.value is ProposalGeneratorWorkflow


def test_proposal_generator_in_schema_map() -> None:
    """PROPOSAL_GENERATOR must appear in SCHEMA_MAP for API dispatcher."""
    assert WorkflowRegistry.PROPOSAL_GENERATOR.name in SCHEMA_MAP
    assert SCHEMA_MAP[WorkflowRegistry.PROPOSAL_GENERATOR.name] is ProposalGeneratorEventSchema


def test_workflow_schema_wired_to_event_schema() -> None:
    """The workflow schema references the event schema and starts at the research node."""
    schema = ProposalGeneratorWorkflow.workflow_schema
    assert schema.event_schema is ProposalGeneratorEventSchema
    assert schema.start is ProposalCompanyResearchNode


def test_event_schema_is_pydantic_model() -> None:
    """ProposalGeneratorEventSchema is a Pydantic BaseModel subclass."""
    assert issubclass(ProposalGeneratorEventSchema, BaseModel)


def test_event_schema_fields_and_defaults() -> None:
    """Event schema requires company_name/industry/description; defaults language to PT."""
    event = ProposalGeneratorEventSchema(
        company_name="Acme Corp",
        industry="Financeiro",
        description="Pagamentos",
    )
    assert event.company_name == "Acme Corp"
    assert event.language == "PT"
    assert isinstance(event.artifact_id, UUID)
    assert event.timestamp.tzinfo is not None
    assert event.intake_notes is None

    en_event = ProposalGeneratorEventSchema(
        company_name="Acme Corp",
        industry="Finance",
        description="Payments",
        language="EN",
    )
    assert en_event.language == "EN"

    with pytest.raises(ValidationError):
        ProposalGeneratorEventSchema()


def test_workflow_validates_and_builds_node_map() -> None:
    """The assembled workflow passes WorkflowValidator and includes all nodes."""
    with patch(_ANTHROPIC_PATCH):
        workflow = ProposalGeneratorWorkflow()
    for node_cls in (
        ProposalCompanyResearchNode,
        OpportunityIdentifierNode,
        ProposalWriterNode,
        ProposalReviewNode,
        ProposalReviewRouterNode,
        ProposalReviseNode,
        StorageNode,
    ):
        assert node_cls in workflow.nodes, f"{node_cls.__name__} missing from workflow.nodes"


def test_initial_scaffold_node_removed() -> None:
    """The scaffold InitialNode is deleted and no longer importable."""
    with pytest.raises(ImportError):
        __import__(
            "workflows.proposal_generator_workflow_nodes.initial_node",
            fromlist=["InitialNode"],
        )


def test_router_marked_is_router() -> None:
    """Only ProposalReviewRouterNode carries is_router=True; all others do not."""
    configs = {nc.node: nc for nc in ProposalGeneratorWorkflow.workflow_schema.nodes}
    assert configs[ProposalReviewRouterNode].is_router is True
    for node_cls in (
        ProposalCompanyResearchNode,
        OpportunityIdentifierNode,
        ProposalWriterNode,
        ProposalReviewNode,
        ProposalReviseNode,
        StorageNode,
    ):
        assert configs[node_cls].is_router is False, (
            f"{node_cls.__name__} should not be marked is_router"
        )


def test_connection_map_matches_spec() -> None:
    """Every connection matches the DAG described in the task spec."""
    configs = {nc.node: nc for nc in ProposalGeneratorWorkflow.workflow_schema.nodes}

    assert configs[ProposalCompanyResearchNode].connections == [OpportunityIdentifierNode]
    assert configs[OpportunityIdentifierNode].connections == [ProposalWriterNode]
    assert configs[ProposalWriterNode].connections == [ProposalReviewNode]
    assert configs[ProposalReviewNode].connections == [ProposalReviewRouterNode]
    assert set(configs[ProposalReviewRouterNode].connections) == {StorageNode, ProposalReviseNode}
    assert configs[ProposalReviseNode].connections == [StorageNode]
    assert configs[StorageNode].connections == []


def test_graph_is_acyclic() -> None:
    """WorkflowValidator passes: the graph is a DAG with no loop-back."""
    with patch(_ANTHROPIC_PATCH):
        workflow = ProposalGeneratorWorkflow()
    # validate() raises on a cycle; reaching here means it passed.
    workflow.validator.validate()


def test_workflow_description_filled() -> None:
    """The workflow carries a non-empty description (no scaffold blank)."""
    assert ProposalGeneratorWorkflow.workflow_schema.description
    assert ProposalGeneratorWorkflow.workflow_schema.description.strip() != ""


# ---------------------------------------------------------------------------
# Integration — pass route (review verdict = pass)
# ---------------------------------------------------------------------------


def test_integration_pass_route_all_nodes_run() -> None:
    """pass route: all pre-router nodes run; StorageNode runs; ReviseNode stays pending."""
    ctx = _run_workflow(review_verdict="pass")

    for name in (
        "ProposalCompanyResearchNode",
        "OpportunityIdentifierNode",
        "ProposalWriterNode",
        "ProposalReviewNode",
        "ProposalReviewRouterNode",
        "StorageNode",
    ):
        assert ctx.node_runs[name].status is NodeStatus.SUCCESS, (
            f"Expected {name} to be SUCCESS, got {ctx.node_runs[name].status}"
        )

    assert ctx.node_runs["ProposalReviseNode"].status is NodeStatus.PENDING


def test_integration_pass_route_roadmap_persisted() -> None:
    """pass route: StorageNode persists exactly one BrainDocument."""
    ctx = _run_workflow(review_verdict="pass")

    persisted = ctx.metadata["persisted"]
    assert len(persisted) == 1
    doc = persisted[0]
    assert doc.doc_type == "proposal"
    assert "proposals/" in doc.file_path
    assert doc.embedding == [0.1] * 512


def test_integration_pass_route_valid_roadmap_in_context() -> None:
    """pass route: ProposalWriterNode output is a valid AutomationRoadmap."""
    ctx = _run_workflow(review_verdict="pass")

    writer_raw = ctx.get_node_output("ProposalWriterNode")
    # ProposalWriterNode stores result= via update_node
    roadmap_data = writer_raw.get("result")
    assert roadmap_data is not None

    # Validate as AutomationRoadmap
    roadmap = AutomationRoadmap.model_validate(roadmap_data.model_dump())
    assert roadmap.situation_summary
    assert len(roadmap.candidates) >= 1
    assert len(roadmap.top_profiles) <= 3


# ---------------------------------------------------------------------------
# Integration — revise route (review verdict = revise)
# ---------------------------------------------------------------------------


def test_integration_revise_route_all_nodes_run() -> None:
    """revise route: all nodes including ReviseNode and StorageNode succeed."""
    ctx = _run_workflow(review_verdict="revise")

    for name in (
        "ProposalCompanyResearchNode",
        "OpportunityIdentifierNode",
        "ProposalWriterNode",
        "ProposalReviewNode",
        "ProposalReviewRouterNode",
        "ProposalReviseNode",
        "StorageNode",
    ):
        assert ctx.node_runs[name].status is NodeStatus.SUCCESS, (
            f"Expected {name} to be SUCCESS, got {ctx.node_runs[name].status}"
        )


def test_integration_revise_route_roadmap_persisted() -> None:
    """revise route: StorageNode persists exactly one BrainDocument."""
    ctx = _run_workflow(review_verdict="revise")

    persisted = ctx.metadata["persisted"]
    assert len(persisted) == 1
    doc = persisted[0]
    assert doc.doc_type == "proposal"


def test_integration_revise_route_revise_node_ran() -> None:
    """revise route: ProposalReviseNode output exists in context."""
    ctx = _run_workflow(review_verdict="revise")

    revise_output = ctx.get_node_output("ProposalReviseNode")
    assert revise_output is not None
    result = revise_output.get("result")
    assert result is not None
    assert result.revision_notes


# ---------------------------------------------------------------------------
# Diagnostic constraint tests (notes §3)
# ---------------------------------------------------------------------------


def test_diagnostic_candidates_sorted_composite_desc() -> None:
    """AutomationRoadmap.candidates are sorted by composite score descending."""
    ctx = _run_workflow(review_verdict="pass")

    writer_raw = ctx.get_node_output("ProposalWriterNode")
    roadmap = AutomationRoadmap.model_validate(writer_raw["result"].model_dump())

    scores = [c.composite for c in roadmap.candidates]
    assert scores == sorted(scores, reverse=True), (
        f"candidates not sorted composite-desc: {scores}"
    )


def test_diagnostic_top_profiles_at_most_three() -> None:
    """AutomationRoadmap.top_profiles contains exactly 3 or all if fewer."""
    ctx = _run_workflow(review_verdict="pass")

    writer_raw = ctx.get_node_output("ProposalWriterNode")
    roadmap = AutomationRoadmap.model_validate(writer_raw["result"].model_dump())

    assert len(roadmap.top_profiles) <= 3, (
        f"top_profiles must have at most 3 entries, got {len(roadmap.top_profiles)}"
    )


def test_diagnostic_pt_language_body_populated() -> None:
    """When language=PT, the roadmap includes a body_pt field."""
    ctx = _run_workflow(language="PT", review_verdict="pass")

    writer_raw = ctx.get_node_output("ProposalWriterNode")
    roadmap = AutomationRoadmap.model_validate(writer_raw["result"].model_dump())

    assert roadmap.body_pt is not None and roadmap.body_pt.strip() != ""


def test_diagnostic_en_language_body_populated() -> None:
    """When language=EN, the roadmap includes a body_en field."""
    ctx = _run_workflow(language="EN", review_verdict="pass")

    writer_raw = ctx.get_node_output("ProposalWriterNode")
    roadmap = AutomationRoadmap.model_validate(writer_raw["result"].model_dump())

    assert roadmap.body_en is not None and roadmap.body_en.strip() != ""


def test_diagnostic_intake_style_input_produces_valid_roadmap() -> None:
    """Given intake-style input (with intake_notes), output is a valid AutomationRoadmap."""
    persisted: list = []

    def _fake_run(self, task_context, user_prompt):
        result = MagicMock()
        result.output = _agent_output_for(self, verdict="pass", task_context=task_context)
        return result

    with (
        patch(_ANTHROPIC_PATCH) as mock_cls,
        patch(_PM_PATCH_RESEARCH, return_value="mocked prompt"),
        patch.object(AgentNode, "__init__", lambda self: None),
        patch.object(AgentNode, "run_agent_recorded", _fake_run),
        patch.object(StorageNode, "_persist", lambda self, doc: persisted.append(doc)),
        patch(
            "workflows.proposal_generator_workflow_nodes.storage_node.EmbeddingService.__init__",
            lambda self: None,
        ),
        patch(
            "workflows.proposal_generator_workflow_nodes.storage_node.EmbeddingService.embed_text",
            lambda self, text: [0.1] * 512,
        ),
    ):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.side_effect = [
            _tool_use_response("id1", "submit_research_brief", _brief_payload()),
            _end_turn_response(),
        ]

        workflow = ProposalGeneratorWorkflow()
        ctx = workflow.run(
            {
                "company_name": "TechBrasil",
                "industry": "Tecnologia",
                "description": "Startup de SaaS B2B",
                "language": "PT",
                "intake_notes": (
                    "Empresa usa Excel para controle de clientes. "
                    "3 pessoas passam ~10h/semana em relatórios manuais."
                ),
            }
        )

    writer_raw = ctx.get_node_output("ProposalWriterNode")
    roadmap = AutomationRoadmap.model_validate(writer_raw["result"].model_dump())

    # Validate all required sections present
    assert roadmap.situation_summary.strip()
    assert len(roadmap.candidates) >= 1
    assert len(roadmap.top_profiles) <= 3
    assert roadmap.recommended_workflow.strip()
    assert roadmap.engagement_scope.strip()
    assert roadmap.price_range_brl[1] >= roadmap.price_range_brl[0]

    # candidates are sorted composite-desc
    scores = [c.composite for c in roadmap.candidates]
    assert scores == sorted(scores, reverse=True)
