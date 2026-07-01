"""Unit tests for ParallelNode in app/core/nodes/parallel.py."""

import threading
import time

import pytest

from core.nodes.base import Node
from core.nodes.parallel import ParallelNode
from core.schema import NodeConfig
from core.task import TaskContext


# ---------------------------------------------------------------------------
# Helpers — stub nodes used across multiple tests
# ---------------------------------------------------------------------------


class _WriteAlphaNode(Node):
    """Writes {"ran": True} under key "Alpha" in task_context.nodes."""

    def process(self, task_context: TaskContext) -> TaskContext:
        task_context.update_node("Alpha", ran=True)
        return task_context


class _WriteBetaNode(Node):
    """Writes {"ran": True} under key "Beta" in task_context.nodes."""

    def process(self, task_context: TaskContext) -> TaskContext:
        task_context.update_node("Beta", ran=True)
        return task_context


class _WriteGammaNode(Node):
    """Writes {"ran": True} under key "Gamma" in task_context.nodes."""

    def process(self, task_context: TaskContext) -> TaskContext:
        task_context.update_node("Gamma", ran=True)
        return task_context


class _RaisingNode(Node):
    """Always raises RuntimeError when processed."""

    def process(self, task_context: TaskContext) -> TaskContext:
        raise RuntimeError("intentional failure in parallel node")


# ---------------------------------------------------------------------------
# Concrete ParallelNode subclasses for tests
# (one per distinct parallel_nodes list so metadata keys stay unique)
# ---------------------------------------------------------------------------


class _AllThreeParallelNode(ParallelNode):
    """Runs Alpha, Beta, Gamma in parallel."""

    def process(self, task_context: TaskContext) -> TaskContext:
        self.execute_nodes_in_parallel(task_context)
        return task_context


class _ConcurrentParallelNode(ParallelNode):
    """Used by the concurrency overlap test."""

    def process(self, task_context: TaskContext) -> TaskContext:
        self.execute_nodes_in_parallel(task_context)
        return task_context


class _RaisingParallelNode(ParallelNode):
    """Runs one well-behaved node plus one that raises."""

    def process(self, task_context: TaskContext) -> TaskContext:
        self.execute_nodes_in_parallel(task_context)
        return task_context


class _DiscardResultsParallelNode(ParallelNode):
    """Used to document that the results list is discarded."""

    def process(self, task_context: TaskContext) -> TaskContext:
        self.execute_nodes_in_parallel(task_context)
        return task_context


# ---------------------------------------------------------------------------
# Helper to build a TaskContext wired for a specific ParallelNode class
# ---------------------------------------------------------------------------


def _make_context(parallel_node_class: type, parallel_nodes: list) -> TaskContext:
    """Return a TaskContext whose metadata is set up for execute_nodes_in_parallel."""
    node_config = NodeConfig(
        node=parallel_node_class,
        parallel_nodes=parallel_nodes,
    )
    ctx = TaskContext(
        event={"type": "test"},
        metadata={"nodes": {parallel_node_class: node_config}},
    )
    return ctx


# ---------------------------------------------------------------------------
# 1. All parallel nodes run
# ---------------------------------------------------------------------------


class TestAllNodesRun:
    def test_all_three_nodes_write_their_keys(self):
        """After execute_nodes_in_parallel, every parallel node's key is present."""
        ctx = _make_context(
            _AllThreeParallelNode,
            [_WriteAlphaNode, _WriteBetaNode, _WriteGammaNode],
        )
        node = _AllThreeParallelNode()
        node.process(ctx)

        assert "Alpha" in ctx.nodes
        assert "Beta" in ctx.nodes
        assert "Gamma" in ctx.nodes

    def test_each_node_writes_correct_value(self):
        """Each parallel node writes the exact value it was designed to produce."""
        ctx = _make_context(
            _AllThreeParallelNode,
            [_WriteAlphaNode, _WriteBetaNode, _WriteGammaNode],
        )
        node = _AllThreeParallelNode()
        node.process(ctx)

        assert ctx.nodes["Alpha"] == {"ran": True}
        assert ctx.nodes["Beta"] == {"ran": True}
        assert ctx.nodes["Gamma"] == {"ran": True}

    def test_single_parallel_node_runs(self):
        """A ParallelNode with only one sub-node still executes that node."""
        ctx = _make_context(_AllThreeParallelNode, [_WriteAlphaNode])
        # Reuse _AllThreeParallelNode class pointing at single node
        node_config = NodeConfig(
            node=_AllThreeParallelNode,
            parallel_nodes=[_WriteAlphaNode],
        )
        ctx = TaskContext(
            event={"type": "test"},
            metadata={"nodes": {_AllThreeParallelNode: node_config}},
        )
        node = _AllThreeParallelNode()
        node.process(ctx)
        assert ctx.nodes["Alpha"] == {"ran": True}

    def test_empty_parallel_nodes_list_runs_cleanly(self):
        """A ParallelNode with no sub-nodes returns without error."""
        ctx = _make_context(_AllThreeParallelNode, [])
        node = _AllThreeParallelNode()
        result = node.process(ctx)
        assert result is ctx


# ---------------------------------------------------------------------------
# 2. Parallel execution is actually concurrent
# ---------------------------------------------------------------------------


def _make_barrier_node(
    barrier: threading.Barrier,
    starts: list,
    ends: list,
    key: str,
) -> type[Node]:
    """Factory that builds a distinct Node subclass with shared state."""

    class _BarrierNode(Node):
        def process(self, task_context: TaskContext) -> TaskContext:
            starts.append(time.monotonic())
            barrier.wait(timeout=5)
            ends.append(time.monotonic())
            task_context.update_node(key, ran=True)
            return task_context

    _BarrierNode.__name__ = f"_BarrierNode_{key}"
    _BarrierNode.__qualname__ = f"_BarrierNode_{key}"
    return _BarrierNode


