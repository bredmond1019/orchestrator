---
type: Reference
title: Core Engine API Reference
description: Class-level reference for the public abstractions in app/core, app/database, app/services, and app/workflows that a developer subclasses when writing a new workflow.
---

# Core Engine API Reference

Precise class-level reference for every public abstraction a developer must understand
and subclass when writing a new workflow. All information is derived from source files
in `app/core/`, `app/database/`, `app/services/`, and `app/workflows/`.

---

## Table of Contents

1. [Workflow](#workflow)
2. [WorkflowSchema and NodeConfig](#workflowschema-and-nodeconfig)
3. [WorkflowValidator](#workflowvalidator)
4. [TaskContext](#taskcontext)
5. [Node](#node)
6. [AgentNode](#agentnode)
7. [ParallelNode](#parallelnode)
8. [BaseRouter and RouterNode](#baserouter-and-routernode)
9. [ToolUseNode](#tooluse-node)
10. [GenericRepository](#genericrepository)
11. [PromptManager](#promptmanager)
12. [EmbeddingService](#embeddingservice)
13. [ArticleExtractionService](#articleextractionservice)
14. [SearchService and SearchResult](#searchservice-and-searchresult)
15. [ChunkingService](#chunkingservice)
16. [TranscriptService](#transcriptservice)
17. [WorkflowRegistry](#workflowregistry)
18. [Event SQLAlchemy Model](#event-sqlalchemy-model)
19. [createworkflow CLI](#createworkflow-cli)
20. [API Layer](#api-layer)

---

## Workflow

**Source:** `app/core/workflow.py`

Abstract base class for all workflow implementations. Subclasses declare a
`workflow_schema` class variable and inherit the full execution loop.

### Class Variable

```python
workflow_schema: ClassVar[WorkflowSchema]
```

Every concrete subclass **must** assign this at the class level before the class
is instantiated. It is read during `__init__` by the validator and during `run()`
by the execution loop.

### `__init__` Validation Sequence

When a `Workflow` instance is created, four steps execute in order:

1. `WorkflowValidator(self.workflow_schema)` — constructs a validator bound to the schema.
2. `self.validator.validate()` — runs the full DAG + connection check; raises `ValueError` on failure.
3. `self._initialize_nodes()` — builds `self.nodes: Dict[Type[Node], NodeConfig]` from every
   `NodeConfig` listed in the schema, including nodes that appear only as connection targets.
4. `load_dotenv()` — loads environment variables from `.env`.

### `run(event: Any, on_progress: Callable[[TaskContext], None] | None = None) -> TaskContext`

Main entry point called by the Celery worker.

```python
def run(
    self,
    event: Any,
    on_progress: Callable[[TaskContext], None] | None = None,
) -> TaskContext:
```

`on_progress` is an optional callback invoked with a snapshot of `TaskContext` at two points:

- **Before the first node:** every node in `self.nodes` is seeded `PENDING` in
  `task_context.node_runs` (via `setdefault`), then `on_progress(task_context)` is called once
  so a freshly-dispatched run immediately surfaces the full DAG as pending.
- **After each node boundary:** once per node after `node_context()` exits (success or failure),
  `on_progress(task_context)` is called with the updated snapshot before computing the next node.

Passing `None` (the default) disables all callback invocations — the parameter is fully
backward-compatible with existing call sites.

Execution steps:

1. Construct `TaskContext(event=event)`.
2. Re-parse the raw event dict through the schema's Pydantic model:
   `task_context.event = self.workflow_schema.event_schema(**event)`.
3. Write the nodes registry into `task_context.metadata["nodes"]`.
4. Seed all nodes `PENDING` in `task_context.node_runs` and invoke `on_progress` once (if set).
5. Set `current_node_class = self.workflow_schema.start`.
6. Loop while `current_node_class` is not `None`:
   - Look up the node class via `self.nodes[current_node_class].node`, then
     instantiate it and call `process(task_context)` inside `node_context()`.
   - Invoke `on_progress(task_context)` (if set) after the boundary exits.
   - Resolve the next node via `_get_next_node_class()`.
7. Remove `"nodes"` from `task_context.metadata` before returning.
8. Return the final `TaskContext`.

### `_get_next_node_class(current_node_class, task_context) -> Optional[Type[Node]]`

Resolves the successor after each node completes.

- Looks up `current_node_class` in `self.workflow_schema.nodes`.
- Returns `None` if no `NodeConfig` exists for it, or if `connections` is empty.
- If `node_config.is_router` is `True`: instantiates the router again and delegates
  to `_handle_router()`, which calls `router.route(task_context)` and returns the
  class of the returned node instance (`next_node.__class__`).
- Otherwise: returns `node_config.connections[0]` — the single linear successor.

### `node_context(node_name: str, task_context: TaskContext)` — Context Manager

```python
@contextmanager
def node_context(self, node_name: str, task_context: TaskContext):
```

Wraps every node execution. On entry, sets the node's `NodeRun` to `RUNNING` and
records a UTC `started_at` timestamp. On a clean exit, sets status to `SUCCESS` and
records `completed_at`. If the node raises, sets status to `FAILED`, records the
stringified exception in `error` and records `completed_at`, then re-raises.

Emits `logging.info` on entry and exit, and `logging.error` on exception. No value
is yielded. The envelope is written entirely by the framework — individual nodes
never touch `node_runs` directly.

---

## WorkflowSchema and NodeConfig

**Source:** `app/core/schema.py`

Both classes are Pydantic `BaseModel` subclasses — all fields are validated at
construction time.

### `WorkflowSchema`

```python
class WorkflowSchema(BaseModel):
    description: Optional[str] = None
    event_schema: Type[BaseModel]
    start: Type[Node]
    nodes: List[NodeConfig]
```

| Field | Type | Required | Description |
|---|---|---|---|
| `description` | `Optional[str]` | No | Human-readable description of the workflow. |
| `event_schema` | `Type[BaseModel]` | Yes | Pydantic model class used to validate the raw event dict at run time. |
| `start` | `Type[Node]` | Yes | The node class that receives control first when `run()` executes. |
| `nodes` | `List[NodeConfig]` | Yes | Ordered list of every node configuration in the workflow. |

`event_schema` is called as `event_schema(**event)` inside `Workflow.run()`, so the
incoming event dict must match the schema's field names exactly.

### `NodeConfig`

```python
class NodeConfig(BaseModel):
    node: Type[Node]
    connections: List[Type[Node]] = Field(default_factory=list)
    is_router: bool = False
    description: Optional[str] = None
    parallel_nodes: Optional[List[Type[Node]]] = Field(default_factory=list)
```

| Field | Type | Default | Description |
|---|---|---|---|
| `node` | `Type[Node]` | required | The node class this config describes. |
| `connections` | `List[Type[Node]]` | `[]` | Successor node classes in declaration order. |
| `is_router` | `bool` | `False` | When `True`, routing is delegated to the node's `route()` logic rather than taking `connections[0]`. |
| `description` | `Optional[str]` | `None` | Documentation string; not used at runtime. |
| `parallel_nodes` | `Optional[List[Type[Node]]]` | `[]` | Node classes launched concurrently by a `ParallelNode`; distinct from `connections`. |

**`parallel_nodes` vs `connections`:** `connections` defines the DAG edge that the
workflow engine traverses sequentially. `parallel_nodes` is a separate list consumed
only by `ParallelNode.execute_nodes_in_parallel()` — the workflow engine does not
traverse these edges automatically.

**`is_router` semantics:** A node config with `is_router=True` may list multiple
`connections`. `WorkflowValidator` rejects any non-router config that declares more
than one connection. When `is_router=True`, `_get_next_node_class` re-instantiates
the node and calls `route()` to select which connection to follow at run time.

---

## WorkflowValidator

**Source:** `app/core/validate.py`

```python
class WorkflowValidator:
    def __init__(self, workflow_schema: WorkflowSchema): ...
```

Constructed with a `WorkflowSchema` instance and called once in `Workflow.__init__`.

### `validate()`

Calls `_validate_dag()` then `_validate_connections()`. Raises `ValueError` on the
first failure.

### `_validate_dag()` — DFS Cycle Detection + BFS Reachability

Two checks run in sequence:

1. **Cycle detection (`_has_cycle`)** — iterative DFS using a visited set and a
   recursion stack set. For each unvisited node in the schema, a recursive DFS
   function marks the node in both sets, recurses into each neighbor listed in
   `connections`, and removes the node from the recursion stack on the way back.
   If a neighbor is already in the recursion stack, a cycle is detected.
   Raises `ValueError("Workflow schema contains a cycle")`.

2. **Reachability check (`_get_reachable_nodes`)** — BFS starting from
   `workflow_schema.start`. Every node reachable by following `connections` edges
   is collected into a set. Any node declared in `workflow_schema.nodes` but absent
   from that set triggers:
   `ValueError("The following nodes are unreachable: {unreachable_nodes}")`.

### `_validate_connections()`

Iterates every `NodeConfig`. If `len(node_config.connections) > 1` and
`node_config.is_router` is `False`, raises:

```
ValueError("Node {name} has multiple connections but is not marked as a router.")
```

---

## NodeStatus

**Source:** `app/core/task.py`

```python
class NodeStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
```

Lifecycle enum for a single node execution. Serializes to its string value via
`model_dump(mode="json")` (e.g. `"success"`), making it safe to store in the
`task_context` JSON column without additional conversion.

---

## NodeRun

**Source:** `app/core/task.py`

```python
class NodeRun(BaseModel):
    status: NodeStatus = NodeStatus.PENDING
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    usage: dict | None = None
```

Per-node execution envelope. Written entirely by the framework (`Workflow.node_context`);
node implementations never touch it directly.

| Field | Type | Description |
|---|---|---|
| `status` | `NodeStatus` | Lifecycle state: `PENDING` → `RUNNING` → `SUCCESS` or `FAILED`. Default `PENDING`. |
| `started_at` | `str \| None` | ISO-8601 timestamp set when the node begins executing. `None` until then. |
| `completed_at` | `str \| None` | ISO-8601 timestamp set when the node finishes (success or failure). |
| `error` | `str \| None` | Stringified exception message if the node raised; `None` on success. |
| `usage` | `dict \| None` | Token-usage dict `{input_tokens, output_tokens, model}` for LLM nodes; `None` for non-LLM nodes. |

---

## TaskContext

**Source:** `app/core/task.py`

```python
class TaskContext(BaseModel):
    event: Any
    nodes: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    node_runs: dict[str, NodeRun] = Field(default_factory=dict)
```

The single shared state object threaded through every node in the workflow.

| Field | Type | Description |
|---|---|---|
| `event` | `Any` | Initially the raw event dict; replaced with the parsed Pydantic schema instance by `Workflow.run()`. |
| `nodes` | `dict[str, Any]` | Accumulates per-node results. Each node writes its output under its own name. |
| `metadata` | `dict[str, Any]` | Workflow-level data. During execution, `"nodes"` key holds the full `Dict[Type[Node], NodeConfig]` registry; this key is removed before `run()` returns. A `field_serializer` also strips `"nodes"` from any `model_dump(mode="json")` call made mid-run, so partial snapshots passed to `on_progress` are always JSON-safe. |
| `node_runs` | `dict[str, NodeRun]` | Per-node execution envelope (status, timing, error, token usage), keyed by node class name. A parallel, additive channel to `nodes` — never replaces node output. Written by the framework; read by callers for observability. |

### `update_node(node_name: str, **kwargs)`

```python
def update_node(self, node_name: str, **kwargs):
    self.nodes[node_name] = {**self.nodes.get(node_name, {}), **kwargs}
```

Merges `kwargs` into the dict stored at `self.nodes[node_name]`. If no entry exists
for `node_name`, it is created. Existing keys for that node are preserved unless
overwritten by a kwarg with the same key.

**Usage pattern inside a node:**

```python
def process(self, task_context: TaskContext) -> TaskContext:
    result = self._run_analysis(task_context.event)
    task_context.update_node(self.node_name, score=result.score, label=result.label)
    return task_context
```

### `get_node_output(node_name: str) -> Any`

```python
def get_node_output(self, node_name: str) -> Any:
```

Retrieves the output stored for a completed node. Raises a descriptive `KeyError` if
the node has not run yet, naming the missing node, listing the nodes that have completed
so far, and suggesting that the `WorkflowSchema` ordering be checked.

**Raises:** `KeyError` — when `node_name` is not present in `self.nodes`. The error
message has the form:

```
Router expected output from node '<node_name>', but it has not run.
Nodes completed so far: [<list>].
Check that '<node_name>' appears before the router in the WorkflowSchema.
```

**Usage pattern inside a router node:**

```python
def determine_next_node(self, task_context: TaskContext) -> Optional[Node]:
    output = task_context.get_node_output("AnalyzeTicketNode")
    if output["intent"] == "refund":
        return ProcessRefundNode()
    return None
```

New router nodes should prefer `get_node_output()` over direct `task_context.nodes[name]`
access. Direct access still works but produces a raw `KeyError` with no diagnostic
context if the node has not run yet.

Downstream nodes read the accumulated results directly from `task_context.nodes`.

---

## Node

**Source:** `app/core/nodes/base.py`

```python
class Node(ABC):
```

Abstract base for all processing steps. Implements the Chain of Responsibility
pattern: each node receives the context, mutates it, and returns it.

### `node_name` property

```python
@property
def node_name(self) -> str:
    return self.__class__.__name__
```

Returns the class name. This is the key used when writing results into
`task_context.nodes`. Consistent with how routers record routing decisions.

### `process(task_context: TaskContext) -> TaskContext` — Abstract

```python
@abstractmethod
def process(self, task_context: TaskContext) -> TaskContext:
```

**Contract:**

- Receives the shared `TaskContext`.
- Performs the node's work.
- Stores results into `task_context.nodes[self.node_name]` (typically via
  `task_context.update_node(self.node_name, ...)`).
- Returns the (modified) `TaskContext`. The workflow engine replaces its reference
  with the returned value, so the return must not be `None`.

Every concrete class — whether it extends `Node`, `AgentNode`, `ParallelNode`, or
any router variant — must implement this method.

---

## AgentNode

**Source:** `app/core/nodes/agent.py`

```python
class AgentNode(Node, ABC):
```

Extends `Node` with pydantic-ai `Agent` wiring. Subclasses implement
`get_agent_config()` to declare which model to use and what the system prompt is.

### Inner Classes

```python
class DepsType(BaseModel):
    pass

class OutputType(BaseModel):
    pass
```

Both are stubs. Subclasses override `DepsType` to declare injectable dependencies
and `OutputType` to declare the structured response schema passed to pydantic-ai
as `output_type`.

### `AgentConfig` Dataclass

```python
@dataclass
class AgentConfig:
    system_prompt: str
    output_type: Optional[Type[Any]]
    deps_type: Optional[Type[Any]]
    model_provider: ModelProvider
    model_name: Union[OpenAIModelName, AnthropicModelName, GeminiModelName, BedrockModelName]
```

| Field | Type | Description |
|---|---|---|
| `system_prompt` | `str` | Rendered system prompt string (obtain via `PromptManager.get_prompt()`). |
| `output_type` | `Optional[Type[Any]]` | Pydantic model class for structured output; `None` for plain text. |
| `deps_type` | `Optional[Type[Any]]` | Dependency injection type for the agent. |
| `model_provider` | `ModelProvider` | Enum value selecting the provider backend. |
| `model_name` | union of provider name types | Provider-specific model identifier string. |

### `ModelProvider` Enum

```python
class ModelProvider(StrEnum):
    OPENAI        = "openai"
    AZURE_OPENAI  = "azure_openai"
    ANTHROPIC     = "anthropic"
    GEMINI        = "gemini"
    OLLAMA        = "ollama"
    BEDROCK       = "bedrock"
```

### `get_agent_config() -> AgentConfig` — Abstract

```python
@abstractmethod
def get_agent_config(self) -> AgentConfig:
```

Called once in `__init__`. Must return a fully populated `AgentConfig`. The system
prompt should be loaded from a `.j2` file via `PromptManager.get_prompt()`.

### `__init__` — Agent Wiring

```python
def __init__(self):
    self.__async_client = AsyncClient()
    agent_wrapper = self.get_agent_config()
    self.agent = Agent(
        system_prompt=agent_wrapper.system_prompt,
        output_type=agent_wrapper.output_type,
        model=self.__get_model_instance(agent_wrapper.model_provider, agent_wrapper.model_name),
    )
```

A single `httpx.AsyncClient` is shared across all provider calls made from this
node instance.

### Provider-Specific Model Construction

| Provider | Constructor | Env Vars Required |
|---|---|---|
| `OPENAI` | `OpenAIModel(model_name, provider=OpenAIProvider(http_client=...))` | `OPENAI_API_KEY` (standard pydantic-ai default) |
| `AZURE_OPENAI` | `OpenAIModel(model_name, provider=OpenAIProvider(openai_client=AsyncAzureOpenAI()))` | Azure SDK env vars |
| `ANTHROPIC` | `AnthropicModel(model_name=..., provider=AnthropicProvider(http_client=...))` | `ANTHROPIC_API_KEY` |
| `GEMINI` | `GeminiModel(model_name=..., provider=GoogleGLAProvider(http_client=...))` | `GOOGLE_API_KEY` |
| `OLLAMA` | `OpenAIModel(model_name=..., provider=OpenAIProvider(base_url=...))` | `OLLAMA_BASE_URL` |
| `BEDROCK` | `BedrockConverseModel(model_name=..., provider=BedrockProvider(bedrock_client=...))` | `BEDROCK_AWS_ACCESS_KEY_ID`, `BEDROCK_AWS_SECRET_ACCESS_KEY`, `BEDROCK_AWS_REGION` |

If `model_provider` does not match any enum value, the implementation falls back to
`OpenAIModel("gpt-4.1")`.

For Ollama: if `OLLAMA_BASE_URL` is not set in the environment, `__init__` raises
`KeyError("OLLAMA_BASE_URL not set in .env")` immediately.

### `run_agent_recorded(task_context, user_prompt) -> Any` — Usage Recording Helper

```python
def run_agent_recorded(self, task_context: TaskContext, user_prompt: str):
```

Runs `self.agent.run_sync(user_prompt=user_prompt)` and stamps token usage onto
`task_context.node_runs[self.node_name].usage` before returning the pydantic-ai result.

**New AgentNode subclasses should call this instead of `self.agent.run_sync` directly**
so per-node token usage is captured in one place. The method is a no-op when no
`NodeRun` is seeded for this node (e.g. when running outside the framework).

The recorded usage dict has the shape:

```python
{
    "input_tokens": int | None,
    "output_tokens": int | None,
    "model": str,   # from get_agent_config().model_name
}
```

A `getattr` fallback covers both current pydantic-ai (`input_tokens`/`output_tokens`)
and the pinned `>=0.1.5` token-name variant (`request_tokens`/`response_tokens`).

**Usage pattern:**

```python
def process(self, task_context: TaskContext) -> TaskContext:
    result = self.run_agent_recorded(task_context, user_prompt=event.model_dump_json())
    task_context.update_node(self.node_name, score=result.output.score)
    return task_context
```

The existing `customer_care` nodes call `self.agent.run_sync()` directly and are
frozen (Rule 3). Those nodes record no usage — that is intentional and expected.

---

## ParallelNode

**Source:** `app/core/nodes/parallel.py`

```python
class ParallelNode(Node, ABC):
```

Extends `Node` to add concurrent sub-node execution. The subclass `process()` method
calls `execute_nodes_in_parallel()` and then decides what to do with the results.

### `execute_nodes_in_parallel(task_context: TaskContext) -> List[TaskContext]`

```python
def execute_nodes_in_parallel(self, task_context: TaskContext):
    node_config: NodeConfig = task_context.metadata["nodes"][self.__class__]
    future_list = []
    with ThreadPoolExecutor() as executor:
        for node in node_config.parallel_nodes:
            future = executor.submit(node().process, task_context)
            future_list.append(future)
        results = [future.result() for future in future_list]
    return results
```

**Mechanics:**

1. Reads `task_context.metadata["nodes"][self.__class__]` to obtain the `NodeConfig`
   for this node — which is why `Workflow.run()` populates `metadata["nodes"]` before
   the loop starts.
2. Iterates `node_config.parallel_nodes`, instantiating each class and submitting
   `node.process(task_context)` to a `ThreadPoolExecutor`.
3. Collects results by calling `.result()` on every future in submission order.
4. Returns the list of `TaskContext` objects returned by each sub-node.

**Caution:** All sub-nodes receive the **same** `task_context` reference concurrently.
Sub-nodes that write to `task_context.nodes` under their own key are safe as long as
their keys do not collide. Sub-nodes that modify shared keys will race.

The parallel nodes listed in `NodeConfig.parallel_nodes` are **not** traversed by
the workflow engine's main loop — they execute only when the owning `ParallelNode`
explicitly calls `execute_nodes_in_parallel()`.

---

## BaseRouter and RouterNode

**Source:** `app/core/nodes/router.py`

Two cooperating classes implement routing:

- `BaseRouter` — a concrete `Node` subclass that drives the routing loop and writes
  the decision to `TaskContext`.
- `RouterNode` — an abstract helper that encapsulates a single routing condition.

### `BaseRouter`

```python
class BaseRouter(Node):
    routes: ...       # List of RouterNode instances
    fallback: ...     # Optional Node instance
```

`routes` and `fallback` are not declared with type annotations in the source; concrete
subclasses must define them as instance attributes.

#### `process(task_context: TaskContext) -> TaskContext`

```python
def process(self, task_context: TaskContext) -> TaskContext:
    next_node = self.route(task_context)
    task_context.nodes[self.node_name] = {"next_node": next_node.node_name}
    return task_context
```

Writes the routing decision as `{"next_node": "<ClassName>"}` under the router's
own key in `task_context.nodes`, then returns the context.

#### `route(task_context: TaskContext) -> Node`

```python
def route(self, task_context: TaskContext) -> Node:
    for route_node in self.routes:
        next_node = route_node.determine_next_node(task_context)
        if next_node:
            return next_node
    return self.fallback if self.fallback else None
```

First-match evaluation: iterates `self.routes` in order, returns the first non-`None`
result from `determine_next_node()`. If no route matches, returns `self.fallback` or
`None`. When `route()` returns `None`, `Workflow._handle_router()` returns `None`,
terminating the execution loop.

### `RouterNode`

```python
class RouterNode(ABC):
    @abstractmethod
    def determine_next_node(self, task_context: TaskContext) -> Optional[Node]:
        pass

    @property
    def node_name(self):
        return self.__class__.__name__
```

Each `RouterNode` subclass implements one routing condition. Return a `Node` instance
to claim the route; return `None` to pass to the next `RouterNode` in the list.

**Important:** `Workflow._handle_router()` calls `router.route()` and then reads
`next_node.__class__` to get the node type for the main execution loop. The returned
`Node` instance from `determine_next_node()` is used only for its class — the workflow
engine instantiates a fresh instance when executing the next node.

---

## ToolUse Node

**Source:** `app/core/nodes/tool_use.py`

```python
class ToolUseNode(Node):
```

Abstract base that drives a raw Anthropic SDK tool-use loop. Unlike `AgentNode`
(which delegates to pydantic-ai), `ToolUseNode` calls `anthropic.Anthropic().messages.create`
directly and manages the `tool_use` / `tool_result` message cycle itself. Subclasses
declare the tools they expose and handle each tool call.

### Class Attribute

```python
max_iterations: int = 10
```

Hard upper bound on the request/tool-result loop. The loop exits cleanly when this
limit is reached — it never raises. Subclasses may override the value but must not
set it to `None` (the guard is unconditional).

### `__init__`

```python
def __init__(self) -> None:
    self._client = anthropic.Anthropic()
    self._model = os.getenv("TOOL_USE_MODEL", _DEFAULT_MODEL)
```

Instantiates the Anthropic client and reads the model from the `TOOL_USE_MODEL`
environment variable (default `claude-haiku-4-5-20251001`). The model is never
hardcoded, keeping deployment choices outside the node.

### `tools` — Abstract Property

```python
@property
@abstractmethod
def tools(self) -> list[dict]:
    """Anthropic tool definitions for this node."""
```

Must return a list of Anthropic tool-definition dicts (the `tools` parameter passed
to `messages.create`). Subclasses declare exactly which tools they expose.

### `handle_tool_call(tool_name, tool_input, task_context) -> str` — Abstract

```python
@abstractmethod
def handle_tool_call(
    self,
    tool_name: str,
    tool_input: dict,
    task_context: TaskContext,
) -> str:
    """Execute a single tool call and return the result string."""
```

Called once per `tool_use` block in the model response. Must return a plain string;
that string is sent back to the model as the `tool_result` content.

### `_build_initial_messages(task_context) -> list[dict]`

```python
def _build_initial_messages(self, task_context: TaskContext) -> list[dict]:
    return [{"role": "user", "content": str(task_context.nodes)}]
```

Hook for shaping the opening user message. Concrete subclasses override this to
inject domain-specific context (e.g., an event payload) without overriding the whole
loop. Default serialises `task_context.nodes` as a string.

### `process(task_context: TaskContext) -> TaskContext`

```python
def process(self, task_context: TaskContext) -> TaskContext:
```

Runs the tool-use loop:

1. Calls `_build_initial_messages()` to seed the message list.
2. Calls `messages.create(model, max_tokens=4096, tools, messages)`.
3. Accumulates `input_tokens` and `output_tokens` from `response.usage` on every
   iteration (uses `getattr` so it is safe when `usage` is absent).
4. On `stop_reason == "end_turn"`: breaks immediately.
5. On `stop_reason == "tool_use"`: iterates `response.content`, calls
   `handle_tool_call()` for each `tool_use` block, appends the assistant turn and
   a `user` turn containing the `tool_result` list, then loops.
6. On any other `stop_reason` (e.g. `"max_tokens"`): breaks immediately.
7. After the loop, if `iterations >= max_iterations`, logs a `WARNING` with the node
   name and limit.
8. Records accumulated token counts onto `task_context.node_runs[self.node_name].usage`
   as `{input_tokens, output_tokens, model}` (only when a `NodeRun` is seeded).
   Returns `task_context` whether exhausted or not.

**Note:** `process` does not write output into `task_context.nodes[self.node_name]`
by default — concrete subclasses are expected to do that inside `handle_tool_call()`
or by overriding `process` and calling `super().process()`.

### Subclassing Example

```python
from core.nodes.tool_use import ToolUseNode
from core.task import TaskContext

class LookupNode(ToolUseNode):
    @property
    def tools(self) -> list[dict]:
        return [
            {
                "name": "lookup_record",
                "description": "Fetch a record by id.",
                "input_schema": {
                    "type": "object",
                    "properties": {"record_id": {"type": "string"}},
                    "required": ["record_id"],
                },
            }
        ]

    def handle_tool_call(
        self, tool_name: str, tool_input: dict, task_context: TaskContext
    ) -> str:
        if tool_name == "lookup_record":
            record = fetch(tool_input["record_id"])
            task_context.update_node(self.node_name, {"record": record})
            return str(record)
        return "unknown tool"
```

---

## GenericRepository

**Source:** `app/database/repository.py`

```python
class GenericRepository[T]:
    def __init__(self, session: Session, model: type[T]): ...
```

Type-safe wrapper around a SQLAlchemy `Session`. Instantiated per request with the
model class it manages.

### Constructor

| Parameter | Type | Description |
|---|---|---|
| `session` | `sqlalchemy.orm.Session` | Active SQLAlchemy session, typically injected via `db_session()`. |
| `model` | `Type[T]` | The SQLAlchemy model class (e.g., `Event`). |

### Method Signatures and Return Types

| Method | Signature | Returns | Notes |
|---|---|---|---|
| `create` | `create(obj: T) -> T` | The persisted object | Calls `session.add()` + `session.commit()`. |
| `get` | `get(obj_id: str) -> Optional[T]` | Single instance or `None` | Filters by `model.id == obj_id`. |
| `get_all` | `get_all() -> List[T]` | All rows | No ordering guarantee. |
| `update` | `update(obj: T) -> T` | The original `obj` passed in | Calls `session.merge(obj)` (return value discarded) + `session.commit()`; returns the original object. |
| `delete` | `delete(obj_id: str) -> None` | `None` | Fetches then deletes; no-op if not found. |
| `get_latest` | `get_latest(n: int = 1) -> List[T]` | Up to `n` rows | Orders by `model.id DESC`. |
| `count` | `count() -> int` | Row count | Uses SQLAlchemy `count()`. |
| `exists` | `exists(**kwargs) -> bool` | Boolean | Returns `True` if any row matching all `kwargs` exists; `False` otherwise. |

### `exists()` Implementation

```python
def exists(self, **kwargs) -> bool:
    return (
        self.session.query(self.model).filter_by(**kwargs).first() is not None
    )
```

Uses the SQLAlchemy 2.x-compatible pattern — `session.query(model).filter_by(**kwargs).first()`.
Accepts any column name and value recognized by the model as keyword arguments.

---

## PromptManager

**Source:** `app/services/prompt_loader.py`

```python
class PromptManager:
    _env = None  # class-level singleton Jinja2 Environment
```

Loads `.j2` templates from `app/prompts/`, parses YAML frontmatter, and renders the
Jinja2 body with caller-supplied variables.

### `get_prompt(template: str, **kwargs) -> str`

```python
@staticmethod
def get_prompt(template: str, **kwargs) -> str:
```

| Parameter | Description |
|---|---|
| `template` | Template name **without** the `.j2` extension (e.g., `"ticket_analysis"`). |
| `**kwargs` | Variables substituted into the Jinja2 template body. |

Returns the fully rendered string.

Raises `ValueError` if Jinja2 rendering fails (e.g., an undefined variable is
referenced and `StrictUndefined` is active). Raises `jinja2.TemplateNotFound` if the
template does not exist in `app/prompts/`.

**`StrictUndefined` behavior:** The environment is created with
`undefined=StrictUndefined`. Any variable referenced in the template body that is not
supplied via `**kwargs` and has no `| default(...)` filter will raise a `ValueError`
at render time, not silently produce an empty string.

### `get_template_info(template: str) -> dict`

```python
@staticmethod
def get_template_info(template: str) -> dict:
```

Returns a dict with these keys:

| Key | Source | Type |
|---|---|---|
| `name` | The `template` argument | `str` |
| `description` | `frontmatter.metadata["description"]` | `str` (default: `"No description provided"`) |
| `author` | `frontmatter.metadata["author"]` | `str` (default: `"Unknown"`) |
| `variables` | `jinja2.meta.find_undeclared_variables` on the template AST | `list` |
| `frontmatter` | Full raw `post.metadata` dict | `dict` |

Raises `jinja2.TemplateNotFound` if the template does not exist in `app/prompts/`.

### `.j2` Frontmatter Schema

Templates use YAML frontmatter delimited by `---`. Only two fields are read by
`PromptManager`:

```yaml
---
description: Human-readable description of what this prompt does
author: Author or team name
---
```

The remainder of the file is the Jinja2 template body rendered by `get_prompt()`.
Example from `ticket_analysis.j2`:

```
---
description: A template for analyzing incoming {{ pipeline | default('customer support') }} tickets
author: TechGear AI Team
---

You're an AI assistant named {{ name | default('Emma') }}, working for {{ company | default('TechGear') }}.
```

---

## EmbeddingService

**Source:** `app/services/embedding_service.py`

```python
class EmbeddingService:
    def __init__(self, model: str = "voyage-2", dims: int = 1024) -> None:
```

Wraps the VoyageAI client to produce float embedding vectors. `model` and `dims` are
constructor params — this is the deliberate provider-swap seam: substituting a local
model (e.g. Qwen3-Embedding via Ollama) requires no code changes, only a different
constructor call.

Reads `VOYAGE_API_KEY` from the environment at construction time via `os.environ["VOYAGE_API_KEY"]`.
If the variable is absent a `KeyError` is raised immediately.

### Constructor parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `model` | `str` | `"voyage-2"` | Model name passed to `voyageai.Client.embed()`. |
| `dims` | `int` | `1024` | Expected embedding dimensionality (stored for future vector-column validation; not currently enforced against returned vectors). |

### `embed_text(text: str) -> list[float]`

```python
def embed_text(self, text: str) -> list[float]:
```

Embeds a single string and returns its vector as a `list[float]`.
Internally calls `voyageai.Client.embed([text], model=self._model)` and returns
`result.embeddings[0]`.

### `embed_batch(texts: list[str]) -> list[list[float]]`

```python
def embed_batch(self, texts: list[str]) -> list[list[float]]:
```

Embeds a list of strings in one API call and returns one vector per input as a
`list[list[float]]`.
Internally calls `voyageai.Client.embed(texts, model=self._model)` and returns
`result.embeddings`.

### Export

`EmbeddingService` is exported from `app/services/__init__.py`:

```python
from services import EmbeddingService
```

---

## ArticleExtractionService

**Source:** `app/services/article_extraction_service.py`

```python
class ArticleResult(BaseModel):
    text: str
    title: str | None = None
    fetch_status: str  # "ok" | "fallback_used" | "failed"

class ArticleExtractionService:
    def __init__(self) -> None: ...
    def extract(self, url: str) -> ArticleResult: ...
```

Extracts readable article text from a URL. Uses `trafilatura` as the primary path
(free, local, fast for clean articles) and optionally falls back to the Firecrawl
hosted scraper when trafilatura returns nothing (e.g., JS-rendered pages).

The service is **stateless** — no call-count guard. Per-agent rate limiting belongs
in the calling node, not here.

### `ArticleResult`

| Field | Type | Values |
|---|---|---|
| `text` | `str` | Extracted article body; empty string on failure |
| `title` | `str \| None` | Page title when available; `None` otherwise |
| `fetch_status` | `str` | `"ok"` — trafilatura succeeded; `"fallback_used"` — Firecrawl fallback succeeded; `"failed"` — both paths failed |

### `ArticleExtractionService.extract(url)`

```python
def extract(self, url: str) -> ArticleResult:
```

Never raises. On total extraction failure returns an `ArticleResult` with
`text=""` and `fetch_status="failed"` and logs a `WARNING`.

**Extraction path:**

1. `trafilatura.fetch_url(url)` → `trafilatura.extract(downloaded)`
2. If step 1 returns `None` **and** `FIRECRAWL_API_KEY` is set, calls
   `FirecrawlApp.scrape_url(url, params={"formats": ["markdown"]})`.
3. If both paths fail, returns `fetch_status="failed"`.

**Firecrawl fallback gating:** The fallback is silently skipped when
`FIRECRAWL_API_KEY` is absent. No exception is raised.

### Exports

Both `ArticleExtractionService` and `ArticleResult` are exported from
`app/services/__init__.py`:

```python
from services import ArticleExtractionService, ArticleResult
```

---

## SearchService and SearchResult

**Source:** `app/services/search_service.py`

Thin wrapper over the [Tavily](https://tavily.com/) search client. Returns typed
`SearchResult` instances suitable for a tool-use agent loop.

### `SearchResult`

```python
class SearchResult(BaseModel):
    title: str
    url: str
    content: str
    score: float | None = None
```

| Field | Type | Description |
|---|---|---|
| `title` | `str` | Page title from the search result. Defaults to `""` if absent in the Tavily response. |
| `url` | `str` | Page URL. Defaults to `""` if absent. |
| `content` | `str` | Page text excerpt. Defaults to `""` if absent. |
| `score` | `float | None` | Relevance score returned by Tavily, or `None` if not provided. |

### `SearchService`

```python
class SearchService:
    def __init__(self) -> None: ...
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]: ...
```

#### `__init__`

Reads `TAVILY_API_KEY` from the environment via `os.environ["TAVILY_API_KEY"]` and
constructs a `TavilyClient`. Raises `KeyError` immediately if the variable is absent —
fail-fast rather than a silent default.

**Required env var:** `TAVILY_API_KEY`

#### `search(query, max_results=5) -> list[SearchResult]`

Calls `TavilyClient.search(query, max_results=max_results)` and maps the raw Tavily
result dicts to `SearchResult` instances. Any missing field defaults gracefully:
`title`, `url`, and `content` default to `""`, `score` defaults to `None`.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `str` | required | Search query string. |
| `max_results` | `int` | `5` | Maximum number of results to return; passed directly to the Tavily client. |

**Returns:** `list[SearchResult]` — empty list if Tavily returns no `"results"` key.

### Exports

Both classes are exported from `app/services/__init__.py`:

```python
from services.search_service import SearchService, SearchResult
```

---

## ChunkingService

**Source:** `app/services/chunking_service.py`

```python
class ChunkingService:
```

Stateless utility class that splits text or binary documents into overlapping
token-sized chunks. Uses `tiktoken` for token-boundary splitting and `pymupdf`
(`fitz`) for PDF text extraction. Exported from `app/services/__init__.py`.

### Class Constant

```python
_ENCODING = "cl100k_base"
```

Tiktoken encoding used for all tokenisation. `cl100k_base` matches the
tokenizer used by modern OpenAI and Anthropic-adjacent models. Overridable
by subclassing.

### `chunk_text(text, chunk_size=500, overlap=50) -> list[str]`

```python
def chunk_text(
    self, text: str, chunk_size: int = 500, overlap: int = 50
) -> list[str]:
```

Tokenises `text` with tiktoken and produces overlapping chunks on token
boundaries.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `text` | `str` | required | Input text to split. |
| `chunk_size` | `int` | `500` | Maximum number of tokens per chunk. |
| `overlap` | `int` | `50` | Number of tokens shared between adjacent chunks. |

**Returns:** A `list[str]` of decoded text chunks. Returns `[]` for empty
or all-whitespace input that encodes to zero tokens.

**Algorithm:** sliding window with `step = chunk_size - overlap`. The final
window may be shorter than `chunk_size` if tokens are exhausted.

### `chunk_document(content, mime_type, chunk_size=500, overlap=50) -> list[str]`

```python
def chunk_document(
    self,
    content: bytes,
    mime_type: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[str]:
```

Dispatches on `mime_type` to the right parser, then delegates to
`chunk_text()`.

| `mime_type` | Parser |
|---|---|
| `"text/plain"` | `content.decode("utf-8")` |
| `"application/pdf"` | `fitz.open(stream=content, filetype="pdf")` — page texts joined with `"\n"` |

**Raises:** `ValueError` naming the unsupported MIME type for any value other
than `"text/plain"` or `"application/pdf"`.

### Package Export

`ChunkingService` is exported from `app/services/__init__.py`:

```python
from services.chunking_service import ChunkingService
```

---

## TranscriptService

**Source:** `app/services/transcript_service.py`

```python
class TranscriptService:
```

Fetches YouTube video transcripts via `youtube-transcript-api` and returns
clean joined text or overlapping token-sized chunks. Raises descriptive
exceptions instead of returning silent empty strings.

### `_extract_video_id(url) -> str`

```python
def _extract_video_id(self, url: str) -> str:
```

Extracts the 11-character YouTube video ID from a URL using the regex
`(?:v=|youtu\.be/|embed/|shorts/)([a-zA-Z0-9_-]{11})`. Handles the
following URL forms: `watch?v=`, `youtu.be/`, `embed/`, and `shorts/`.

| Parameter | Type | Description |
|---|---|---|
| `url` | `str` | Any YouTube URL containing a video ID. |

**Returns:** The 11-character video ID string.

**Raises:** `ValueError` — "Cannot extract video ID from URL: ..." — if no
video ID can be parsed.

### `fetch_transcript(url) -> str`

```python
def fetch_transcript(self, url: str) -> str:
```

Fetches the transcript for a YouTube video and returns the full text as a
single space-joined string. Delegates video ID extraction to
`_extract_video_id`, then calls `YouTubeTranscriptApi().fetch(video_id)` and
joins all snippet `.text` values.

| Parameter | Type | Description |
|---|---|---|
| `url` | `str` | Any YouTube URL containing a valid video ID. |

**Returns:** Non-empty `str` — the full transcript text.

**Raises:**
- `ValueError` — unsupported URL format (from `_extract_video_id`).
- `RuntimeError` — transcript unavailable (wraps the underlying API exception
  with `from e`) or transcript text is empty after joining.

Never returns a silent empty string.

### `fetch_and_chunk(url, chunk_size=500, overlap=50) -> list[str]`

```python
def fetch_and_chunk(
    self, url: str, chunk_size: int = 500, overlap: int = 50
) -> list[str]:
```

Fetches a transcript via `fetch_transcript` and splits it into overlapping
token-sized chunks by delegating to `ChunkingService.chunk_text`.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `url` | `str` | required | YouTube URL. |
| `chunk_size` | `int` | `500` | Maximum tokens per chunk. |
| `overlap` | `int` | `50` | Tokens shared between adjacent chunks. |

**Returns:** `list[str]` of decoded text chunks (may be empty if transcript
encodes to zero tokens, but `fetch_transcript` prevents empty transcripts
from reaching this point).

### Package Export

`TranscriptService` is exported from `app/services/__init__.py`:

```python
from services.transcript_service import TranscriptService
```

---

## WorkflowRegistry

**Source:** `app/workflows/workflow_registry.py`

```python
from enum import Enum
from workflows.content_pipeline_workflow import ContentPipelineWorkflow
from workflows.customer_care_workflow import CustomerCareWorkflow

class WorkflowRegistry(Enum):
    CUSTOMER_CARE    = CustomerCareWorkflow
    CONTENT_PIPELINE = ContentPipelineWorkflow
```

A plain `Enum` mapping string workflow type identifiers to workflow classes. The
Celery worker resolves the correct `Workflow` subclass by looking up the
`Event.workflow_type` string value against this enum.

### Adding a New Entry

1. Import the new workflow class at the top of the file.
2. Add an enum member whose name matches the intended `workflow_type` string (by
   convention, `UPPER_SNAKE_CASE`).
3. Add an entry to `app/api/schema_registry.py`'s `SCHEMA_MAP` mapping the enum
   member name to the workflow's event schema class. Without this step the generic
   API dispatcher will reject requests for the new workflow with a 422.

```python
# app/workflows/workflow_registry.py
from workflows.my_new_workflow import MyNewWorkflow

class WorkflowRegistry(Enum):
    CUSTOMER_CARE    = CustomerCareWorkflow
    CONTENT_PIPELINE = ContentPipelineWorkflow
    MY_NEW           = MyNewWorkflow
```

```python
# app/api/schema_registry.py
from schemas.my_new_schema import MyNewEventSchema

SCHEMA_MAP: dict[str, type[BaseModel]] = {
    WorkflowRegistry.CUSTOMER_CARE.name:    CustomerCareEventSchema,
    WorkflowRegistry.CONTENT_PIPELINE.name: ContentPipelineEventSchema,
    WorkflowRegistry.MY_NEW.name:           MyNewEventSchema,
}
```

### Naming Convention

The enum member name corresponds to the `workflow_type` column value stored on the
`Event` row. When the API endpoint creates an event, it writes a `workflow_type` string
(e.g., `"MY_NEW"`) into the database. The worker reads that string, looks up
`WorkflowRegistry["MY_NEW"].value`, and instantiates the returned class.

---

## Event SQLAlchemy Model

**Source:** `app/database/event.py`

```python
class Event(Base):
    __tablename__ = "events"
```

Primary persistence record. Stores both the raw inbound payload and the final
workflow output.

### Columns

| Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID(as_uuid=True)` | No (PK) | `uuid.uuid1` | Primary key, UUID v1 generated at insert time. |
| `workflow_type` | `String(150)` | No | — | Matches a `WorkflowRegistry` enum member name. Max 150 characters. |
| `data` | `JSON` | Yes | — | Raw event dict as received from the API endpoint. |
| `task_context` | `JSON` | Yes | — | Serialized `TaskContext` written back after workflow completes. |
| `created_at` | `DateTime` | Yes | `datetime.now` | Set on insert; not updated thereafter. |
| `updated_at` | `DateTime` | Yes | `datetime.now` | Refreshed by SQLAlchemy `onupdate=datetime.now` on every update. |

### Data vs Task Context Population

- `data` is populated by the API endpoint when the event is first received, before
  the Celery task runs. It holds the original request body as-is.
- `task_context` is written back **incrementally** by the worker: a `persist_progress`
  closure (passed as `on_progress` to `Workflow.run()`) assigns the serialized
  `TaskContext` snapshot to `db_event.task_context` and calls `session.flush()` at each
  node boundary, inside the open `db_session` transaction. After `Workflow.run()` returns,
  the worker performs a final authoritative write via `repository.update(obj=db_event)`,
  ensuring the completed `TaskContext` is committed regardless of boundary-flush count.
  See `app/worker/tasks.py`.

**Commit semantics:** The API endpoint stages the `Event` row with `session.add()` +
`session.flush()` (assigns `event.id` without committing), then calls `send_task()`.
If `send_task()` raises, `db_session()` rolls back the open transaction automatically —
no orphaned row is possible. On success, `db_session()` commits after the route handler
returns. See `app/api/endpoint.py`.

### Session and Base

`Event` inherits from `Base = declarative_base()` defined in `app/database/session.py`.
The engine is created lazily on first use: `db_session()` calls `_get_engine()`, which
initialises `_ENGINE` (a module-level sentinel, initially `None`) to a live
`create_engine(...)` instance on the first call. Importing `session.py` does not
trigger a database connection.

---

## createworkflow CLI

**Source:** `app/core/commands/init_workflow.py`

### Invocation

```bash
# From the repo root
uv run createworkflow
```

The entry point is registered as `createworkflow` in `pyproject.toml`. Running it
invokes `WorkflowInitCommand().run()`, which prompts interactively for the workflow
name.

### Input Validation

The command accepts a `snake_case` name at the prompt. Rules:

- Must match `^[a-z][a-z0-9_]*[a-z0-9]$`.
- Any trailing `_workflow` or `workflow` suffix is stripped automatically before
  validation (e.g., `ticket_workflow` becomes `ticket`).
- The loop re-prompts until a valid name is entered.

### What `WorkflowInitCommand.run()` Generates

Four files are created. Existing files are skipped (never overwritten).

#### 1. `app/workflows/<name>_workflow_nodes/__init__.py`

Empty file. Creates the nodes subpackage.

#### 2. `app/workflows/<name>_workflow_nodes/initial_node.py`

```python
from core.nodes.base import Node
from core.task import TaskContext


class InitialNode(Node):
    def process(self, task_context: TaskContext) -> TaskContext:
        return task_context
```

A pass-through stub. Replace the body with real processing logic.

#### 3. `app/workflows/<name>_workflow.py`

```python
from core.schema import WorkflowSchema, NodeConfig
from core.workflow import Workflow
from schemas.<name>_schema import <Name>EventSchema
from workflows.<name>_workflow_nodes.initial_node import InitialNode


class <Name>Workflow(Workflow):
    workflow_schema = WorkflowSchema(
        description="",
        event_schema=<Name>EventSchema,
        start=InitialNode,
        nodes=[
            NodeConfig(
                node=InitialNode,
                connections=[],
                description="",
                parallel_nodes=[],
            ),
        ],
    )
```

#### 4. `app/schemas/<name>_schema.py`

```python
from pydantic import BaseModel


class <Name>EventSchema(BaseModel):
    pass
```

### Required Edits After Scaffolding

The scaffolded files are stubs. The following steps must be completed before the
workflow is functional:

| Step | Action |
|---|---|
| 1 | Add fields to `<Name>EventSchema` in `app/schemas/<name>_schema.py`. |
| 2 | Add real node files under `app/workflows/<name>_workflow_nodes/`. |
| 3 | Wire `WorkflowSchema`: set `start`, populate `nodes` with real `NodeConfig` entries and their `connections`. |
| 4 | Register in `app/workflows/workflow_registry.py`: import the class and add an enum member. |
| 4a | Add the event schema to `app/api/schema_registry.py` `SCHEMA_MAP` (see [WorkflowRegistry — Adding a New Entry](#adding-a-new-entry)). |
| 5 | Add at least one `.j2` prompt file in `app/prompts/` for every system prompt the workflow uses. |
| 6 | Write tests before marking the workflow complete (see `planning/Test_Plan.md`). |

---

## API Layer

**Sources:** `app/api/models.py`, `app/api/health.py`, `app/api/schema_registry.py`, `app/api/endpoint.py`, `app/api/graph.py`

The API layer exposes a generic dispatch endpoint, read-only workflow graph introspection
endpoints, and a health endpoint. All request and response types are typed Pydantic
models — no raw `dict` responses.

### `EventPayload`

**Source:** `app/api/models.py`

```python
class EventPayload(BaseModel):
    workflow_type: str
    data: dict
```

The inbound request body for `POST /events`. `workflow_type` must match an entry in
`SCHEMA_MAP` (see below). `data` is validated against the resolved workflow-specific
event schema before dispatch.

| Field | Type | Description |
|---|---|---|
| `workflow_type` | `str` | Must match a `WorkflowRegistry` enum member name (e.g. `"CONTENT_PIPELINE"`). |
| `data` | `dict` | Raw event payload; validated against the workflow's event schema class. |

### `TaskAcceptedResponse`

**Source:** `app/api/models.py`

```python
class TaskAcceptedResponse(BaseModel):
    task_id: str
    message: str
```

Typed 202 response body returned by `POST /events` on successful dispatch.

| Field | Type | Description |
|---|---|---|
| `task_id` | `str` | The Celery task UUID assigned to the dispatched workflow run. |
| `message` | `str` | Human-readable confirmation string. |

### `WorkflowListResponse`

**Source:** `app/api/models.py`

```python
class WorkflowListResponse(BaseModel):
    workflows: list[str]
```

Typed 200 response body for `GET /workflows`. Contains all registered workflow type
names as strings (matching `WorkflowRegistry` enum member names).

| Field | Type | Description |
|---|---|---|
| `workflows` | `list[str]` | Registered workflow type names (e.g. `["CUSTOMER_CARE", "CONTENT_PIPELINE"]`). |

### `WorkflowGraphResponse`

**Source:** `app/api/models.py`

```python
class WorkflowGraphResponse(BaseModel):
    nodes: list[str]
    edges: list[tuple[str, str]]
```

Typed 200 response body for `GET /workflows/{workflow_type}/graph`. Serializes the
static `WorkflowSchema` DAG as a node list and an edge list. Node identity uses each
node class's `__name__`, which aligns with `task_context.node_runs` keys at runtime.

| Field | Type | Description |
|---|---|---|
| `nodes` | `list[str]` | Ordered list of node class names in the workflow DAG. |
| `edges` | `list[tuple[str, str]]` | Directed edges as `(source_node_name, target_node_name)` pairs. |

### `HealthResponse`

**Source:** `app/api/health.py`

```python
class HealthResponse(BaseModel):
    status: str
    version: str
```

Typed 200 response body for `GET /health`.

| Field | Type | Description |
|---|---|---|
| `status` | `str` | Always `"ok"` when the service is running. |
| `version` | `str` | Application version string (e.g. `"0.1.0"`). |

### `GET /health`

**Source:** `app/api/health.py`

```
GET /health → 200 HealthResponse(status="ok", version="0.1.0")
```

No authentication required. Returns immediately without touching the database or
message broker. Use this endpoint for liveness probes.

### `GET /workflows`

**Source:** `app/api/graph.py`

```
GET /workflows → 200 WorkflowListResponse(workflows=["CUSTOMER_CARE", "CONTENT_PIPELINE", ...])
```

Returns the names of all registered workflow types from `WorkflowRegistry`. No
authentication required. Does not touch the database or message broker.

### `GET /workflows/{workflow_type}/graph`

**Source:** `app/api/graph.py`

```
GET /workflows/CUSTOMER_CARE/graph → 200 WorkflowGraphResponse(nodes=[...], edges=[...])
GET /workflows/UNKNOWN/graph      → 404 {"detail": "Unknown workflow_type: 'UNKNOWN'"}
```

Returns the static `WorkflowSchema` DAG for the given workflow type as a node list and
edge list. Node names match the class `__name__` values used as keys in
`task_context.node_runs` at runtime, so the static graph can be correlated with live
execution state.

Responds with `404` if `workflow_type` does not match any registered `WorkflowRegistry`
member.

### `SCHEMA_MAP`

**Source:** `app/api/schema_registry.py`

```python
SCHEMA_MAP: dict[str, type[BaseModel]] = {
    WorkflowRegistry.CUSTOMER_CARE.name:    CustomerCareEventSchema,
    WorkflowRegistry.CONTENT_PIPELINE.name: ContentPipelineEventSchema,
}
```

Maps `WorkflowRegistry` enum member names (strings) to their corresponding event
schema classes. The generic dispatcher in `endpoint.py` resolves the correct schema
by looking up `payload.workflow_type` in this dict.

**Every new workflow must add an entry here.** If the entry is missing, requests for
that `workflow_type` return `422 Unprocessable Entity` with a descriptive error
message. See [WorkflowRegistry — Adding a New Entry](#adding-a-new-entry) for the
complete checklist.
