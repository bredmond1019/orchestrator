"""Unit tests for the proposal_generator review + router + revise branch (Task 5).

Covers:
- ProposalReviewNode: emits PASS/FAIL per criterion and a verdict
- ProposalReviewRouterNode: routes to StorageNode on pass, ReviseNode on revise
- ProposalReviseNode: reads original roadmap + review, produces revised roadmap

Agents are mocked — no real pydantic-ai Agent is constructed, so these tests
need no API key or network connection.
"""

import json
from unittest.mock import MagicMock, patch

from core.nodes.agent import AgentNode
from core.task import NodeRun, NodeStatus, TaskContext
from schemas.proposal_generator_schema import ProposalGeneratorEventSchema
from workflows.proposal_generator_workflow_nodes.proposal_review_node import (
    CriterionResult,
    ProposalReviewNode,
)
from workflows.proposal_generator_workflow_nodes.proposal_review_router_node import (
    ProposalReviewRouterNode,
    _ReviewVerdictRouter,
)
from workflows.proposal_generator_workflow_nodes.proposal_revise_node import (
    ProposalReviseNode,
)
from workflows.proposal_generator_workflow_nodes.storage_node import StorageNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make(node_cls):
    """Build an AgentNode without constructing a real Agent / model."""
    node = node_cls.__new__(node_cls)
    node.agent = MagicMock()
    return node


def _result_for(output) -> MagicMock:
    result = MagicMock()
    result.output = output
    result.usage.return_value = MagicMock(input_tokens=10, output_tokens=20)
    return result


def _seed_run(ctx: TaskContext, node) -> None:
    ctx.node_runs[node.node_name] = NodeRun(status=NodeStatus.RUNNING)


def _make_event(**kwargs) -> ProposalGeneratorEventSchema:
    defaults = {
        "company_name": "Acme Corp",
        "industry": "Financeiro",
        "description": "Empresa de processamento de pagamentos",
    }
    defaults.update(kwargs)
    return ProposalGeneratorEventSchema(**defaults)


def _make_roadmap_dict() -> dict:
    return {
        "situation_summary": (
            "Acme Corp enfrenta processos manuais custosos. "
            "A Acme Corp pode automatizar faturas. Acme Corp terá ganhos imediatos."
        ),
        "candidates": [],
        "top_profiles": [],
        "recommended_workflow": "Invoice Automation",
        "engagement_scope": "Fase 1: automação de faturas em 4–6 semanas.",
        "price_range_brl": [15000, 25000],
    }


# ---------------------------------------------------------------------------
# ProposalReviewNode
# ---------------------------------------------------------------------------