class TestConcurrentExecution:
    def test_nodes_overlap_in_time(self):
        """
        Verify that two parallel nodes actually execute concurrently.

        Strategy: use a threading.Barrier(2).  Each node records its start,
        then blocks at the barrier.  The barrier only releases when *both*
        nodes have arrived — which is only possible if they are running
        simultaneously.  If execution were sequential the second node would
        never arrive while the first was still blocked, causing a timeout.
        """
        barrier = threading.Barrier(2)
        starts: list[float] = []
        ends: list[float] = []

        NodeX = _make_barrier_node(barrier, starts, ends, "X")
        NodeY = _make_barrier_node(barrier, starts, ends, "Y")

        node_config = NodeConfig(
            node=_ConcurrentParallelNode,
            parallel_nodes=[NodeX, NodeY],
        )
        ctx = TaskContext(
            event={"type": "test"},
            metadata={"nodes": {_ConcurrentParallelNode: node_config}},
        )

        node = _ConcurrentParallelNode()
        # If execution were serial the barrier.wait(timeout=5) would deadlock;
        # the test would fail with BrokenBarrierError — not a false positive.
        node.process(ctx)

        # Both nodes ran
        assert ctx.nodes["X"] == {"ran": True}
        assert ctx.nodes["Y"] == {"ran": True}
        # Both recorded start and end times
        assert len(starts) == 2
        assert len(ends) == 2

    def test_all_nodes_complete_before_execute_returns(self):
        """execute_nodes_in_parallel waits for all futures before returning."""
        completed: list[str] = []

        def _make_recording_node(key: str) -> type[Node]:
            class _RecNode(Node):
                def process(self, task_context: TaskContext) -> TaskContext:
                    time.sleep(0.05)
                    completed.append(key)
                    task_context.update_node(key, ran=True)
                    return task_context

            _RecNode.__name__ = f"_RecNode_{key}"
            return _RecNode

        NodeA = _make_recording_node("A")
        NodeB = _make_recording_node("B")
        NodeC = _make_recording_node("C")

        node_config = NodeConfig(
            node=_ConcurrentParallelNode,
            parallel_nodes=[NodeA, NodeB, NodeC],
        )
        ctx = TaskContext(
            event={"type": "test"},
            metadata={"nodes": {_ConcurrentParallelNode: node_config}},
        )

        node = _ConcurrentParallelNode()
        node.process(ctx)

        # All three must have finished before process() returned
        assert set(completed) == {"A", "B", "C"}


# ---------------------------------------------------------------------------
# 3. Exception propagates from a parallel node
# ---------------------------------------------------------------------------


class TestExceptionPropagates:
    def test_raising_node_propagates_runtime_error(self):
        """An exception raised inside a parallel node propagates out of execute_nodes_in_parallel."""
        ctx = _make_context(_RaisingParallelNode, [_RaisingNode])
        node = _RaisingParallelNode()

        with pytest.raises(RuntimeError, match="intentional failure in parallel node"):
            node.process(ctx)

    def test_exception_propagates_even_when_other_node_succeeds(self):
        """If one parallel node raises, the exception still propagates even if another succeeded."""
        ctx = _make_context(
            _RaisingParallelNode,
            [_WriteAlphaNode, _RaisingNode],
        )
        node = _RaisingParallelNode()

        with pytest.raises(RuntimeError, match="intentional failure"):
            node.process(ctx)


# ---------------------------------------------------------------------------
# 4. Merging isolated contexts (Project E fix)
# ---------------------------------------------------------------------------


class _ReturnsValueNode(Node):
    """Returns a meaningful value from process(); used to test results handling."""

    def process(self, task_context: TaskContext) -> TaskContext:
        task_context.update_node("ValueNode", result=42)
        return task_context


class _ModifyEventNode(Node):
    """Modifies the event to prove isolation; the change should not leak back."""
    
    def process(self, task_context: TaskContext) -> TaskContext:
        if isinstance(task_context.event, dict):
            task_context.event["modified"] = True
        return task_context


class TestMergeBehavior:
    def test_execute_nodes_in_parallel_merges_isolated_contexts(self):
        """
        execute_nodes_in_parallel returns a list of futures' results,
        and aggregates the results back into the main context's nodes dictionary.
        """
        node_config = NodeConfig(
            node=_DiscardResultsParallelNode,
            parallel_nodes=[_ReturnsValueNode],
        )
        ctx = TaskContext(
            event={"type": "test"},
            metadata={"nodes": {_DiscardResultsParallelNode: node_config}},
        )

        node = _DiscardResultsParallelNode()
        results = node.execute_nodes_in_parallel(ctx)

        # The list of isolated contexts is returned
        assert isinstance(results, list)
        assert len(results) == 1

        # The main task_context now has the successfully merged output
        assert ctx.nodes["ValueNode"] == {"result": 42}

    def test_task_context_is_isolated_per_thread(self):
        """
        Parallel nodes operate on deep copies of TaskContext.
        Mutations (e.g. to event) do not leak back to the main context,
        only nodes and node_runs are explicitly merged.
        """
        node_config = NodeConfig(
            node=_ConcurrentParallelNode,
            parallel_nodes=[_ModifyEventNode, _WriteAlphaNode],
        )
        ctx = TaskContext(
            event={"original": True},
            metadata={"nodes": {_ConcurrentParallelNode: node_config}},
        )
        node = _ConcurrentParallelNode()
        node.execute_nodes_in_parallel(ctx)
        
        # The main context event shouldn't be touched by the parallel threads
        assert ctx.event.get("modified") is None
        # The explicit output (nodes) should still be merged
        assert ctx.nodes["Alpha"] == {"ran": True}
