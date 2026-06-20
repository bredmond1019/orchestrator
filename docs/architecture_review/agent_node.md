---
type: Reference
title: AgentNode — How It Works
description: How AgentNode works — the LLM-calling node abstraction.
---

# AgentNode — How It Works

`app/core/nodes/agent.py`

---

## The big picture

`AgentNode` is the node type you'll use whenever you want to make an AI call inside a workflow. It wraps [pydantic-ai](https://docs.pydantic.ai/)'s `Agent` class, so you get structured output, multi-provider support, and typed dependency injection — without writing any provider-specific boilerplate yourself.

Every concrete node that calls an LLM inherits from `AgentNode`. You only have to implement two things: `get_agent_config()` (describe what agent you want) and `process()` (use it).

---

## Step 1 — The base class: `Node`

Before looking at `AgentNode`, understand what it inherits from:

```python
# app/core/nodes/base.py
class Node(ABC):
    @property
    def node_name(self) -> str:
        return self.__class__.__name__   # e.g. "FilterSpamNode"

    @abstractmethod
    def process(self, task_context: TaskContext) -> TaskContext:
        pass
```

`Node` has one concrete member — the `node_name` property, which returns `self.__class__.__name__` — and one abstract member: `process()`. Subclasses must implement `process()`; `node_name` is inherited as-is.

`AgentNode` extends `Node` and fills in the AI machinery.

---

## Step 2 — `ModelProvider` enum

```python
class ModelProvider(StrEnum):
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    BEDROCK = "bedrock"
```

This enum is how you declare *which AI provider you want* in your node config. It uses `StrEnum` (Python 3.11+), so it serialises cleanly to/from JSON and config files.

The choice lives in `AgentConfig`, never hardcoded inside a node's logic. That's the D18 injection-point discipline — the node describes what it needs; the framework wires it up.

---

## Step 3 — `AgentConfig` dataclass

```python
@dataclass
class AgentConfig:
    system_prompt: str
    output_type: Optional[Type[Any]]
    deps_type: Optional[Type[Any]]
    model_provider: ModelProvider
    model_name: Union[OpenAIModelName, AnthropicModelName, GeminiModelName, BedrockModelName]
```

A plain dataclass — no magic. When you subclass `AgentNode`, you return one of these from `get_agent_config()` to declare:

- **`system_prompt`** — the static system prompt string (or a rendered Jinja2 string from `PromptManager`).
- **`output_type`** — a Pydantic model class; pydantic-ai will force the LLM to return data that validates against it. `None` means free-form text.
- **`deps_type`** — a Pydantic model class for runtime dependencies (context injected into dynamic parts of the prompt). `None` if the prompt is fully static.
- **`model_provider`** — which provider (from the enum above).
- **`model_name`** — the specific model string, e.g. `"gpt-4o"` or `"claude-opus-4-8"`.

---

## Step 4 — `AgentNode.__init__`: where the `Agent` is built

```python
class AgentNode(Node, ABC):
    class DepsType(BaseModel):
        pass

    class OutputType(BaseModel):
        pass

    def __init__(self):
        self.__async_client = AsyncClient()          # shared HTTP client
        agent_wrapper = self.get_agent_config()      # call the subclass
        self.agent = Agent(
            system_prompt=agent_wrapper.system_prompt,
            output_type=agent_wrapper.output_type,
            model=self.__get_model_instance(
                agent_wrapper.model_provider, agent_wrapper.model_name
            ),
        )
```

When a node is instantiated, `__init__` immediately:

1. Creates a shared `AsyncClient` (used by HTTP-based providers to reuse connections).
2. Calls `self.get_agent_config()` — which is your subclass's method — to get the config.
3. Passes everything to pydantic-ai's `Agent(...)`, which is now stored as `self.agent`.

After `__init__`, `self.agent` is ready to call. New subclasses should call `self.run_agent_recorded(task_context, user_prompt)` instead of `self.agent.run_sync(...)` directly — it runs the agent and stamps per-node token usage into `NodeRun.usage` automatically (see Step 6 below).

The inner classes `DepsType` and `OutputType` are empty base Pydantic models. Subclasses extend them with real fields (see the `FilterSpamNode` example below).

> **Known side effect:** `agent.py` calls `load_dotenv()` at module level (line 25), producing a side effect at import time. `CLAUDE.md` flags this pattern as a known anti-pattern in this codebase (see the similar issues in `worker/config.py` and `database/session.py`).

---

## Step 5 — `__get_model_instance`: mapping provider → pydantic-ai model object

