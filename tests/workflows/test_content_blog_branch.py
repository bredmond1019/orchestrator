"""Unit tests for the content_pipeline blog branch.

Covers the blog-decision router (gates the branch on ``make_blog``) and the
three linear agent nodes (writer -> self-critic -> revise). Agents are mocked:
no real pydantic-ai ``Agent`` is constructed, so these tests need no API key or
network and never load a model.
"""

from unittest.mock import MagicMock, patch

from core.nodes.agent import AgentNode
from core.nodes.base import Node
from core.task import NodeRun, NodeStatus, TaskContext
from schemas.content_pipeline_schema import ContentPipelineEventSchema
from workflows.content_pipeline_workflow_nodes.blog_decision_router_node import (
    BlogDecisionRouterNode,
    MakeBlogRouter,
)
from workflows.content_pipeline_workflow_nodes.blog_writer_node import BlogWriterNode
from workflows.content_pipeline_workflow_nodes.revise_node import ReviseNode
from workflows.content_pipeline_workflow_nodes.self_critic_node import SelfCriticNode
from workflows.content_pipeline_workflow_nodes.summarizer_node import SummaryOutput


def _make(node_cls):
    """Build an AgentNode subclass without constructing a real Agent/model."""
    node = node_cls.__new__(node_cls)
    node.agent = MagicMock()
    return node


def _result_for(output) -> MagicMock:
    result = MagicMock()
    result.output = output
    result.usage.return_value = MagicMock(input_tokens=1, output_tokens=1)
    return result


def _summary() -> SummaryOutput:
    return SummaryOutput(
        title="Agentic Harnesses 101",
        category="ai_engineering",
        tl_dr="Wrap an agent in an SDLC loop.",
        read_time_estimate="7 min",
        core_concepts=["harness"],
        key_insights=["human gates matter"],
        questions_raised=["how to bound retries?"],
        connections_to_my_work=["maps to the orchestration framework"],
        further_exploration=["read the eval rubric doc"],
    )


def _seed_run(ctx: TaskContext, node: Node) -> None:
    ctx.node_runs[node.node_name] = NodeRun(status=NodeStatus.RUNNING)


# ---------------------------------------------------------------------------
# Blog-decision router
# ---------------------------------------------------------------------------


class TestBlogDecisionRouter:
    def test_router_routes_to_writer_when_make_blog_true(self):
        ctx = TaskContext(
            event=ContentPipelineEventSchema(url="https://x", make_blog=True)
        )
        # The router instantiates a real BlogWriterNode; skip Agent construction
        # (no API key/network in tests) by no-op'ing AgentNode.__init__.
        with patch.object(AgentNode, "__init__", lambda self: None):
            next_node = MakeBlogRouter().determine_next_node(ctx)
        assert isinstance(next_node, BlogWriterNode)

    def test_router_terminates_when_make_blog_false(self):
        ctx = TaskContext(
            event=ContentPipelineEventSchema(url="https://x", make_blog=False)
        )
        assert BlogDecisionRouterNode().route(ctx) is None

    def test_router_route_returns_writer_when_make_blog_true(self):
        ctx = TaskContext(
            event=ContentPipelineEventSchema(url="https://x", make_blog=True)
        )
        with patch.object(AgentNode, "__init__", lambda self: None):
            routed = BlogDecisionRouterNode().route(ctx)
        assert isinstance(routed, BlogWriterNode)


# ---------------------------------------------------------------------------
# Linear agent nodes: writer -> self-critic -> revise
# ---------------------------------------------------------------------------


class TestBlogWriterNode:
    def test_blog_writer_reads_summary_and_records_result(self):
        node = _make(BlogWriterNode)
        draft = BlogWriterNode.OutputType(
            title="Draft Title",
            body_markdown="# Draft\n\nbody",
            reasoning="hook then insights",
        )
        node.agent.run_sync.return_value = _result_for(draft)

        ctx = TaskContext(event=ContentPipelineEventSchema(url="https://x", make_blog=True))
        ctx.nodes["SummarizerNode"] = {"result": _summary()}
        _seed_run(ctx, node)

        node.process(ctx)

        # The agent was run against the JSON-serialized summary.
        node.agent.run_sync.assert_called_once_with(
            user_prompt=_summary().model_dump_json()
        )
        stored = ctx.nodes[node.node_name]["result"]
        assert stored.body_markdown == "# Draft\n\nbody"

    def test_blog_writer_uses_claude_code_sdk_sonnet(self):
        node = _make(BlogWriterNode)
        config = node.get_agent_config()
        assert config.model_provider.value == "claude_code_sdk"
        assert config.model_name == "sonnet"
        assert config.output_type is BlogWriterNode.OutputType
        # Prompt is loaded from the .j2 file, not hardcoded in Python.
        assert "Brandon" in config.system_prompt