class TestProposalReviewNode:
    """Review node reads the ProposalWriterNode output and emits a verdict."""

    def test_review_pass_verdict(self):
        node = _make(ProposalReviewNode)
        review_output = ProposalReviewNode.OutputType(
            verdict="pass",
            criteria_results=[
                CriterionResult(criterion="CLIENT NAME", verdict="PASS", note="Found 3 times"),
                CriterionResult(
                    criterion="TESTABLE DELIVERABLE", verdict="PASS", note="Stated clearly"
                ),
                CriterionResult(
                    criterion="REALISTIC TIMELINE", verdict="PASS", note="4-6 weeks mentioned"
                ),
                CriterionResult(
                    criterion="NO VAGUE LANGUAGE", verdict="PASS", note="No filler found"
                ),
                CriterionResult(
                    criterion="INVESTMENT MATCHES COMPLEXITY",
                    verdict="PASS",
                    note="R$15-25k for medium scope",
                ),
            ],
            summary="All criteria passed.",
        )
        node.agent.run_sync.return_value = _result_for(review_output)

        ctx = TaskContext(event=_make_event())
        ctx.nodes["ProposalWriterNode"] = _make_roadmap_dict()
        _seed_run(ctx, node)

        node.process(ctx)

        assert ctx.nodes["ProposalReviewNode"]["result"].verdict == "pass"
        assert len(ctx.nodes["ProposalReviewNode"]["result"].criteria_results) == 5

    def test_review_revise_verdict_on_failure(self):
        node = _make(ProposalReviewNode)
        review_output = ProposalReviewNode.OutputType(
            verdict="revise",
            criteria_results=[
                CriterionResult(
                    criterion="CLIENT NAME",
                    verdict="FAIL",
                    note="Company name appears only once",
                ),
                CriterionResult(
                    criterion="TESTABLE DELIVERABLE",
                    verdict="PASS",
                    note="Stated clearly",
                ),
                CriterionResult(
                    criterion="REALISTIC TIMELINE",
                    verdict="PASS",
                    note="4-6 weeks mentioned",
                ),
                CriterionResult(
                    criterion="NO VAGUE LANGUAGE", verdict="PASS", note="No filler found"
                ),
                CriterionResult(
                    criterion="INVESTMENT MATCHES COMPLEXITY",
                    verdict="PASS",
                    note="Aligned",
                ),
            ],
            summary="Client name criterion failed — name must appear at least 3 times.",
        )
        node.agent.run_sync.return_value = _result_for(review_output)

        ctx = TaskContext(event=_make_event())
        ctx.nodes["ProposalWriterNode"] = _make_roadmap_dict()
        _seed_run(ctx, node)

        node.process(ctx)

        stored = ctx.nodes["ProposalReviewNode"]["result"]
        assert stored.verdict == "revise"
        fail_results = [r for r in stored.criteria_results if r.verdict == "FAIL"]
        assert len(fail_results) == 1
        assert fail_results[0].criterion == "CLIENT NAME"

    def test_review_reads_proposal_writer_output(self):
        """Node reads exactly the ProposalWriterNode context key."""
        node = _make(ProposalReviewNode)
        review_output = ProposalReviewNode.OutputType(
            verdict="pass",
            criteria_results=[],
            summary="All criteria passed.",
        )
        node.agent.run_sync.return_value = _result_for(review_output)

        roadmap = _make_roadmap_dict()
        ctx = TaskContext(event=_make_event())
        ctx.nodes["ProposalWriterNode"] = roadmap
        _seed_run(ctx, node)

        node.process(ctx)

        # Agent must have been called with the writer output as JSON.
        call_args = node.agent.run_sync.call_args
        user_prompt = call_args.kwargs.get("user_prompt") or call_args.args[0]
        parsed = json.loads(user_prompt)
        assert parsed["engagement_scope"] == roadmap["engagement_scope"]

    def test_review_criteria_results_pass_fail_mix(self):
        """Each criterion result carries verdict PASS or FAIL."""
        node = _make(ProposalReviewNode)
        criteria = [
            CriterionResult(criterion="CLIENT NAME", verdict="FAIL", note="Only 1 mention"),
            CriterionResult(criterion="TESTABLE DELIVERABLE", verdict="PASS", note="OK"),
            CriterionResult(criterion="REALISTIC TIMELINE", verdict="FAIL", note="No weeks stated"),
            CriterionResult(criterion="NO VAGUE LANGUAGE", verdict="PASS", note="Clean"),
            CriterionResult(
                criterion="INVESTMENT MATCHES COMPLEXITY", verdict="PASS", note="Aligned"
            ),
        ]
        output = ProposalReviewNode.OutputType(
            verdict="revise",
            criteria_results=criteria,
            summary="Two criteria failed.",
        )
        node.agent.run_sync.return_value = _result_for(output)

        ctx = TaskContext(event=_make_event())
        ctx.nodes["ProposalWriterNode"] = _make_roadmap_dict()
        _seed_run(ctx, node)

        node.process(ctx)

        stored = ctx.nodes["ProposalReviewNode"]["result"]
        verdicts = [r.verdict for r in stored.criteria_results]
        assert "PASS" in verdicts
        assert "FAIL" in verdicts


