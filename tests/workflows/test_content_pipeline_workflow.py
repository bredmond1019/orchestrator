"""Tests for the assembled content_pipeline (Project A) workflow.

Two layers:

* **Structure** — registration, schema wiring (start node, router flags,
  connection map) and that ``WorkflowValidator`` accepts the graph (a DAG with
  no cycles and the scaffold ``InitialNode`` gone).
* **Integration** — the full chain run end-to-end with every agent and service
  mocked (no API key, no network, no DB, no real Voyage call): a
  ``make_blog=False`` request runs fetch -> summarize -> store and the blog
  nodes do **not** run; a ``make_blog=True`` request additionally runs the
  linear blog branch (writer -> self-critic -> revise).
"""

from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from pydantic import BaseModel, ValidationError

from core.nodes.agent import AgentNode
from core.task import NodeStatus
from schemas.content_pipeline_schema import ContentPipelineEventSchema
from workflows.content_pipeline_workflow import ContentPipelineWorkflow
from workflows.content_pipeline_workflow_nodes import storage_node
from workflows.content_pipeline_workflow_nodes.blog_decision_router_node import (
    BlogDecisionRouterNode,
)
from workflows.content_pipeline_workflow_nodes.blog_writer_node import BlogWriterNode
from workflows.content_pipeline_workflow_nodes.fetch_article_node import (
    FetchArticleNode,
)
from workflows.content_pipeline_workflow_nodes.fetch_transcript_node import (
    FetchTranscriptNode,
)
from workflows.content_pipeline_workflow_nodes.revise_node import ReviseNode
from workflows.content_pipeline_workflow_nodes.self_critic_node import SelfCriticNode
from workflows.content_pipeline_workflow_nodes.source_router_node import (
    SourceRouterNode,
)
from workflows.content_pipeline_workflow_nodes.storage_node import StorageNode
from workflows.content_pipeline_workflow_nodes.summarizer_node import (
    SummarizerNode,
    SummaryOutput,
)
from workflows.workflow_registry import WorkflowRegistry


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


def test_content_pipeline_registered() -> None:
    """CONTENT_PIPELINE maps to ContentPipelineWorkflow in the registry."""
    assert WorkflowRegistry.CONTENT_PIPELINE.value is ContentPipelineWorkflow


def test_workflow_schema_wired_to_event_schema() -> None:
    """The workflow schema references the event schema and starts at the router."""
    schema = ContentPipelineWorkflow.workflow_schema
    assert schema.event_schema is ContentPipelineEventSchema
    assert schema.start is SourceRouterNode


def test_event_schema_fields_and_defaults() -> None:
    """The event schema requires `url` and defaults `make_blog` to False."""
    assert issubclass(ContentPipelineEventSchema, BaseModel)
    event = ContentPipelineEventSchema(url="https://youtu.be/abc123")
    assert event.url == "https://youtu.be/abc123"
    assert event.make_blog is False
    assert isinstance(event.artifact_id, UUID)
    assert event.timestamp.tzinfo is not None
    assert ContentPipelineEventSchema(url="https://x.com", make_blog=True).make_blog is True
    with pytest.raises(ValidationError):
        ContentPipelineEventSchema()


def test_workflow_validates_and_builds_node_map() -> None:
    """The assembled workflow passes WorkflowValidator and registers every node."""
    workflow = ContentPipelineWorkflow()
    for node_cls in (
        SourceRouterNode,
        FetchTranscriptNode,
        FetchArticleNode,
        SummarizerNode,
        StorageNode,
        BlogDecisionRouterNode,
        BlogWriterNode,
        SelfCriticNode,
        ReviseNode,
    ):
        assert node_cls in workflow.nodes


def test_initial_scaffold_node_removed() -> None:
    """The scaffold InitialNode module is deleted and no longer importable."""
    with pytest.raises(ImportError):
        __import__(
            "workflows.content_pipeline_workflow_nodes.initial_node",
            fromlist=["InitialNode"],
        )


def test_both_routers_marked_is_router() -> None:
    """Only the two router nodes carry is_router=True; the rest do not."""
    configs = {nc.node: nc for nc in ContentPipelineWorkflow.workflow_schema.nodes}
    assert configs[SourceRouterNode].is_router is True
    assert configs[BlogDecisionRouterNode].is_router is True
    for node_cls in (
        FetchTranscriptNode,
        FetchArticleNode,
        SummarizerNode,
        StorageNode,
        BlogWriterNode,
        SelfCriticNode,
        ReviseNode,
    ):
        assert configs[node_cls].is_router is False


def test_connection_map_matches_spec() -> None:
    """Every connection matches the wiring described in the task spec."""
    configs = {nc.node: nc for nc in ContentPipelineWorkflow.workflow_schema.nodes}
    assert set(configs[SourceRouterNode].connections) == {
        FetchTranscriptNode,
        FetchArticleNode,
    }
    assert configs[FetchTranscriptNode].connections == [SummarizerNode]
    assert configs[FetchArticleNode].connections == [SummarizerNode]
    assert configs[SummarizerNode].connections == [StorageNode]
    assert configs[StorageNode].connections == [BlogDecisionRouterNode]
    assert configs[BlogDecisionRouterNode].connections == [BlogWriterNode]
    assert configs[BlogWriterNode].connections == [SelfCriticNode]
    assert configs[SelfCriticNode].connections == [ReviseNode]
    assert configs[ReviseNode].connections == []


