"""Unit tests for TaskContext in app/core/task.py."""

import pytest

from core.task import TaskContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def empty_context():
    """TaskContext with no nodes recorded yet."""
    return TaskContext(event={"type": "test"})


@pytest.fixture()
def populated_context():
    """TaskContext that already has one node's output recorded."""
    ctx = TaskContext(event={"type": "test"})
    ctx.nodes["PresentNode"] = {"result": "hello"}
    return ctx


# ---------------------------------------------------------------------------
# get_node_output — missing node
# ---------------------------------------------------------------------------


class TestGetNodeOutputMissing:
    def test_raises_key_error_when_node_absent(self, empty_context):
        """get_node_output raises KeyError for an unrecorded node name."""
        with pytest.raises(KeyError):
            empty_context.get_node_output("MissingNode")

    def test_error_message_contains_missing_node_name(self, empty_context):
        """KeyError message names the missing node."""
        with pytest.raises(KeyError, match="MissingNode"):
            empty_context.get_node_output("MissingNode")

    def test_error_message_lists_available_nodes(self, populated_context):
        """KeyError message lists nodes that have run so far."""
        with pytest.raises(KeyError, match="PresentNode"):
            populated_context.get_node_output("MissingNode")

    def test_error_message_mentions_workflow_schema(self, empty_context):
        """KeyError message hints at the WorkflowSchema ordering as the fix."""
        with pytest.raises(KeyError, match="WorkflowSchema"):
            empty_context.get_node_output("MissingNode")

    def test_empty_nodes_message_shows_empty_list(self, empty_context):
        """When no nodes have run, the 'completed so far' list is empty."""
        with pytest.raises(KeyError, match=r"\[\]"):
            empty_context.get_node_output("MissingNode")


# ---------------------------------------------------------------------------
# get_node_output — present node
# ---------------------------------------------------------------------------


class TestGetNodeOutputPresent:
    def test_returns_correct_value_for_present_node(self, populated_context):
        """get_node_output returns the stored value when the node exists."""
        result = populated_context.get_node_output("PresentNode")
        assert result == {"result": "hello"}

    def test_returns_exact_object_stored(self, empty_context):
        """get_node_output returns the same object that was stored."""
        sentinel = object()
        empty_context.nodes["SomeNode"] = sentinel
        assert empty_context.get_node_output("SomeNode") is sentinel

    def test_works_after_update_node(self, empty_context):
        """get_node_output works correctly for a node written via update_node."""
        empty_context.update_node("MyNode", score=0.9, label="ok")
        result = empty_context.get_node_output("MyNode")
        assert result == {"score": 0.9, "label": "ok"}

    def test_multiple_nodes_returns_correct_one(self, empty_context):
        """get_node_output returns the right value when multiple nodes exist."""
        empty_context.nodes["Alpha"] = "alpha_value"
        empty_context.nodes["Beta"] = "beta_value"
        assert empty_context.get_node_output("Alpha") == "alpha_value"
        assert empty_context.get_node_output("Beta") == "beta_value"