```python
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
            return self.__get_openai_model("gpt-4.1")   # safe default
```

This is a private routing function. It takes the provider enum and model name string, and returns the correct pydantic-ai `Model` object. Each branch calls one of six private builder methods.

### OpenAI

```python
def __get_openai_model(self, model_name: OpenAIModelName) -> Model:
    return OpenAIModel(
        model_name,
        provider=OpenAIProvider(http_client=self.__async_client),
    )
```

Standard OpenAI. Reads `OPENAI_API_KEY` from the environment automatically (via the provider). The shared `AsyncClient` is passed in to reuse the connection pool.

### Azure OpenAI

```python
def __get_azure_openai_model(self, model_name: OpenAIModelName) -> Model:
    client = AsyncAzureOpenAI()    # reads AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT from env
    return OpenAIModel(
        model_name,
        provider=OpenAIProvider(openai_client=client),
    )
```

Same `OpenAIModel` type but with an Azure-flavoured client. Azure OpenAI uses a deployment name instead of a model name, so `model_name` here is your Azure deployment name.

### Anthropic

```python
def __get_anthropic_model(self, model_name: AnthropicModelName) -> Model:
    return AnthropicModel(
        model_name=model_name,
        provider=AnthropicProvider(http_client=self.__async_client),
    )
```

Uses pydantic-ai's `AnthropicModel`. Reads `ANTHROPIC_API_KEY` from env. Pass `"claude-sonnet-4-6"` or `"claude-opus-4-8"` as `model_name`.

### Gemini

```python
def __get_gemini_model(self, model_name: str) -> Model:
    return GeminiModel(
        model_name=model_name,
        provider=GoogleGLAProvider(http_client=self.__async_client),
    )
```

Google's Gemini via the GLA (Google Generative Language API) provider.

> **Note:** `AgentConfig.model_name` is typed as `Union[OpenAIModelName, AnthropicModelName, GeminiModelName, BedrockModelName]`, importing `GeminiModelName` from `pydantic_ai.models.gemini`. However, `__get_gemini_model()` takes `model_name: str` in its actual signature. These two declarations are inconsistent; in practice any string accepted by the Gemini provider can be passed.

### Ollama (local models)

```python
def __get_ollama_model(self, model_name: str) -> Model:
    base_url = os.getenv("OLLAMA_BASE_URL")
    if not base_url:
        raise KeyError("OLLAMA_BASE_URL not set in .env")

    return OpenAIModel(
        model_name=model_name, provider=OpenAIProvider(base_url=base_url)
    )
```

Ollama exposes an OpenAI-compatible API, so this reuses `OpenAIModel` pointed at a local URL (e.g. `http://localhost:11434/v1`). If `OLLAMA_BASE_URL` is not set it raises immediately — no silent misconfiguration.

### AWS Bedrock

```python
def __get_bedrock_model(self, model_name: str) -> Model:
    bedrock_client = boto3.client(
        "bedrock-runtime",
        region_name=os.getenv("BEDROCK_AWS_REGION"),
        aws_access_key_id=os.getenv("BEDROCK_AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("BEDROCK_AWS_SECRET_ACCESS_KEY"),
    )
    return BedrockConverseModel(
        model_name=model_name,
        provider=BedrockProvider(bedrock_client=bedrock_client),
    )
```

Builds a `boto3` Bedrock runtime client from env vars, then wraps it in pydantic-ai's `BedrockConverseModel`. Model names here are ARNs or Bedrock model IDs like `"anthropic.claude-3-5-sonnet-20241022-v2:0"`.

> **Note:** the actual source extracts each `os.getenv()` call to a local variable first (`aws_access_key_id`, `aws_secret_access_key`, `aws_region`) before passing them to `boto3.client()`. The snippet above inlines them for clarity; the behavior is identical.

---

## Step 6 — Putting it together: a real subclass

Here's `FilterSpamNode` from the customer care workflow — the clearest example of the wiring. Note: `customer_care` is frozen (Rule 3) and still uses `self.agent.run_sync()` directly. **New nodes should use `self.run_agent_recorded()` instead** to get automatic token-usage recording.

