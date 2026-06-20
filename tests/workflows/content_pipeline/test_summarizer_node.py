"""Unit tests for the content_pipeline SummarizerNode.

The agent is mocked: these assert that the node reads the correct upstream
fetched text, runs the agent, and stores a populated ``SummaryOutput`` without
hitting a real model or loading the Jinja environment.
"""

from unittest.mock import MagicMock

from core.nodes.agent import AgentConfig, ModelProvider
from core.task import NodeRun, NodeStatus, TaskContext
from workflows.content_pipeline_workflow_nodes.summarizer_node import (
    SummarizerNode,
    SummaryOutput,
)


def _make_node() -> SummarizerNode:
    """Build a SummarizerNode without constructing a real Agent/model."""
    node = SummarizerNode.__new__(SummarizerNode)
    node.agent = MagicMock()
    return node


def _summary() -> SummaryOutput:
    return SummaryOutput(
        title="Agentic Harnesses 101",
        category="ai_engineering",
        tl_dr="How to wrap an agent in an SDLC loop.",
        read_time_estimate="7 min",
        core_concepts=["harness", "eval loop"],
        key_insights=["self-improvement needs human gates"],
        questions_raised=["how to bound retries?"],
        connections_to_my_work=["maps to the orchestration framework"],
        further_exploration=["read the eval rubric doc"],
    )


def _result_for(summary: SummaryOutput) -> MagicMock:
    result = MagicMock()
    result.output = summary
    result.usage.return_value = MagicMock(input_tokens=10, output_tokens=20)
    return result


class TestSummarizerNodeConfig:
    def test_uses_top_tier_anthropic_model(self):
        node = _make_node()
        config = node.get_agent_config()
        assert isinstance(config, AgentConfig)
        assert config.model_provider is ModelProvider.ANTHROPIC
        assert config.model_name == "claude-opus-4-8"
        assert config.output_type is SummaryOutput
        # System prompt is loaded from the .j2 file, not hardcoded in Python.
        assert "Brandon" in config.system_prompt


class TestSummarizerNodeProcess:
    def test_reads_transcript_text_and_stores_summary(self):
        node = _make_node()
        summary = _summary()
        node.agent.run_sync.return_value = _result_for(summary)

        ctx = TaskContext(event={"url": "https://youtu.be/abc"})
        ctx.nodes["FetchTranscriptNode"] = {
            "text": "full transcript body",
            "fetch_status": "ok",
        }
        ctx.node_runs[node.node_name] = NodeRun(status=NodeStatus.RUNNING)

        node.process(ctx)

        # The agent was run against the upstream transcript text.
        node.agent.run_sync.assert_called_once_with(
            user_prompt="full transcript body"
        )
        stored = ctx.nodes[node.node_name]["result"]
        assert isinstance(stored, SummaryOutput)
        assert stored.title == "Agentic Harnesses 101"
        assert stored.category == "ai_engineering"

    def test_reads_article_text_when_no_transcript(self):
        node = _make_node()
        node.agent.run_sync.return_value = _result_for(_summary())

        ctx = TaskContext(event={"url": "https://example.com/post"})
        ctx.nodes["FetchArticleNode"] = {
            "text": "extracted article body",
            "title": "A Post",
            "fetch_status": "fallback_used",
        }

        node.process(ctx)

        node.agent.run_sync.assert_called_once_with(
            user_prompt="extracted article body"
        )

    def test_missing_fetch_text_does_not_crash(self):
        node = _make_node()
        node.agent.run_sync.return_value = _result_for(_summary())

        ctx = TaskContext(event={"url": "https://example.com/post"})
        # No fetch node output present, or a failed fetch with no text.
        ctx.nodes["FetchArticleNode"] = {"fetch_status": "failed"}

        node.process(ctx)

        node.agent.run_sync.assert_called_once_with(user_prompt="")
        assert isinstance(ctx.nodes[node.node_name]["result"], SummaryOutput)
