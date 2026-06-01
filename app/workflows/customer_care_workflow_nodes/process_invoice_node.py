import logging

from core.nodes.base import Node
from core.task import TaskContext


class ProcessInvoiceNode(Node):
    def process(self, task_context: TaskContext) -> TaskContext:
        logging.info("Processing invoice")
        return task_context