```python
# app/workflows/customer_care_workflow_nodes/filter_spam.py
class FilterSpamNode(AgentNode):

    # 1. Extend OutputType to declare what the LLM must return
    class OutputType(AgentNode.OutputType):
        reasoning: str = Field(description="Explain your reasoning...")
        confidence: float = Field(ge=0, le=1, description="Confidence score...")
        is_human: bool = Field(description="True if written by a human; False if spam.")

    # 2. Declare the agent's config
    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt="You are a helpful assistant that filters messages...",
            output_type=self.OutputType,
            deps_type=None,
            model_provider=ModelProvider.OPENAI,
            model_name="gpt-4o",
        )

    # 3. Use the agent in process()
    def process(self, task_context: TaskContext) -> TaskContext:
        event: CustomerCareEventSchema = task_context.event
        result = self.agent.run_sync(user_prompt=event.model_dump_json())
        task_context.update_node(node_name=self.node_name, result=result)
        return task_context
```

Walk through what happens when `FilterSpamNode()` is instantiated and called:

1. `FilterSpamNode.__init__()` → calls `AgentNode.__init__()`.
2. `AgentNode.__init__()` calls `self.get_agent_config()` → gets the config above.
3. `__get_model_instance(OPENAI, "gpt-4o")` → returns an `OpenAIModel`.
4. `Agent(system_prompt=..., output_type=FilterSpamNode.OutputType, model=OpenAIModel)` is stored as `self.agent`.
5. When `process(task_context)` is called later, `self.agent.run_sync(user_prompt=...)` fires the API call.
6. pydantic-ai validates the response against `OutputType` — if the model returns something that doesn't validate, it retries automatically.
7. The validated result is stored into `task_context` via `update_node(...)`.

### `run_agent_recorded` — usage-capturing replacement for `run_sync`

```python
def run_agent_recorded(self, task_context: TaskContext, user_prompt: str):
```

This helper (added in Task 6 of the incremental-execution-observability spec) calls
`self.agent.run_sync(user_prompt=user_prompt)`, reads `result.usage()`, and writes
`{input_tokens, output_tokens, model}` onto `task_context.node_runs[self.node_name].usage`.
It is a no-op when no `NodeRun` has been seeded (e.g. in unit tests that run nodes
outside the framework). Returns the pydantic-ai result unchanged.

**Recommended pattern for new nodes:**

```python
def process(self, task_context: TaskContext) -> TaskContext:
    event: MyEventSchema = task_context.event
    result = self.run_agent_recorded(task_context, user_prompt=event.model_dump_json())
    task_context.update_node(self.node_name, result=result.output)
    return task_context
```

A `getattr` fallback inside `run_agent_recorded` covers both newer pydantic-ai
(`input_tokens`/`output_tokens`) and the pinned `>=0.1.5` token names
(`request_tokens`/`response_tokens`), so an SDK upgrade will not silently zero
out recorded usage.

> **`@abstractmethod` enforcement:** Both `get_agent_config()` and `process()` are formal `@abstractmethod` declarations (confirmed in `agent.py`). Forgetting to implement either raises `TypeError` at instantiation time — when `AgentNode()` is called — not at call time when `process()` would execute. This means a misconfigured node fails at worker startup, not when an event arrives.

---

## What `OutputType` and `DepsType` actually do

**`OutputType`** tells pydantic-ai the shape of the response you expect. pydantic-ai converts this to a tool-call schema under the hood and forces the model to return JSON matching it. You then access `.output` on the result to get a typed instance.

```python
result = self.agent.run_sync(user_prompt="...")
result.output.is_human        # bool — fully typed, validated
result.output.confidence      # float between 0 and 1
```

**`DepsType`** is for injecting runtime context into dynamic parts of the system prompt — for example, a user's account tier that can only be known at call time. The deps instance would be passed to `run_sync(deps=...)` and made available inside `@agent.system_prompt` decorated functions.

**Current implementation note:** `deps_type` is collected in `AgentConfig` but is not yet passed to the pydantic-ai `Agent(...)` constructor in `AgentNode.__init__`. The `Agent` call currently passes only `system_prompt`, `output_type`, and `model`. If you need deps injection in a node today, you would need to extend `__init__` to wire it through. `FilterSpamNode` uses `deps_type=None`, so this gap doesn't affect it.

---

## Key design decision: why pydantic-ai instead of the raw SDK?

pydantic-ai handles the tool-call loop for you. When `output_type` is set, the model is instructed to call a `final_result` tool; pydantic-ai validates the arguments against the Pydantic schema and retries if validation fails. For nodes that are infrastructure (classification, generation, summarisation), this is exactly what you want — less code, more reliability.

For nodes where understanding the loop *is* the goal (Project 2's research agent), you'd write a raw `ToolUseNode` instead and manage the `while stop_reason == "tool_use"` loop yourself.