# ---------------------------------------------------------------------------
# ProposalReviewRouterNode
# ---------------------------------------------------------------------------


class TestProposalReviewRouterNode:
    """Router branches correctly on pass/revise verdict."""

    def test_routes_to_storage_on_pass(self):
        review_result = ProposalReviewNode.OutputType(
            verdict="pass",
            criteria_results=[],
            summary="All criteria passed.",
        )
        ctx = TaskContext(event=_make_event())
        ctx.nodes["ProposalReviewNode"] = {"result": review_result}

        with patch.object(AgentNode, "__init__", lambda self: None):
            next_node = _ReviewVerdictRouter().determine_next_node(ctx)

        assert isinstance(next_node, StorageNode)

    def test_routes_to_revise_on_revise(self):
        review_result = ProposalReviewNode.OutputType(
            verdict="revise",
            criteria_results=[],
            summary="Client name missing.",
        )
        ctx = TaskContext(event=_make_event())
        ctx.nodes["ProposalReviewNode"] = {"result": review_result}

        with patch.object(AgentNode, "__init__", lambda self: None):
            next_node = _ReviewVerdictRouter().determine_next_node(ctx)

        assert isinstance(next_node, ProposalReviseNode)

    def test_routes_to_revise_on_dict_verdict(self):
        """Router handles serialized dict result (after model_dump)."""
        ctx = TaskContext(event=_make_event())
        ctx.nodes["ProposalReviewNode"] = {"result": {"verdict": "revise", "summary": "Issues"}}

        with patch.object(AgentNode, "__init__", lambda self: None):
            next_node = _ReviewVerdictRouter().determine_next_node(ctx)

        assert isinstance(next_node, ProposalReviseNode)

    def test_routes_to_storage_on_dict_pass(self):
        """Router handles serialized dict with pass verdict."""
        ctx = TaskContext(event=_make_event())
        ctx.nodes["ProposalReviewNode"] = {"result": {"verdict": "pass", "summary": "All good"}}

        with patch.object(AgentNode, "__init__", lambda self: None):
            next_node = _ReviewVerdictRouter().determine_next_node(ctx)

        assert isinstance(next_node, StorageNode)

    def test_router_process_records_next_node(self):
        """BaseRouter.process writes next_node to context."""
        review_result = ProposalReviewNode.OutputType(
            verdict="pass",
            criteria_results=[],
            summary="All criteria passed.",
        )
        ctx = TaskContext(event=_make_event())
        ctx.nodes["ProposalReviewNode"] = {"result": review_result}

        with patch.object(AgentNode, "__init__", lambda self: None):
            router = ProposalReviewRouterNode()
            router.process(ctx)

        assert "ProposalReviewRouterNode" in ctx.nodes
        assert ctx.nodes["ProposalReviewRouterNode"]["next_node"] == "StorageNode"

    def test_router_has_no_fallback(self):
        """ProposalReviewRouterNode has no fallback — missing verdict returns None."""
        ctx = TaskContext(event=_make_event())
        ctx.nodes["ProposalReviewNode"] = {"result": None}

        router = ProposalReviewRouterNode()
        assert router.fallback is None
        next_node = _ReviewVerdictRouter().determine_next_node(ctx)
        assert next_node is None


# ---------------------------------------------------------------------------
# ProposalReviseNode
# ---------------------------------------------------------------------------


