"""
Router Module

This module implements the routing logic for workflow nodes.
It provides base classes for implementing routing decisions between nodes
in a processing workflow.
"""

from abc import ABC, abstractmethod

from core.nodes.base import Node
from core.task import TaskContext


class BaseRouter(Node):
    """Base router class for implementing node routing logic.

    The BaseRouter class provides core routing functionality for directing
    task flow between workflow nodes. It processes routing rules in sequence
    and falls back to a default node if no rules match.

    Attributes:
        routes: List of RouterNode instances defining routing rules
        fallback: Optional default node to route to if no rules match
    """

    def process(self, task_context: TaskContext) -> TaskContext:
        """Processes the routing logic and updates task context.

        Uses ``TaskContext.update_node`` (a merge) rather than a direct
        ``task_context.nodes[self.node_name] = ...`` assignment, so that a
        ``RouterNode.determine_next_node`` which stashes its own data on the
        router's node name via ``update_node`` (e.g. ``TaskQueueRouterNode``
        recording the dispatched task's fields under its own ``result`` key)
        is preserved alongside the routing decision, instead of being wiped
        out by this method running after ``route()``.

        Args:
            task_context: Current task execution context

        Returns:
            Updated TaskContext with routing decision recorded
        """
        next_node = self.route(task_context)
        task_context.update_node(
            node_name=self.node_name,
            next_node=next_node.node_name if next_node else None,
        )
        return task_context

    def route(self, task_context: TaskContext) -> Node:
        """Determines the next node based on routing rules.

        Evaluates each routing rule in sequence and returns the first
        matching node. Falls back to the default node if no rules match.

        Args:
            task_context: Current task execution context

        Returns:
            The next node to execute, or None if no route is found
        """
        for route_node in self.routes:  # pylint: disable=no-member
            next_node = route_node.determine_next_node(task_context)
            if next_node:
                return next_node
        return self.fallback if self.fallback else None  # pylint: disable=no-member


class RouterNode(ABC):
    @abstractmethod
    def determine_next_node(self, task_context: TaskContext) -> Node | None:
        pass

    @property
    def node_name(self):
        return self.__class__.__name__