class TestSelfCriticNode:
    def test_self_critic_reads_draft(self):
        node = _make(SelfCriticNode)
        critique = SelfCriticNode.OutputType(
            critique="needs a stronger hook",
            issues=["intro is vague"],
            approved=False,
        )
        node.agent.run_sync.return_value = _result_for(critique)

        draft = BlogWriterNode.OutputType(
            title="Draft Title", body_markdown="body", reasoning="r"
        )
        ctx = TaskContext(event=ContentPipelineEventSchema(url="https://x", make_blog=True))
        ctx.nodes["BlogWriterNode"] = {"result": draft}
        _seed_run(ctx, node)

        node.process(ctx)

        node.agent.run_sync.assert_called_once_with(
            user_prompt=draft.model_dump_json()
        )
        stored = ctx.nodes[node.node_name]["result"]
        assert stored.issues == ["intro is vague"]
        assert stored.approved is False


class TestApprovedFieldIsInert:
    """``SelfCriticNode.approved`` carries no control-flow weight.

    The blog branch is a strictly linear, acyclic DAG (writer -> self-critic ->
    revise) — there is no loop-back and no conditional skip. ``ReviseNode``
    therefore always runs, whatever the critic decided. These tests pin that
    intent so a future reader does not mistake the unused field for a latent
    "skip revise when approved" bug.
    """

    def test_self_critic_connects_unconditionally_to_revise(self):
        from workflows.content_pipeline_workflow import ContentPipelineWorkflow

        nodes = ContentPipelineWorkflow.workflow_schema.nodes
        critic_cfg = next(n for n in nodes if n.node is SelfCriticNode)
        # A single static edge to ReviseNode, and the critic is not a router —
        # so nothing reads ``approved`` to choose the next node.
        assert critic_cfg.connections == [ReviseNode]
        assert critic_cfg.is_router is False

    def test_revise_runs_even_when_critic_approved(self):
        node = _make(ReviseNode)
        revised = ReviseNode.OutputType(
            title="Final Title", body_markdown="# Final\n\nrevised body"
        )
        node.agent.run_sync.return_value = _result_for(revised)

        draft = BlogWriterNode.OutputType(
            title="Draft Title", body_markdown="body", reasoning="r"
        )
        # approved=True must NOT short-circuit the revise step.
        critique = SelfCriticNode.OutputType(
            critique="looks great", issues=[], approved=True
        )
        ctx = TaskContext(event=ContentPipelineEventSchema(url="https://x", make_blog=True))
        ctx.nodes["BlogWriterNode"] = {"result": draft}
        ctx.nodes["SelfCriticNode"] = {"result": critique}
        _seed_run(ctx, node)

        node.process(ctx)

        node.agent.run_sync.assert_called_once()
        stored = ctx.nodes[node.node_name]["result"]
        assert stored.body_markdown == "# Final\n\nrevised body"


class TestReviseNode:
    def test_revise_reads_draft_and_critique(self):
        node = _make(ReviseNode)
        revised = ReviseNode.OutputType(
            title="Final Title", body_markdown="# Final\n\nrevised body"
        )
        node.agent.run_sync.return_value = _result_for(revised)

        draft = BlogWriterNode.OutputType(
            title="Draft Title", body_markdown="body", reasoning="r"
        )
        critique = SelfCriticNode.OutputType(
            critique="needs a stronger hook",
            issues=["intro is vague"],
            approved=False,
        )
        ctx = TaskContext(event=ContentPipelineEventSchema(url="https://x", make_blog=True))
        ctx.nodes["BlogWriterNode"] = {"result": draft}
        ctx.nodes["SelfCriticNode"] = {"result": critique}
        _seed_run(ctx, node)

        node.process(ctx)

        # The user prompt threads both the draft and the critique through.
        node.agent.run_sync.assert_called_once()
        sent = node.agent.run_sync.call_args.kwargs["user_prompt"]
        assert "intro is vague" in sent
        assert "body" in sent
        stored = ctx.nodes[node.node_name]["result"]
        assert stored.body_markdown == "# Final\n\nrevised body"
