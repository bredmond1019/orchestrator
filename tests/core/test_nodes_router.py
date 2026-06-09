"""Unit tests for BaseRouter and RouterNode in app/core/nodes/router.py."""

import pytest

from core.nodes.base import Node
from core.nodes.router import BaseRouter, RouterNode
from core.task import TaskContext


# ---------------------------------------------------------------------------
# Stub helpers — minimal Node subclasses (satisfy the ABC only)
# ---------------------------------------------------------------------------


class StubNodeAlpha(Node):
    """Minimal stub node Alpha — records its own execution in task_context."""

    def process(self, task_context: TaskContext) -> TaskContext:
        task_context.update_node("StubNodeAlpha", ran=True)
        return task_context


class StubNodeBeta(Node):
    """Minimal stub node Beta — records its own execution in task_context."""

    def process(self, task_context: TaskContext) -> TaskContext:
        task_context.update_node("StubNodeBeta", ran=True)
        return task_context


class StubNodeGamma(Node):
    """Minimal stub node Gamma — records its own execution in task_context."""

    def process(self, task_context: TaskContext) -> TaskContext:
        task_context.update_node("StubNodeGamma", ran=True)
        return task_context


# ---------------------------------------------------------------------------
# Stub RouterNode implementations
# ---------------------------------------------------------------------------


class AlwaysMatchRouterNode(RouterNode):
    """RouterNode that always returns a fixed target node (unconditional match)."""

    def __init__(self, target: Node):
        self._target = target

    def determine_next_node(self, task_context: TaskContext) -> Node | None:
        return self._target


class NeverMatchRouterNode(RouterNode):
    """RouterNode that always returns None (no match)."""

    def determine_next_node(self, task_context: TaskContext) -> Node | None:
        return None


class MissingNodeRouterNode(RouterNode):
    """RouterNode that calls get_node_output('Missing') — raises KeyError."""

    def determine_next_node(self, task_context: TaskContext) -> Node | None:
        # Calls get_node_output for a node that has not run — always raises KeyError.
        task_context.get_node_output("Missing")
        return None  # unreachable, but satisfies the return type


# ---------------------------------------------------------------------------
# Stub BaseRouter implementations
# ---------------------------------------------------------------------------


class SingleMatchRouter(BaseRouter):
    """Router with exactly one always-matching route and no fallback."""

    def __init__(self, target: Node):
        self.routes = [AlwaysMatchRouterNode(target)]
        self.fallback = None


class NoMatchNoFallbackRouter(BaseRouter):
    """Router with one never-matching route and no fallback configured."""

    def __init__(self):
        self.routes = [NeverMatchRouterNode()]
        self.fallback = None


class NoMatchWithFallbackRouter(BaseRouter):
    """Router with one never-matching route and a configured fallback node."""

    def __init__(self, fallback_node: Node):
        self.routes = [NeverMatchRouterNode()]
        self.fallback = fallback_node


class FirstMatchWinsRouter(BaseRouter):
    """Router with two always-matching routes; the first should always win."""

    def __init__(self, first: Node, second: Node):
        self.routes = [
            AlwaysMatchRouterNode(first),
            AlwaysMatchRouterNode(second),
        ]
        self.fallback = None


class SkipThenMatchRouter(BaseRouter):
    """Router: first route returns None; second route always matches."""

    def __init__(self, target: Node):
        self.routes = [NeverMatchRouterNode(), AlwaysMatchRouterNode(target)]
        self.fallback = None


class KeyErrorRouter(BaseRouter):
    """Router whose only route raises KeyError via get_node_output('Missing')."""

    def __init__(self):
        self.routes = [MissingNodeRouterNode()]
        self.fallback = None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def empty_context():
    """TaskContext with no nodes recorded yet."""
    return TaskContext(event={"type": "test"})


@pytest.fixture()
def alpha_node():
    return StubNodeAlpha()


@pytest.fixture()
def beta_node():
    return StubNodeBeta()


@pytest.fixture()
def gamma_node():
    return StubNodeGamma()


# ---------------------------------------------------------------------------
# Tests: BaseRouter.process()
# ---------------------------------------------------------------------------


