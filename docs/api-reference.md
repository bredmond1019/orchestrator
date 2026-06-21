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
19. [SummarizerNode](#summarizernode)
20. [LearningArtifact SQLAlchemy Model](#learningartifact-sqlalchemy-model)
21. [StorageNode](#storagenode)
22. [digest_renderer](#digest_renderer)
23. [createworkflow CLI](#createworkflow-cli)
24. [API Layer](#api-layer)

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
    OPENAI           = "openai"
    AZURE_OPENAI     = "azure_openai"
    ANTHROPIC        = "anthropic"
    GEMINI           = "gemini"
    OLLAMA           = "ollama"
    BEDROCK          = "bedrock"
    CLAUDE_CODE_SDK  = "claude_code_sdk"
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
    task_context.nodes[self.node_name] = {"next_node": next_node.node_name if next_node else None}
    return task_context
```

Writes the routing decision as `{"next_node": "<ClassName>"}` (or `{"next_node": null}` when the
router terminates a branch) under the router's own key in `task_context.nodes`, then returns the
context. When `route()` returns `None` (e.g. `BlogDecisionRouterNode` on the digest-only path),
`next_node.node_name` would crash — the guard records `None` instead and lets the workflow engine
handle termination via `_handle_router()` returning `None`.

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

## Content Pipeline Nodes (Phase 1 Project A — Task 3)

**Source:** `app/workflows/content_pipeline_workflow_nodes/`

Three nodes implement URL classification and content fetching for the content ingestion pipeline.

### `SourceRouterNode`

**Source:** `app/workflows/content_pipeline_workflow_nodes/source_router_node.py`

```python
class SourceRouterNode(BaseRouter):
    def __init__(self):
        self.routes = [YouTubeRouter()]
        self.fallback = FetchArticleNode()
```

Classifies `event.url` by hostname and routes to the appropriate fetch node. Follows
the `BaseRouter` / `RouterNode` shape (`ticket_router_node.py` reference pattern).

- **YouTube** (`youtube.com`, `youtu.be`, any subdomain) → `FetchTranscriptNode`
- **All other URLs** → `FetchArticleNode` (fallback)

Unparseable or empty hostnames fall through to the article fallback — they never raise.

#### `YouTubeRouter`

```python
class YouTubeRouter(RouterNode):
    def determine_next_node(self, task_context: TaskContext) -> Node | None:
```

The single `RouterNode` rule in `SourceRouterNode.routes`. Uses
`urllib.parse.urlparse(...).hostname` plus a suffix check (avoids matching a URL that
merely contains "youtube.com" in its path). Returns `FetchTranscriptNode()` on match,
`None` otherwise.

---

### `FetchTranscriptNode`

**Source:** `app/workflows/content_pipeline_workflow_nodes/fetch_transcript_node.py`

```python
class FetchTranscriptNode(Node):
    def process(self, task_context: TaskContext) -> TaskContext:
```

Fetches the YouTube transcript for `event.url` via `TranscriptService().fetch_transcript(url)`.

#### Node output keys

| Key | Type | Value |
|---|---|---|
| `text` | `str` | Raw transcript text on success; `""` on failure |
| `title` | `None` | Always `None` — shape-parity with `FetchArticleNode` |
| `fetch_status` | `str` | `"ok"` on success; `"failed"` if the service raises |

`ValueError` (bad URL) and `RuntimeError` (no transcript / empty) from `TranscriptService`
are caught and recorded as `fetch_status="failed"`. The pipeline continues normally.
Unexpected exceptions propagate.

---

### `FetchArticleNode`

**Source:** `app/workflows/content_pipeline_workflow_nodes/fetch_article_node.py`

```python
class FetchArticleNode(Node):
    def process(self, task_context: TaskContext) -> TaskContext:
```

Extracts readable article text from `event.url` via
`ArticleExtractionService().extract(url)`. The service uses trafilatura first, then
Firecrawl as a fallback for JS-heavy pages (D24). It **never raises** — it always
returns an `ArticleResult`.

#### Node output keys

| Key | Type | Value |
|---|---|---|
| `text` | `str` | Extracted article text (may be `""` on failure) |
| `title` | `str \| None` | Page title when extractable; `None` otherwise |
| `fetch_status` | `str` | `"ok"`, `"fallback_used"` (Firecrawl path), or `"failed"` |

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

## ClaudeResult

**Source:** `app/services/claude_code/backend.py`

```python
@dataclass
class ClaudeResult:
    model: str
    text: str | None = None
    structured: Any | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    session_id: str | None = None
```

The uniform return type for every `ClaudeCodeBackend` implementation. One instance
represents one completed LLM turn.

| Field | Type | Description |
|---|---|---|
| `model` | `str` | The model identifier reported by the backend (required). |
| `text` | `str \| None` | Free-text output from the LLM turn. Populated for text runs; `None` for structured-output runs. |
| `structured` | `Any \| None` | Parsed structured output when a JSON schema was requested; `None` otherwise. Mutually exclusive with `text` in practice. |
| `input_tokens` | `int \| None` | Input tokens consumed, as reported by the SDK's terminal `ResultMessage`. `None` if the backend cannot report them. |
| `output_tokens` | `int \| None` | Output tokens generated. `None` if the backend cannot report them. |
| `cost_usd` | `float \| None` | Client-side cost estimate in USD from the SDK. `None` if unavailable. |
| `session_id` | `str \| None` | Session identifier from the underlying Claude Code session, when available. |

### Package Export

`ClaudeResult` is exported from `app/services/claude_code/__init__.py`:

```python
from services.claude_code import ClaudeResult
```

---

## ClaudeCodeBackend

**Source:** `app/services/claude_code/backend.py`

```python
@runtime_checkable
class ClaudeCodeBackend(Protocol):
    async def run(
        self,
        prompt: str,
        *,
        system: str | None,
        model: str,
        schema: dict | None,
    ) -> ClaudeResult: ...
```

A `typing.Protocol` defining the pluggable seam between `ClaudeCodeModel` (a
pydantic-ai `Model`) and its underlying execution engine. Decorated with
`@runtime_checkable` so backends and tests can assert conformance with
`isinstance(obj, ClaudeCodeBackend)`.

Concrete implementations:

| Class | Source | Description |
|---|---|---|
| `ClaudeAgentSdkBackend` | `app/services/claude_code/sdk_backend.py` | Drives the official `claude-agent-sdk`, forces subscription auth by blanking `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` in the spawned CLI env. |

### `run(prompt, *, system, model, schema) -> ClaudeResult`

| Parameter | Type | Description |
|---|---|---|
| `prompt` | `str` | The user-facing prompt for this turn. |
| `system` | `str \| None` | Optional system prompt; `None` means no system prompt override. |
| `model` | `str` | Model alias or full model name to pass to the backend. |
| `schema` | `dict \| None` | JSON schema for structured output, or `None` for free-text output. |

Returns a `ClaudeResult` carrying the output and usage metadata.

### Package Export

`ClaudeCodeBackend` is exported from `app/services/claude_code/__init__.py`:

```python
from services.claude_code import ClaudeCodeBackend
```

---

## ClaudeAgentSdkBackend

**Source:** `app/services/claude_code/sdk_backend.py`

```python
class ClaudeAgentSdkBackend:
    async def run(
        self,
        prompt: str,
        *,
        system: str | None,
        model: str,
        schema: dict | None,
    ) -> ClaudeResult: ...
```

Concrete implementation of the `ClaudeCodeBackend` protocol that delegates to
`claude_agent_sdk.query()`. The spawned `claude` CLI is forced onto the Claude
Code **subscription** (not metered API credits) by blanking `ANTHROPIC_API_KEY`
and `ANTHROPIC_AUTH_TOKEN` in the child process environment. All configuration is
read from `CLAUDE_CODE_*` env vars at call time (see `docs/configuration.md`).

### Behaviour

1. Builds `ClaudeAgentOptions` from env vars (`CLAUDE_CODE_BIN`,
   `CLAUDE_CODE_CWD`, `CLAUDE_CODE_PERMISSION_MODE`) and the call parameters
   (`model`, `system`, `schema`).
2. Calls `query()` inside `asyncio.wait_for` with a timeout from
   `CLAUDE_CODE_SDK_TIMEOUT_SECONDS` (default `180` seconds).
3. Drains the async stream, keeping the last `ResultMessage` as the terminal
   result.
4. Raises `RuntimeError` on: timeout, no terminal result, non-`success` subtype,
   or `is_error=True` — all with a descriptive message including `subtype`,
   `is_error`, `api_error_status`, and `errors`.
5. Maps a successful `ResultMessage` into `ClaudeResult`:

| `ResultMessage` field | `ClaudeResult` field |
|---|---|
| `result` | `text` |
| `structured_output` | `structured` |
| `usage["input_tokens"]` | `input_tokens` |
| `usage["output_tokens"]` | `output_tokens` |
| `total_cost_usd` | `cost_usd` |
| `session_id` | `session_id` |
| _(call parameter)_ `model` | `model` |

### Environment Variables

See `docs/configuration.md` for the full table. Summary:

| Variable | Default | Purpose |
|---|---|---|
| `CLAUDE_CODE_BIN` | `claude` (on `$PATH`) | Path to the `claude` binary |
| `CLAUDE_CODE_CWD` | process cwd | Working directory for the subprocess |
| `CLAUDE_CODE_PERMISSION_MODE` | `bypassPermissions` | SDK permission mode |
| `CLAUDE_CODE_SDK_TIMEOUT_SECONDS` | `180` | Per-call timeout in seconds |
## ClaudeCodeModel

**Source:** `app/services/claude_code/model.py`

```python
class ClaudeCodeModel(pydantic_ai.models.Model):
    def __init__(self, backend: ClaudeCodeBackend, model_name: str) -> None: ...
```

A pydantic-ai `Model` implementation that delegates one LLM turn to a
`ClaudeCodeBackend`. It is the seam between pydantic-ai's `Agent` machinery
and the pluggable Claude Code execution engine. Constructed with a concrete
backend and the requested model name (a Claude alias such as `"opus"` or a
full id like `"claude-opus-4-8"`).

**When to use:** Pass a `ClaudeCodeModel` instance to `AgentNode` via the
`model_instance` parameter instead of relying on a `ModelProvider` enum when
you need to drive an LLM call through the Claude Code SDK backend.

### Properties

| Property | Return Type | Description |
|---|---|---|
| `model_name` | `str` | The requested Claude model name (alias or full id) as passed to the constructor. |
| `system` | `str` | Always `"claude-code"` — the provider identifier surfaced to pydantic-ai telemetry. |
| `base_url` | `str \| None` | Always `None` — the backend shells out to the Claude Code engine; no HTTP base URL is used. |

### `request(messages, model_settings, model_request_parameters) -> tuple[ModelResponse, Usage]`

Executes one turn via the backend and adapts the result to pydantic-ai 0.1.5.

| Parameter | Type | Description |
|---|---|---|
| `messages` | `list[ModelMessage]` | The full message history for this turn. `SystemPromptPart` and `UserPromptPart` contents are extracted; all other message types are ignored. |
| `model_settings` | `ModelSettings \| None` | Forwarded for interface compatibility; not used by this implementation. |
| `model_request_parameters` | `ModelRequestParameters` | Carries `output_tools`; when non-empty the first tool's `parameters_json_schema` is passed to the backend as `schema`. |

**Output path — structured:** when `model_request_parameters.output_tools` is non-empty, calls
`backend.run(..., schema=<first output tool's JSON schema>)` and returns a
`ToolCallPart(tool_name=output_tool.name, args=result.structured or json.loads(result.text))`.

**Output path — text:** when `output_tools` is empty, calls `backend.run(..., schema=None)` and
returns a `TextPart(content=result.text or "")`.

In both cases `Usage(requests=1, request_tokens=..., response_tokens=...)` is built from the
backend result's token fields.

### `request_stream(...)`

Raises `NotImplementedError` immediately. Streaming is documented future work and is out of scope
for the Claude Code provider.

### `customize_request_parameters(model_request_parameters) -> ModelRequestParameters`

Returns the parameters unchanged. No provider-specific rewriting is needed.

### `_get_instructions(messages) -> None`

Returns `None`. System text is extracted from `SystemPromptPart` elements inside `request`;
no model-level instruction injection is performed.

### Package Export

`ClaudeCodeModel`, `ClaudeAgentSdkBackend`, `ClaudeCodeBackend`, and `ClaudeResult` are all exported from `app/services/claude_code/__init__.py`:

```python
from services.claude_code import ClaudeCodeModel
from services.claude_code import ClaudeAgentSdkBackend
from services.claude_code import ClaudeCodeBackend, ClaudeResult
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

## SummarizerNode

**Source:** `app/workflows/content_pipeline_workflow_nodes/summarizer_node.py`

```python
class SummarizerNode(AgentNode):
```

Concrete `AgentNode` that turns fetched source text (from `FetchTranscriptNode` or
`FetchArticleNode`) into a structured `SummaryOutput`. Produces the per-artifact
summary stored on `LearningArtifact.summary` and consumed by `StorageNode` (Task 5).

### `SummaryOutput`

```python
class SummaryOutput(AgentNode.OutputType):
```

Module-level Pydantic model that is also assigned as `SummarizerNode.OutputType`.
Exported from this module so downstream nodes (e.g. `StorageNode`) can import it
without creating a circular dependency.

| Field | Type | Description |
|---|---|---|
| `title` | `str` | Clean, human-readable title for the artifact. |
| `category` | `str` | Free-form category string; preferred values: `ai_engineering`, `physics_relativity`, `music`, `other`. |
| `tl_dr` | `str` | One-line core takeaway. |
| `read_time_estimate` | `str` | Short human read-time estimate, e.g. `'6 min'`. |
| `core_concepts` | `list[str]` | Key ideas the source teaches. |
| `key_insights` | `list[str]` | Non-obvious, memorable points worth retaining. |
| `questions_raised` | `list[str]` | Open questions the source provokes. |
| `connections_to_my_work` | `list[str]` | Explicit links to Brandon's agentic-engineering / AI-architecture work. |
| `further_exploration` | `list[str]` | Concrete next things to read, watch, or try. |

### `get_agent_config() -> AgentConfig`

```python
def get_agent_config(self) -> AgentConfig:
    return AgentConfig(
        system_prompt=PromptManager().get_prompt("content_summarizer"),
        output_type=SummaryOutput,
        deps_type=None,
        model_provider=ModelProvider.ANTHROPIC,
        model_name="claude-opus-4-8",
    )
```

Loads the system prompt from `app/prompts/content_summarizer.j2` via `PromptManager`.
Uses `ModelProvider.ANTHROPIC` with `claude-opus-4-8` (top-tier Anthropic model per
the D19 model strategy). No prompt text is hardcoded in Python.

### `process(task_context) -> TaskContext`

Reads the upstream fetched text from whichever fetch node ran (via
`_read_source_text()`), calls `self.run_agent_recorded(task_context, source_text)`
for per-node token telemetry, and stores the resulting `SummaryOutput` under the
node's `result` key via `task_context.update_node()`.

If no fetch node produced text (e.g. a failed fetch), `process()` passes an empty
string to the agent rather than raising — the pipeline continues with a best-effort
summary of an empty source.

### `_read_source_text(task_context) -> str`

Iterates `_FETCH_NODE_NAMES = ("FetchTranscriptNode", "FetchArticleNode")` in
priority order and returns the first non-empty `text` value found in
`task_context.nodes`. Returns `""` if no text is available.

### System Prompt

`app/prompts/content_summarizer.j2` — biased toward agentic/harness/AI-architecture
and RAG-memory topics; personal categories include physics/relativity and music.
No prompt text is stored in Python; all prompt content lives in the `.j2` file.

---

## Content Pipeline Blog Branch Nodes (Phase 1 Project A — Task 6)

**Source:** `app/workflows/content_pipeline_workflow_nodes/`

Four nodes implement the optional blog-generation branch for the content pipeline.
The branch is gated by `event.make_blog`: when false, the pipeline ends after storage;
when true it runs `BlogWriterNode → SelfCriticNode → ReviseNode` (linear, no cycle).

---

### `BlogDecisionRouterNode`

**Source:** `app/workflows/content_pipeline_workflow_nodes/blog_decision_router_node.py`

```python
class BlogDecisionRouterNode(BaseRouter):
    def __init__(self):
        self.routes = [MakeBlogRouter()]
        self.fallback = None
```

Routes to `BlogWriterNode` when `event.make_blog` is `True`; has no fallback so
`BaseRouter.route` returns `None` on the false path (digest-only run terminates after
the storage step). Follows the `ticket_router_node.py` reference pattern.

#### `MakeBlogRouter`

```python
class MakeBlogRouter(RouterNode):
    def determine_next_node(self, task_context: TaskContext) -> Node | None:
```

The single `RouterNode` rule in `BlogDecisionRouterNode.routes`. Returns
`BlogWriterNode()` when `task_context.event.make_blog` is truthy; `None` otherwise.

---

### `BlogWriterNode`

**Source:** `app/workflows/content_pipeline_workflow_nodes/blog_writer_node.py`

```python
class BlogWriterNode(AgentNode):
```

First node of the blog branch. Converts the structured `SummaryOutput` produced by
`SummarizerNode` into a draft blog post written in Brandon's voice.

#### `OutputType`

| Field | Type | Description |
|---|---|---|
| `title` | `str` | Clear, specific title for the blog post. |
| `body_markdown` | `str` | Full post body in Markdown. |
| `reasoning` | `str` | Short note on the chosen angle and structure. |

#### `get_agent_config() -> AgentConfig`

Loads `app/prompts/blog_writer.j2` via `PromptManager`; uses `ModelProvider.ANTHROPIC`
with `claude-opus-4-8`. No prompt text is hardcoded in Python.

#### `process(task_context) -> TaskContext`

Reads `SummarizerNode`'s `result` (a `SummaryOutput`) via
`task_context.get_node_output("SummarizerNode")["result"]`, serialises it with
`model_dump_json()`, calls `run_agent_recorded()`, and stores the `OutputType` instance
under this node's `result` key.

### System Prompt

`app/prompts/blog_writer.j2` — instructs the agent to write in Brandon's voice; voice
guidance is intended to be reused by Project C.

---

### `SelfCriticNode`

**Source:** `app/workflows/content_pipeline_workflow_nodes/self_critic_node.py`

```python
class SelfCriticNode(AgentNode):
```

Second node of the blog branch. Critiques the `BlogWriterNode` draft for clarity,
accuracy against the source summary, voice consistency, and structure.

#### `OutputType`

| Field | Type | Description |
|---|---|---|
| `critique` | `str` | Short overall assessment of the draft. |
| `issues` | `list[str]` | Concrete, actionable problems found in the draft (default `[]`). |
| `approved` | `bool` | `True` only when the draft has no material issues (default `False`). |

#### `get_agent_config() -> AgentConfig`

Loads `app/prompts/blog_self_critic.j2` via `PromptManager`; uses
`ModelProvider.ANTHROPIC` with `claude-opus-4-8`.

#### `process(task_context) -> TaskContext`

Reads `BlogWriterNode`'s `result` via `get_node_output("BlogWriterNode")["result"]`,
serialises it, calls `run_agent_recorded()`, and stores the critique `OutputType`.

### System Prompt

`app/prompts/blog_self_critic.j2` — critique criteria: clarity, accuracy vs. source,
voice consistency, structure.

---

### `ReviseNode`

**Source:** `app/workflows/content_pipeline_workflow_nodes/revise_node.py`

```python
class ReviseNode(AgentNode):
```

Terminal node of the blog branch (no downstream connection). Applies the
`SelfCriticNode` critique to the `BlogWriterNode` draft and produces the final revised
post. Threads both draft and critique into one JSON user prompt.

#### `OutputType`

| Field | Type | Description |
|---|---|---|
| `title` | `str` | Revised (or unchanged) post title. |
| `body_markdown` | `str` | Full revised post body in Markdown. |

#### `get_agent_config() -> AgentConfig`

Loads `app/prompts/blog_reviser.j2` via `PromptManager`; uses
`ModelProvider.ANTHROPIC` with `claude-opus-4-8`.

#### `process(task_context) -> TaskContext`

Reads `BlogWriterNode` draft and `SelfCriticNode` critique via `get_node_output()`,
builds a combined `{"draft": ..., "critique": ...}` JSON user prompt,
calls `run_agent_recorded()`, and stores the revised `OutputType`.

### System Prompt

`app/prompts/blog_reviser.j2` — instructs the agent to apply critique changes while
preserving Brandon's voice; frontmatter included for `PromptManager` rendering.

---

## LearningArtifact SQLAlchemy Model

**Source:** `app/database/learning_artifact.py`

```python
class LearningArtifact(Base):
    __tablename__ = "learning_artifacts"
```

Persistence record for a single ingested source (YouTube transcript or extracted article).
Produced by the content pipeline (Phase 1, Project A). Each ingested item yields exactly
one row, carrying source provenance, a structured summary, and a 1024-dim pgvector embedding
written at storage time.

**Module-level constant:** `EMBEDDING_DIM = 1024`

### Columns

| Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID(as_uuid=True)` | No (PK) | `uuid.uuid4` | Primary key, UUID v4 generated at insert time. |
| `source_url` | `String(2048)` | No | — | Original YouTube or article URL that was ingested. |
| `source_type` | `String(50)` | Yes | — | Source classification: `'youtube'` or `'article'`. |
| `title` | `String(512)` | Yes | — | Human-readable title of the source content. |
| `category` | `String(150)` | Yes | — | Classified category (e.g. `'ai_engineering'`, `'physics_relativity'`). |
| `tl_dr` | `String` | Yes | — | One-line summary of the content. |
| `summary` | `JSON` | Yes | — | Full structured `SummaryOutput` as JSON. |
| `embedding` | `Vector(1024)` | Yes | — | 1024-dim embedding of the summary text (pgvector), written by the StorageNode. |
| `fetch_status` | `String(50)` | Yes | — | Outcome of the fetch step: `'ok'`, `'fallback_used'`, or `'failed'`. |
| `make_blog` | `Boolean` | Yes | `False` | Whether a blog draft was requested for this artifact. |
| `created_at` | `DateTime` | Yes | `datetime.now` | Set on insert; not updated thereafter. |

### Migration

The `learning_artifacts` table is created by migration `a1b2c3d4e5f6`
(`app/alembic/versions/a1b2c3d4e5f6_create_learning_artifacts_table.py`).
`down_revision = '12a5c7643ab9'` — chains off the pgvector extension migration.
The `pgvector` package (`pgvector>=0.3.0`) must be installed (added to `pyproject.toml`
in Phase 1 Project A Task 2).

### Session and Base

`LearningArtifact` inherits from `Base = declarative_base()` defined in
`app/database/session.py`. The model is imported in `app/alembic/env.py`
(`from database.learning_artifact import *`) so Alembic autogenerate sees its metadata.

---

## StorageNode

**Source:** `app/workflows/content_pipeline_workflow_nodes/storage_node.py`

```python
class StorageNode(Node):
```

Concrete `Node` that closes the content pipeline: for every ingested item it (a) embeds the
summary text at write time via `EmbeddingService`, (b) persists a `LearningArtifact` row through
`GenericRepository` using the shared `db_session` factory (no connection string or deployment
path lives inside the node — rule 7), and (c) writes a static HTML digest page and regenerates
the category index. The output directory comes from the `CONTENT_DIGEST_DIR` env var.

### `process(task_context) -> TaskContext`

1. Reads `SummaryOutput` from `task_context.get_node_output("SummarizerNode")["result"]`.
2. Derives `source_type` and `fetch_status` from whichever fetch node ran (via
   `_read_source_meta`).
3. Builds the embedding text as `f"{title}\n{tl_dr}\n{' '.join(core_concepts)}"` and calls
   `EmbeddingService().embed_text(embed_text)` — embedding is produced **at write time** before
   the artifact is persisted.
4. Constructs a `LearningArtifact` with `id=task_context.event.artifact_id` (stable identity
   from the event schema) and calls `self._persist(artifact)`.
5. Calls `render_artifact_page(...)` and `regenerate_category_index(...)` from `digest_renderer`.
6. Records `{"artifact_id", "page", "category", "embedded": True}` via `task_context.update_node()`.

### `_persist(artifact) -> None`

Single persistence seam. Opens the shared `db_session` context manager, creates a
`GenericRepository(session, LearningArtifact)`, and calls `.create(artifact)`. Tests
monkeypatch this method so no real database is touched.

### `_read_source_meta(task_context) -> tuple[str, str]`

Returns `(source_type, fetch_status)` from whichever fetch node ran. A
`FetchTranscriptNode` output implies `source_type="youtube"`; otherwise `"article"`. An
explicit `source_type` key on the fetch output wins. Falls back to `fetch_status="ok"` if
the key is absent.

---

## digest_renderer

**Source:** `app/workflows/content_pipeline_workflow_nodes/digest_renderer.py`

Pure-function static-HTML renderer. Deliberately dumb: no JavaScript, no search, no tagging
(D22 — MVP is ingestion + store + dumb display only). All output paths are supplied by the
caller (config/env), never hardcoded.

### `render_artifact_page(artifact, output_dir, category) -> Path`

```python
def render_artifact_page(artifact: dict, output_dir: Path, category: str) -> Path:
```

Writes a single static HTML page for one artifact and returns its path. The page is written to
`output_dir/<category>/<artifact_id>.html`. Content includes title, TL;DR, read-time estimate,
category, source URL, and the five `SummaryOutput` list fields (`core_concepts`, `key_insights`,
`questions_raised`, `connections_to_my_work`, `further_exploration`). All interpolated values
are HTML-escaped via `_esc`.

| Parameter | Type | Description |
|---|---|---|
| `artifact` | `dict` | Merged dict of `SummaryOutput.model_dump()` plus `artifact_id` and `source_url`. |
| `output_dir` | `Path` | Root digest directory (from `CONTENT_DIGEST_DIR` env via caller). |
| `category` | `str` | Category string; becomes the sub-folder name. |

### `regenerate_category_index(output_dir, category) -> Path`

```python
def regenerate_category_index(output_dir: Path, category: str) -> Path:
```

Rewrites `output_dir/<category>/index.html` listing every artifact page. Globs for `*.html`
(excluding `index.html`), sorts the results, and writes a minimal `<ul>` of links. Called by
`StorageNode.process()` after every artifact write so the index is always current.

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
