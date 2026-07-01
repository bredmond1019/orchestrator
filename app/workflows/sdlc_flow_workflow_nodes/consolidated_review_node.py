"""ConsolidatedReviewNode — forward declaration for the ``TriageRouterNode`` PASS route.

Task 7 (``TriageRouterNode``) routes a ``PASS`` verdict to this node, so the
class must exist for the router to import. The full review implementation
(reading the git diff, checking it against the task's acceptance criteria,
and issuing an ``SDLCReviewVerdict``) is built out in Task 8 of
``planning/sdlc-workflow-architecture/tasks.md`` — this is intentionally a
minimal placeholder, not the completed node.
"""

from core.nodes.base import Node
from core.task import TaskContext


class ConsolidatedReviewNode(Node):
    """Placeholder for the Task 8 consolidated review node."""

    def process(self, task_context: TaskContext) -> TaskContext:
        raise NotImplementedError(
            "ConsolidatedReviewNode is implemented in Task 8 of "
            "planning/sdlc-workflow-architecture/tasks.md"
        )
