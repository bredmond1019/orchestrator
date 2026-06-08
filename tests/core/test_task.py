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
# TaskContext creation
# ---------------------------------------------------------------------------


class TestTaskContextCreation:
    def test_create_with_event_only(self):
        """TaskContext can be created with just an event; nodes and metadata default to empty dicts."""
        ctx = TaskContext(event={"type": "ping"})
        assert ctx.event == {"type": "ping"}
        assert ctx.nodes == {}
        assert ctx.metadata == {}

    def test_create_with_string_event(self):
        """TaskContext accepts any type for event, including a plain string."""
        ctx = TaskContext(event="raw_event_string")
        assert ctx.event == "raw_event_string"

    def test_create_with_pydantic_event(self):
        """TaskContext accepts a Pydantic model instance as the event."""
        from pydantic import BaseModel

        class StubEvent(BaseModel):
            action: str

        event = StubEvent(action="run")
        ctx = TaskContext(event=event)
        assert ctx.event.action == "run"

    def test_create_with_initial_nodes(self):
        """TaskContext accepts a pre-populated nodes dict."""
        ctx = TaskContext(
            event={"type": "test"},
            nodes={"NodeA": {"score": 0.8}},
        )
        assert ctx.nodes == {"NodeA": {"score": 0.8}}

    def test_create_with_initial_metadata(self):
        """TaskContext accepts a pre-populated metadata dict."""
        ctx = TaskContext(
            event={"type": "test"},
            metadata={"priority": "high", "retries": 0},
        )
        assert ctx.metadata["priority"] == "high"
        assert ctx.metadata["retries"] == 0

    def test_create_with_event_nodes_and_metadata(self):
        """TaskContext can be fully initialised in one call."""
        ctx = TaskContext(
            event={"type": "full"},
            nodes={"A": 1},
            metadata={"x": True},
        )
        assert ctx.event == {"type": "full"}
        assert ctx.nodes == {"A": 1}
        assert ctx.metadata == {"x": True}

    def test_nodes_default_is_independent_per_instance(self):
        """Two TaskContext instances do not share the same nodes dict."""
        ctx1 = TaskContext(event="e1")
        ctx2 = TaskContext(event="e2")
        ctx1.nodes["X"] = 1
        assert "X" not in ctx2.nodes

    def test_metadata_default_is_independent_per_instance(self):
        """Two TaskContext instances do not share the same metadata dict."""
        ctx1 = TaskContext(event="e1")
        ctx2 = TaskContext(event="e2")
        ctx1.metadata["k"] = "v"
        assert "k" not in ctx2.metadata


# ---------------------------------------------------------------------------
# update_node
# ---------------------------------------------------------------------------


class TestUpdateNode:
    def test_single_key(self, empty_context):
        """update_node stores a single keyword argument under the node name."""
        empty_context.update_node("MyNode", score=0.5)
        assert empty_context.nodes["MyNode"] == {"score": 0.5}

    def test_multiple_keys(self, empty_context):
        """update_node stores multiple keyword arguments at once."""
        empty_context.update_node("MyNode", score=0.5, label="ok", count=3)
        assert empty_context.nodes["MyNode"] == {
            "score": 0.5,
            "label": "ok",
            "count": 3,
        }

    def test_merges_into_existing_entry(self, empty_context):
        """update_node merges new keys into an existing dict for that node."""
        empty_context.update_node("MyNode", score=0.5)
        empty_context.update_node("MyNode", label="ok")
        assert empty_context.nodes["MyNode"] == {"score": 0.5, "label": "ok"}

    def test_overwrites_existing_key(self, empty_context):
        """update_node overwrites a key that already exists under the node name."""
        empty_context.update_node("MyNode", score=0.1)
        empty_context.update_node("MyNode", score=0.9)
        assert empty_context.nodes["MyNode"]["score"] == 0.9

    def test_multiple_nodes_are_independent(self, empty_context):
        """update_node for one node does not affect another node's dict."""
        empty_context.update_node("Alpha", value=1)
        empty_context.update_node("Beta", value=2)
        assert empty_context.nodes["Alpha"] == {"value": 1}
        assert empty_context.nodes["Beta"] == {"value": 2}

    def test_node_entry_readable_via_get_node_output(self, empty_context):
        """A node written by update_node is retrievable via get_node_output."""
        empty_context.update_node("CheckNode", passed=True)
        assert empty_context.get_node_output("CheckNode") == {"passed": True}


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