def test_graph_is_acyclic_linear_blog_branch() -> None:
    """WorkflowValidator passes: the graph is a DAG (blog branch has no loop-back)."""
    workflow = ContentPipelineWorkflow()
    # validate() raises on a cycle; reaching here means it passed at construction.
    workflow.validator.validate()


def test_workflow_description_filled() -> None:
    """The workflow carries a non-empty description (no scaffold blank)."""
    assert ContentPipelineWorkflow.workflow_schema.description
    assert ContentPipelineWorkflow.workflow_schema.description.strip() != ""


# ---------------------------------------------------------------------------
# Integration — full chain with all agents/services mocked
# ---------------------------------------------------------------------------


def _agent_output_for(node: AgentNode):
    """Return the right OutputType instance for a given mocked agent node."""
    name = type(node).__name__
    if name == "SummarizerNode":
        return SummaryOutput(
            title="Agentic Harnesses 101",
            category="ai_engineering",
            tl_dr="Wrap an agent in an SDLC loop.",
            read_time_estimate="7 min",
            core_concepts=["harness"],
        )
    if name == "BlogWriterNode":
        return BlogWriterNode.OutputType(
            title="Draft", body_markdown="# Draft\n\nbody", reasoning="hook"
        )
    if name == "SelfCriticNode":
        return SelfCriticNode.OutputType(
            critique="needs a hook", issues=["vague intro"], approved=False
        )
    if name == "ReviseNode":
        return ReviseNode.OutputType(title="Final", body_markdown="# Final\n\nbody")
    raise AssertionError(f"unexpected agent node: {name}")


def _fake_run_agent_recorded(self, task_context, user_prompt):  # noqa: ARG001
    """Stand-in for AgentNode.run_agent_recorded — no real model call."""
    result = MagicMock()
    result.output = _agent_output_for(self)
    return result


def _run_pipeline(url: str, make_blog: bool, tmp_path):
    """Run the full workflow with all agents and services mocked.

    Returns the resulting TaskContext (with the captured persisted artifacts
    stashed under ``metadata['persisted']``). AgentNode.__init__ is no-op'd so
    no blog node ever builds a real pydantic-ai Agent.
    """
    persisted: list = []
    with patch.object(AgentNode, "__init__", lambda self: None), patch.object(
        AgentNode, "run_agent_recorded", _fake_run_agent_recorded
    ), patch(
        "workflows.content_pipeline_workflow_nodes.fetch_transcript_node.TranscriptService"
    ) as transcript_svc, patch(
        "workflows.content_pipeline_workflow_nodes.fetch_article_node.ArticleExtractionService"
    ) as article_svc, patch.object(
        storage_node.EmbeddingService, "__init__", lambda self: None
    ), patch.object(
        storage_node.EmbeddingService, "embed_text", lambda self, text: [0.1] * 1024
    ), patch.object(
        storage_node.StorageNode,
        "_persist",
        lambda self, artifact: persisted.append(artifact),
    ), patch.dict(
        "os.environ", {"CONTENT_DIGEST_DIR": str(tmp_path)}
    ):
        transcript_svc.return_value.fetch_transcript.return_value = "transcript text"
        article_svc.return_value.extract.return_value = MagicMock(
            text="article text", title="A Title", fetch_status="ok"
        )
        workflow = ContentPipelineWorkflow()
        ctx = workflow.run({"url": url, "make_blog": make_blog})
    ctx.metadata["persisted"] = persisted
    return ctx


_BLOG_NODES = ("BlogWriterNode", "SelfCriticNode", "ReviseNode")
_DIGEST_NODES = ("SourceRouterNode", "SummarizerNode", "StorageNode")


def test_integration_digest_only_skips_blog_branch(tmp_path) -> None:
    """make_blog=False runs fetch -> summarize -> store; blog nodes never run."""
    ctx = _run_pipeline("https://example.com/post", make_blog=False, tmp_path=tmp_path)

    # The digest path ran to completion.
    for name in _DIGEST_NODES:
        assert ctx.node_runs[name].status is NodeStatus.SUCCESS
    assert ctx.node_runs["FetchArticleNode"].status is NodeStatus.SUCCESS

    # An artifact was persisted with a 1024-dim embedding written at write time.
    persisted = ctx.metadata["persisted"]
    assert len(persisted) == 1
    assert len(persisted[0].embedding) == 1024
    assert persisted[0].make_blog is False

    # A digest page + category index were written.
    category = persisted[0].category
    assert (tmp_path / category / "index.html").exists()

    # The blog nodes were seeded but never executed.
    for name in _BLOG_NODES:
        assert ctx.node_runs[name].status is NodeStatus.PENDING


def test_integration_make_blog_runs_linear_blog_branch(tmp_path) -> None:
    """make_blog=True additionally runs writer -> self-critic -> revise in order."""
    ctx = _run_pipeline("https://youtu.be/abc123", make_blog=True, tmp_path=tmp_path)

    # Digest path still runs; a YouTube URL routes through the transcript node.
    assert ctx.node_runs["FetchTranscriptNode"].status is NodeStatus.SUCCESS
    for name in _DIGEST_NODES:
        assert ctx.node_runs[name].status is NodeStatus.SUCCESS

    # The whole linear blog branch ran.
    for name in _BLOG_NODES:
        assert ctx.node_runs[name].status is NodeStatus.SUCCESS

    # The revised post is the terminal blog output threaded from the draft.
    revised = ctx.get_node_output("ReviseNode")["result"]
    assert revised.body_markdown == "# Final\n\nbody"

    # The persisted artifact recorded the blog flag.
    assert ctx.metadata["persisted"][0].make_blog is True
