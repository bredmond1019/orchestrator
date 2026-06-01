import logging

from core.nodes.base import Node
from core.task import TaskContext
from workflows.customer_care_workflow_nodes.generate_response_node import (
    GenerateResponseNode,
)


class SendReplyNode(Node):
    def process(self, task_context: TaskContext) -> TaskContext:
        logging.info("Sending reply:")
        output: GenerateResponseNode.OutputType = task_context.nodes[
            "GenerateResponseNode"
        ]["result"].output
        logging.info(output.response)
        return task_context