class TestProposalReviseNode:
    """Revise node reads both writer output and review result, produces corrected roadmap."""

    def _make_revise_output(self) -> ProposalReviseNode.OutputType:
        return ProposalReviseNode.OutputType(
            situation_summary=(
                "Acme Corp processamento manual gera custos. "
                "A Acme Corp pode automatizar. Acme Corp verá retorno."
            ),
            candidates_json="[]",
            top_profiles_json="[]",
            recommended_workflow="Invoice Automation",
            engagement_scope="Fase 1: automação de faturas em 4–6 semanas.",
            price_range_brl_min=15000,
            price_range_brl_max=25000,
            body_pt="Texto em português revisado.",
            body_en=None,
            revision_notes="Added company name 2 more times to meet ≥3 criterion.",
        )

    def test_revise_reads_writer_and_review_outputs(self):
        node = _make(ProposalReviseNode)
        output = self._make_revise_output()
        node.agent.run_sync.return_value = _result_for(output)

        ctx = TaskContext(event=_make_event())
        ctx.nodes["ProposalWriterNode"] = _make_roadmap_dict()
        ctx.nodes["ProposalReviewNode"] = {
            "result": {
                "verdict": "revise",
                "criteria_results": [
                    {"criterion": "CLIENT NAME", "verdict": "FAIL", "note": "Only 1 mention"}
                ],
                "summary": "Client name must appear 3 times.",
            }
        }
        _seed_run(ctx, node)

        node.process(ctx)

        # Agent must receive both the original roadmap and the review.
        call_args = node.agent.run_sync.call_args
        user_prompt = call_args.kwargs.get("user_prompt") or call_args.args[0]
        payload = json.loads(user_prompt)
        assert "original_roadmap" in payload
        assert "review_result" in payload
        assert "event" in payload

    def test_revise_produces_corrected_roadmap(self):
        node = _make(ProposalReviseNode)
        output = self._make_revise_output()
        node.agent.run_sync.return_value = _result_for(output)

        ctx = TaskContext(event=_make_event())
        ctx.nodes["ProposalWriterNode"] = _make_roadmap_dict()
        ctx.nodes["ProposalReviewNode"] = {
            "result": {"verdict": "revise", "summary": "Fix client name"}
        }
        _seed_run(ctx, node)

        node.process(ctx)

        stored = ctx.nodes["ProposalReviseNode"]["result"]
        assert stored.revision_notes != ""
        assert stored.engagement_scope != ""
        assert stored.price_range_brl_min > 0
        assert stored.price_range_brl_max >= stored.price_range_brl_min

    def test_revise_includes_event_context(self):
        """Event context (company_name, industry, language) is forwarded to agent."""
        node = _make(ProposalReviseNode)
        output = self._make_revise_output()
        node.agent.run_sync.return_value = _result_for(output)

        event = _make_event(company_name="TechBrasil", language="PT")
        ctx = TaskContext(event=event)
        ctx.nodes["ProposalWriterNode"] = _make_roadmap_dict()
        ctx.nodes["ProposalReviewNode"] = {
            "result": {"verdict": "revise", "summary": "Issues"}
        }
        _seed_run(ctx, node)

        node.process(ctx)

        call_args = node.agent.run_sync.call_args
        user_prompt = call_args.kwargs.get("user_prompt") or call_args.args[0]
        payload = json.loads(user_prompt)
        assert payload["event"]["company_name"] == "TechBrasil"
        assert payload["event"]["language"] == "PT"

    def test_revise_flows_to_storage_after_revise(self):
        """After ReviseNode, the router should ultimately route to StorageNode.

        This is a structural/DAG test: ReviseNode connects to StorageNode in
        the workflow schema (Task 7). Here we confirm that a 'pass' verdict
        produced by routing after revision would go to StorageNode.
        """
        # Simulate: after revise, verdict context would be 'pass' in Task 7 flow.
        # Just verify the router routes to StorageNode on pass.
        review_result_pass = ProposalReviewNode.OutputType(
            verdict="pass",
            criteria_results=[],
            summary="All criteria passed.",
        )
        ctx = TaskContext(event=_make_event())
        ctx.nodes["ProposalReviewNode"] = {"result": review_result_pass}

        with patch.object(AgentNode, "__init__", lambda self: None):
            next_node = _ReviewVerdictRouter().determine_next_node(ctx)

        assert isinstance(next_node, StorageNode)
