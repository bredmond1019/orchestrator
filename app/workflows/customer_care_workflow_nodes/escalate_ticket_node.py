import logging

from core.nodes.base import Node
from core.task import TaskContext


class EscalateTicketNode(Node):
    def process(self, task_context: TaskContext) -> TaskContext:
        logging.info("Escalating ticket")
        return task_context