class TestBaseRouterProcess:
    """Verify that process() invokes route() and records the result in task_context."""

    def test_process_writes_next_node_key_to_task_context(
        self, alpha_node, empty_context
    ):
        """process() stores an entry under the router's class name in task_context.nodes."""
        router = SingleMatchRouter(alpha_node)
        router.process(empty_context)
        assert "SingleMatchRouter" in empty_context.nodes

    def test_process_records_next_node_name(self, alpha_node, empty_context):
        """process() stores {'next_node': <target name>} under the router's name."""
        router = SingleMatchRouter(alpha_node)
        router.process(empty_context)
        assert empty_context.nodes["SingleMatchRouter"] == {"next_node": "StubNodeAlpha"}

    def test_process_returns_same_task_context(self, alpha_node, empty_context):
        """process() returns the exact same task_context object it received."""
        router = SingleMatchRouter(alpha_node)
        result = router.process(empty_context)
        assert result is empty_context

    def test_process_records_correct_target_class_name(self, beta_node, empty_context):
        """process() uses the target node's own class name, not the router's name."""
        router = SingleMatchRouter(beta_node)
        router.process(empty_context)
        assert empty_context.nodes["SingleMatchRouter"]["next_node"] == "StubNodeBeta"

    def test_process_uses_router_class_name_as_context_key(
        self, alpha_node, empty_context
    ):
        """The key written to task_context.nodes is the router's own class name."""
        router = SingleMatchRouter(alpha_node)
        router.process(empty_context)
        # Key must be the router's class name, not the target's name
        assert "SingleMatchRouter" in empty_context.nodes
        assert "StubNodeAlpha" not in empty_context.nodes


# ---------------------------------------------------------------------------
# Tests: BaseRouter.route() — first-match wins
# ---------------------------------------------------------------------------


class TestBaseRouterRouteFirstMatchWins:
    """Verify that route() returns the first matching RouterNode's result."""

    def test_first_route_result_returned_when_both_match(
        self, alpha_node, beta_node, empty_context
    ):
        """When two routes both match, route() returns the first route's node."""
        router = FirstMatchWinsRouter(alpha_node, beta_node)
        result = router.route(empty_context)
        assert result is alpha_node

    def test_second_route_node_not_returned_when_first_matches(
        self, alpha_node, beta_node, empty_context
    ):
        """When the first route matches, the second route's node is NOT returned."""
        router = FirstMatchWinsRouter(alpha_node, beta_node)
        result = router.route(empty_context)
        assert result is not beta_node

    def test_first_match_wins_regardless_of_fallback(
        self, alpha_node, beta_node, gamma_node, empty_context
    ):
        """The fallback is not used when the first route matches."""

        class FirstMatchWithFallbackRouter(BaseRouter):
            def __init__(self):
                self.routes = [
                    AlwaysMatchRouterNode(alpha_node),
                    AlwaysMatchRouterNode(beta_node),
                ]
                self.fallback = gamma_node

        router = FirstMatchWithFallbackRouter()
        result = router.route(empty_context)
        assert result is alpha_node
        assert result is not gamma_node


# ---------------------------------------------------------------------------
# Tests: BaseRouter.route() — fallback
# ---------------------------------------------------------------------------


class TestBaseRouterRouteFallback:
    """Verify that route() uses the fallback node when no route matches."""

    def test_fallback_returned_when_no_routes_match(self, gamma_node, empty_context):
        """When no route matches, route() returns the configured fallback node."""
        router = NoMatchWithFallbackRouter(gamma_node)
        result = router.route(empty_context)
        assert result is gamma_node

    def test_fallback_is_the_exact_instance_set_on_router(
        self, gamma_node, empty_context
    ):
        """The returned fallback is the exact object assigned to router.fallback."""
        router = NoMatchWithFallbackRouter(gamma_node)
        result = router.route(empty_context)
        assert result is gamma_node

    def test_fallback_not_used_when_route_matches(
        self, alpha_node, gamma_node, empty_context
    ):
        """When a route matches, the fallback is not returned."""

        class MatchingRouterWithFallback(BaseRouter):
            def __init__(self):
                self.routes = [AlwaysMatchRouterNode(alpha_node)]
                self.fallback = gamma_node

        router = MatchingRouterWithFallback()
        result = router.route(empty_context)
        assert result is alpha_node
        assert result is not gamma_node


# ---------------------------------------------------------------------------
# Tests: BaseRouter.route() — no fallback, no match
# ---------------------------------------------------------------------------


