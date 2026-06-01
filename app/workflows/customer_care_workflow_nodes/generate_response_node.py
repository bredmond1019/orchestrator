from pydantic import Field

from core.nodes.agent import AgentNode, AgentConfig, ModelProvider
from core.task import TaskContext
from schemas.customer_care_schema import CustomerCareEventSchema
from services.prompt_loader import PromptManager


class GenerateResponseNode(AgentNode):
    class OutputType(AgentNode.OutputType):
        reasoning: str = Field(description="The reasoning for the response")
        response: str = Field(description="The response to the ticket")
        confidence: float = Field(
            ge=0, le=1, description="Confidence score for how helpful the response is"
        )

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt=PromptManager().get_prompt("customer_ticket_response"),
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
