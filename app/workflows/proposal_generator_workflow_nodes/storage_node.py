"""StorageNode stub for the proposal_generator workflow.

Persistence logic is implemented in Task 6 (``BrainDocument`` + embedding via
``GenericRepository``). This stub exists so ``ProposalReviewRouterNode`` can
import the class by name; the real implementation replaces this file in Task 6.

Do NOT add business logic here — Task 6 owns this file.
"""

from core.nodes.base import Node
from core.task import TaskContext


class StorageNode(Node):
    """Stub — persistence implemented in Task 6."""

    def process(self, task_context: TaskContext) -> TaskContext:
        """Placeholder: passes context through unchanged until Task 6 fills this."""
        return task_context
