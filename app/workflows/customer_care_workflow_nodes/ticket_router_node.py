from typing import Optional

from core.nodes.base import Node
from core.nodes.router import BaseRouter, RouterNode
from core.task import TaskContext
from workflows.customer_care_workflow_nodes.close_ticket_node import CloseTicketNode
from workflows.customer_care_workflow_nodes.determine_intent_ticket_node import (
    CustomerIntent,
)
from workflows.customer_care_workflow_nodes.escalate_ticket_node import (
    EscalateTicketNode,
)
from workflows.customer_care_workflow_nodes.filter_spam import FilterSpamNode
from workflows.customer_care_workflow_nodes.generate_response_node import (
    GenerateResponseNode,
)
from workflows.customer_care_workflow_nodes.process_invoice_node import (
    ProcessInvoiceNode,
)


class TicketRouterNode(BaseRouter):
    def __init__(self):
        self.routes = [
            CloseTicketRouter(),
            EscalationRouter(),
            InvoiceRouter(),
        ]
        self.fallback = GenerateResponseNode()


class CloseTicketRouter(RouterNode):
    def determine_next_node(self, task_context: TaskContext) -> Optional[Node]:
        output: FilterSpamNode.OutputType = task_context.nodes["FilterSpamNode"][
            "result"
        ].output
        if not output.is_human and output.confidence > 0.8:
            return CloseTicketNode()
        return None


class EscalationRouter(RouterNode):
    def determine_next_node(self, task_context: TaskContext) -> Optional[Node]:
        analysis = task_context.nodes["DetermineTicketIntentNode"]["result"].output
        if analysis.intent.escalate or analysis.escalate:
            return EscalateTicketNode()
        return None


class InvoiceRouter(RouterNode):
    def determine_next_node(self, task_context: TaskContext) -> Optional[Node]:
        analysis = task_context.nodes["DetermineTicketIntentNode"]["result"].output
        if analysis.intent == CustomerIntent.BILLING_INVOICE:
            return ProcessInvoiceNode()
        return None
