from pydantic import Field

from core.nodes.agent import AgentNode, AgentConfig, ModelProvider
from core.task import TaskContext
from schemas.customer_care_schema import CustomerCareEventSchema


class ValidateTicketNode(AgentNode):
    class OutputType(AgentNode.OutputType):
        reasoning: str = Field(
            description="Explain your reasoning for determining whether the ticket contains enough information for customer care to take action."
        )
        confidence: float = Field(
            ge=0,
            le=1,
            description="Confidence score for whether the ticket is actionable by customer care.",
        )
        is_actionable: bool = Field(
            description="Set to True if the ticket contains enough information for customer care to take action; False otherwise."
        )

    def get_agent_config(self) -> AgentConfig:
        system_prompt = (
            "You are a helpful assistant that reviews customer care tickets to determine whether they contain enough information for a customer care employee to take action. "
            "Consider factors such as the presence of identifying details, a clear description of the issue, and any necessary context. "
            "If the ticket is missing critical information, it is not actionable."
        )
        return AgentConfig(
            system_prompt=system_prompt,
            output_type=self.OutputType,
            deps_type=None,
            model_provider=ModelProvider.OPENAI,
            model_name="gpt-4o",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        event: CustomerCareEventSchema = task_context.event
        result = self.agent.run_sync(
            user_prompt=event.model_dump_json(),
        )
        task_context.update_node(node_name=self.node_name, result=result)
        return task_context
