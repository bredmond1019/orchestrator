import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import boto3
from dotenv import load_dotenv
from httpx import AsyncClient
from openai import AsyncAzureOpenAI
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelName
from pydantic_ai.models.bedrock import BedrockConverseModel, BedrockModelName
from pydantic_ai.models.gemini import GeminiModel, GeminiModelName
from pydantic_ai.models.openai import OpenAIModel, OpenAIModelName
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.bedrock import BedrockProvider
from pydantic_ai.providers.google_gla import GoogleGLAProvider
from pydantic_ai.providers.openai import OpenAIProvider

from core.nodes.base import Node
from core.task import TaskContext, to_jsonable

load_dotenv()


class ModelProvider(StrEnum):
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    BEDROCK = "bedrock"


@dataclass
class AgentConfig:
    system_prompt: str
    output_type: type[Any] | None
    deps_type: type[Any] | None
    model_provider: ModelProvider
    model_name: OpenAIModelName | AnthropicModelName | GeminiModelName | BedrockModelName


class AgentNode(Node, ABC):
    class DepsType(BaseModel):
        pass

    class OutputType(BaseModel):
        pass

    def __init__(self):
        self.__async_client = AsyncClient()
        agent_wrapper = self.get_agent_config()
        self.agent = Agent(
            system_prompt=agent_wrapper.system_prompt,
            output_type=agent_wrapper.output_type,
            model=self.__get_model_instance(
                agent_wrapper.model_provider, agent_wrapper.model_name
            ),
        )

    def run_agent_recorded(self, task_context: TaskContext, user_prompt: str):
        """Run the agent and record per-node telemetry for this node.

        New AgentNode subclasses should call this instead of
        ``self.agent.run_sync`` so per-node observability is captured by the
        framework in one place. The base class cannot intercept direct
        ``self.agent.run_sync(...)`` calls a subclass makes, so this helper
        runs the agent and records, per the data contract:

        - ``NodeRun.input`` — the ``user_prompt`` sent to the model.
        - ``NodeRun.usage`` — ``{input_tokens, output_tokens, model}``.
        - ``TaskContext.nodes[node_name]["output"]`` — the JSON-serializable
          model output (``result.output``), so a consumer can read it without
          the raw SDK result object.

        Telemetry is only stamped when a ``NodeRun`` exists for this node; the
        result is always returned unchanged so existing subclasses that read
        ``result.output`` keep working.

        The ``getattr`` fallback covers both newer pydantic-ai
        (``input_tokens``/``output_tokens``) and the pinned ``>=0.1.5`` line
        (``request_tokens``/``response_tokens``).
        """
        result = self.agent.run_sync(user_prompt=user_prompt)
        usage = result.usage()
        run = task_context.node_runs.get(self.node_name)
        if run is not None:
            run.input = user_prompt
            run.usage = {
                "input_tokens": getattr(usage, "input_tokens", None)
                or getattr(usage, "request_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None)
                or getattr(usage, "response_tokens", None),
                "model": self.get_agent_config().model_name,
            }
            task_context.update_node(
                self.node_name, output=to_jsonable(result.output)
            )
        return result

    @abstractmethod
    def get_agent_config(self) -> AgentConfig:
        pass

    @abstractmethod
    def process(self, task_context: TaskContext) -> TaskContext:
        pass

    def __get_model_instance(self, provider: ModelProvider, model_name: str) -> Model:
        match provider.value:
            case provider.OPENAI.value:
                return self.__get_openai_model(model_name)
            case provider.AZURE_OPENAI.value:
                return self.__get_azure_openai_model(model_name)
            case provider.ANTHROPIC.value:
                return self.__get_anthropic_model(model_name)
            case provider.GEMINI.value:
                return self.__get_gemini_model(model_name)
            case provider.OLLAMA.value:
                return self.__get_ollama_model(model_name)
            case provider.BEDROCK.value:
                return self.__get_bedrock_model(model_name)
            case _:
                return self.__get_openai_model("gpt-4.1")

    def __get_openai_model(self, model_name: OpenAIModelName) -> Model:
        return OpenAIModel(
            model_name,
            provider=OpenAIProvider(http_client=self.__async_client),
        )

    def __get_azure_openai_model(self, model_name: OpenAIModelName) -> Model:
        client = AsyncAzureOpenAI()
        return OpenAIModel(
            model_name,
            provider=OpenAIProvider(openai_client=client),
        )

    def __get_anthropic_model(self, model_name: AnthropicModelName) -> Model:
        return AnthropicModel(
            model_name=model_name,
            provider=AnthropicProvider(http_client=self.__async_client),
        )

    def __get_gemini_model(self, model_name: str) -> Model:
        return GeminiModel(
            model_name=model_name,
            provider=GoogleGLAProvider(http_client=self.__async_client),
        )

    def __get_ollama_model(self, model_name: str) -> Model:
        base_url = os.getenv("OLLAMA_BASE_URL")
        if not base_url:
            raise KeyError("OLLAMA_BASE_URL not set in .env")

        return OpenAIModel(
            model_name=model_name, provider=OpenAIProvider(base_url=base_url)
        )

    def __get_bedrock_model(self, model_name: str) -> Model:
        aws_access_key_id = os.getenv("BEDROCK_AWS_ACCESS_KEY_ID")
        aws_secret_access_key = os.getenv("BEDROCK_AWS_SECRET_ACCESS_KEY")
        aws_region = os.getenv("BEDROCK_AWS_REGION")

        bedrock_client = boto3.client(
            "bedrock-runtime",
            region_name=aws_region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )
        return BedrockConverseModel(
            model_name=model_name,
            provider=BedrockProvider(bedrock_client=bedrock_client),
        )
