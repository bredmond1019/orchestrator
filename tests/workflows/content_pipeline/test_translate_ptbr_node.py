"""Unit tests for the content_pipeline TranslatePtBrNode.

The agent is mocked: these assert that the node reads the finished revised post
from ``ReviseNode``, runs the agent against its JSON, and stores a populated
pt-BR ``OutputType`` — without hitting a real model or loading the Jinja
environment. Mirrors the blog-branch node tests.
"""

from unittest.mock import MagicMock

from core.nodes.agent import AgentConfig, ModelProvider
from core.task import NodeRun, NodeStatus, TaskContext
from schemas.content_pipeline_schema import ContentPipelineEventSchema
from workflows.content_pipeline_workflow_nodes.revise_node import ReviseNode
from workflows.content_pipeline_workflow_nodes.translate_ptbr_node import (
    TranslatedTerm,
    TranslatePtBrNode,
)


def _make_node() -> TranslatePtBrNode:
    """Build a TranslatePtBrNode without constructing a real Agent/model."""
    node = TranslatePtBrNode.__new__(TranslatePtBrNode)
    node.agent = MagicMock()
    return node


def _translation() -> TranslatePtBrNode.OutputType:
    return TranslatePtBrNode.OutputType(
        translated_title="Arreios Agênticos 101",
        translated_body_markdown="# Final\n\ncorpo revisado",
        confidence=90,
        cultural_notes=["mantido 'framework' em inglês"],
        technical_terms=[
            TranslatedTerm(
                original="framework",
                translation="framework",
                reasoning="termo amplamente usado em inglês",
            )
        ],
    )


def _result_for(output) -> MagicMock:
    result = MagicMock()
    result.output = output
    result.usage.return_value = MagicMock(input_tokens=10, output_tokens=20)
    return result


class TestTranslatePtBrNodeConfig:
    def test_uses_top_tier_anthropic_model_and_j2_prompt(self):
        node = _make_node()
        config = node.get_agent_config()
        assert isinstance(config, AgentConfig)
        assert config.model_provider is ModelProvider.ANTHROPIC
        assert config.model_name == "claude-opus-4-8"
        assert config.output_type is TranslatePtBrNode.OutputType
        # System prompt is loaded from the .j2 file, not hardcoded in Python.
        assert "pt-BR" in config.system_prompt


class TestTranslatePtBrNodeProcess:
    def test_reads_revised_post_and_stores_translation(self):
        node = _make_node()
        node.agent.run_sync.return_value = _result_for(_translation())

        revised = ReviseNode.OutputType(
            title="Final Title", body_markdown="# Final\n\nrevised body"
        )
        ctx = TaskContext(
            event=ContentPipelineEventSchema(url="https://youtu.be/x", make_blog=True)
        )
        ctx.nodes["ReviseNode"] = {"result": revised}
        ctx.node_runs[node.node_name] = NodeRun(status=NodeStatus.RUNNING)

        node.process(ctx)

        # The agent was run against the JSON-serialized revised post.
        node.agent.run_sync.assert_called_once_with(
            user_prompt=revised.model_dump_json()
        )
        stored = ctx.nodes[node.node_name]["result"]
        assert isinstance(stored, TranslatePtBrNode.OutputType)
        assert stored.translated_body_markdown == "# Final\n\ncorpo revisado"
        assert stored.confidence == 90
        assert stored.technical_terms[0].original == "framework"

    def test_output_defaults_are_lenient(self):
        """Only the two required text fields are mandatory; the rest default."""
        out = TranslatePtBrNode.OutputType(
            translated_title="t", translated_body_markdown="b"
        )
        assert out.confidence == 80
        assert out.cultural_notes == []
        assert out.technical_terms == []