class TestBaseRouterRouteNoFallbackNoMatch:
    """Verify that route() returns None when no route matches and fallback is unset."""

    def test_returns_none_when_no_routes_match_and_no_fallback(self, empty_context):
        """route() returns None when no RouterNode matches and fallback is None."""
        router = NoMatchNoFallbackRouter()
        result = router.route(empty_context)
        assert result is None

    def test_empty_routes_list_and_no_fallback_returns_none(self, empty_context):
        """route() returns None when routes list is empty and fallback is None."""

        class EmptyRoutesRouter(BaseRouter):
            def __init__(self):
                self.routes = []
                self.fallback = None

        router = EmptyRoutesRouter()
        result = router.route(empty_context)
        assert result is None


# ---------------------------------------------------------------------------
# Tests: RouterNode.determine_next_node() returns None — route() skips it
# ---------------------------------------------------------------------------


class TestBaseRouterRouteSkipsNoneReturn:
    """Verify route() skips RouterNodes that return None and continues to the next."""

    def test_skips_none_returning_route_and_uses_next_match(
        self, alpha_node, empty_context
    ):
        """When first route returns None, route() tries the second route."""
        router = SkipThenMatchRouter(alpha_node)
        result = router.route(empty_context)
        assert result is alpha_node

    def test_result_is_not_none_when_later_route_matches(
        self, alpha_node, empty_context
    ):
        """route() does not return None when a later route successfully matches."""
        router = SkipThenMatchRouter(alpha_node)
        result = router.route(empty_context)
        assert result is not None

    def test_multiple_skips_before_final_match(
        self, alpha_node, empty_context
    ):
        """route() evaluates all routes until a match is found."""

        class MultiSkipRouter(BaseRouter):
            def __init__(self):
                self.routes = [
                    NeverMatchRouterNode(),
                    NeverMatchRouterNode(),
                    NeverMatchRouterNode(),
                    AlwaysMatchRouterNode(alpha_node),
                ]
                self.fallback = None

        router = MultiSkipRouter()
        result = router.route(empty_context)
        assert result is alpha_node

    def test_all_none_with_fallback_uses_fallback(
        self, gamma_node, empty_context
    ):
        """When all routes return None, route() uses the fallback."""

        class AllNoneWithFallback(BaseRouter):
            def __init__(self):
                self.routes = [NeverMatchRouterNode(), NeverMatchRouterNode()]
                self.fallback = gamma_node

        router = AllNoneWithFallback()
        result = router.route(empty_context)
        assert result is gamma_node


# ---------------------------------------------------------------------------
# Tests: KeyError propagation from RouterNode.determine_next_node()
# ---------------------------------------------------------------------------


class TestBaseRouterRouteKeyErrorPropagates:
    """Verify that KeyError from get_node_output propagates out of route()."""

    def test_key_error_propagates_out_of_route(self, empty_context):
        """A RouterNode calling get_node_output('Missing') causes route() to raise KeyError."""
        router = KeyErrorRouter()
        with pytest.raises(KeyError):
            router.route(empty_context)

    def test_key_error_message_names_missing_node(self, empty_context):
        """The propagated KeyError message names the missing node ('Missing')."""
        router = KeyErrorRouter()
        with pytest.raises(KeyError, match="Missing"):
            router.route(empty_context)

    def test_key_error_is_not_swallowed_by_route(self, empty_context):
        """route() does not catch or suppress KeyError — it propagates to the caller."""
        router = KeyErrorRouter()
        raised = False
        try:
            router.route(empty_context)
        except KeyError:
            raised = True
        assert raised, "KeyError must propagate out of route(), not be swallowed"

    def test_key_error_message_references_workflow_schema(self, empty_context):
        """KeyError message hints at WorkflowSchema ordering as the fix."""
        router = KeyErrorRouter()
        with pytest.raises(KeyError, match="WorkflowSchema"):
            router.route(empty_context)

    def test_key_error_message_lists_available_nodes(self, empty_context):
        """KeyError message lists nodes that have completed so far."""
        # empty_context has no completed nodes, so the list should be empty
        router = KeyErrorRouter()
        with pytest.raises(KeyError, match=r"\[\]"):
            router.route(empty_context)

    def test_key_error_shows_available_nodes_when_some_have_run(self, empty_context):
        """KeyError message includes nodes that ran before the router."""
        empty_context.update_node("PriorNode", result="done")
        router = KeyErrorRouter()
        with pytest.raises(KeyError, match="PriorNode"):
            router.route(empty_context)
