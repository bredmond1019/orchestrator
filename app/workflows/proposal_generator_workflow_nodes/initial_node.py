"""Scaffold placeholder node for the proposal_generator workflow.

This module is a temporary stub created at scaffold time. Task 7 replaces
this with the real DAG (CompanyResearchNode as start node). After Task 7
lands, this file should be removed and is expected to be non-importable
by the integration test.
"""

from core.nodes.base import Node
from core.task import TaskContext


class InitialNode(Node):
    """Temporary scaffold node — replaced in Task 7 when the DAG is wired."""

    def process(self, task_context: TaskContext) -> TaskContext:
        """Placeholder: passes context through unchanged."""
        return task_context
