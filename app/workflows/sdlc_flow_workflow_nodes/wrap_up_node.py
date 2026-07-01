"""WrapUpNode — forward declaration for the ``TriageRouterNode`` MAJOR_BAIL route.

Task 7 (``TriageRouterNode``) routes a ``MAJOR_BAIL`` verdict to this node, so
the class must exist for the router to import. The full wrap-up
implementation (editing ``planning/status.md``, prepending a dated summary to
``log.md``, generating a markdown report under ``reports/``) is built out in
Task 8 of ``planning/sdlc-workflow-architecture/tasks.md`` — this is
intentionally a minimal placeholder, not the completed node.
"""

from core.nodes.base import Node
from core.task import TaskContext


class WrapUpNode(Node):
    """Placeholder for the Task 8 wrap-up node."""

    def process(self, task_context: TaskContext) -> TaskContext:
        raise NotImplementedError(
            "WrapUpNode is implemented in Task 8 of "
            "planning/sdlc-workflow-architecture/tasks.md"
        )
