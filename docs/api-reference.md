---
type: Reference
title: Core Engine API Reference
description: Class-level reference for the public abstractions in app/core, app/database, app/services, and app/workflows that a developer subclasses when writing a new workflow.
doc_id: api-reference
layer: [engine]
project: orchestrator
status: active
keywords: [API reference, Workflow, TaskContext, AgentNode, WorkflowSchema, NodeConfig]
related: [app-architecture-overview, workflows, getting-started]
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
4. [NodeStatus](#nodestatus)
5. [NodeRun](#noderun)
6. [TaskContext](#taskcontext)
7. [Node](#node)
8. [AgentNode](#agentnode)
9. [ParallelNode](#parallelnode)
10. [BaseRouter and RouterNode](#baserouter-and-routernode)
11. [Content Pipeline Nodes](#content-pipeline-nodes-phase-1-project-a--task-3)
12. [ToolUseNode](#tooluse-node)
13. [GenericRepository](#genericrepository)
14. [PromptManager](#promptmanager)
15. [EmbeddingService](#embeddingservice)
16. [ArticleExtractionService](#articleextractionservice)
17. [SearchService and SearchResult](#searchservice-and-searchresult)
18. [ChunkingService](#chunkingservice)
19. [TranscriptService](#transcriptservice)
20. [ClaudeResult](#clauderesult)
21. [ClaudeCodeBackend](#claudecodebackend)
22. [ClaudeAgentSdkBackend](#claudeagentsdkbackend)
23. [BastionSessionBackend](#bastionsessionbackend)
24. [ClaudeCodeModel](#claudecodemodel)
25. [WorkflowRegistry](#workflowregistry)
26. [Event SQLAlchemy Model](#event-sqlalchemy-model)
27. [SummarizerNode](#summarizernode)
28. [Content Pipeline Blog Branch Nodes](#content-pipeline-blog-branch-nodes-phase-1-project-a--task-6)
29. [ProposalWriterNode](#proposalwriternode)
30. [LearningArtifact SQLAlchemy Model](#learningartifact-sqlalchemy-model)
31. [BrainDocument SQLAlchemy Model](#braindocument-sqlalchemy-model)
32. [BrainEdge SQLAlchemy Model](#brainedge-sqlalchemy-model)
33. [ContentChunk SQLAlchemy Model](#contentchunk-sqlalchemy-model)
34. [ChatSession SQLAlchemy Model](#chatsession-sqlalchemy-model)
35. [StorageNode](#storagenode)
36. [ProposalGenerator StorageNode](#proposalgenerator-storagenode)
37. [digest_renderer](#digest_renderer)
38. [createworkflow CLI](#createworkflow-cli)
39. [API Security and CORS](#api-security-and-cors)
40. [API Layer](#api-layer)
41. [DocumentIngestEventSchema](#documentingesteventschemae)
42. [ParseDocumentNode](#parsedocumentnode)
43. [ChunkDocumentNode](#chunkdocumentnode)
44. [EmbedChunksNode](#embedchunksnode)
45. [DocumentIngest StoreChunksNode](#documentingest-storechnksnode)
46. [DocumentIngestWorkflow](#documentingestworkflow)
47. [RetrieveChunksNode](#retrievechunksnode)
48. [DocumentQAEventSchema](#documentqaeventschemae)
49. [EmbedQuestionNode](#embedquestionnode)
50. [AssembleContextNode](#assemblecontextnode)
51. [AnswerNode](#answernode)
52. [UpdateSessionMemoryNode](#updatesessionmemorynode)
53. [DocumentQAWorkflow](#documentqaworkflow)

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
   Raises `ValueError("Workflow schema contains a cycle")`. Router nodes
   (`NodeConfig.is_router=True`) determine their actual next node at *runtime* via
   `BaseRouter.route()`, not by walking the declared `connections` list, so a
   declared back-edge through a router (e.g. a bounded retry loop) is only a
   *possible* destination, not a structural edge — the DFS skips traversing a
   router node's own `connections` (its incoming edges from upstream nodes are
   still checked normally), letting router-mediated loops pass validation while
   still catching genuine cycles among non-router nodes.

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
    input: Any | None = None
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
| `input` | `Any \| None` | Prompt/messages sent by the node (populated by LLM base classes); JSON-serializable; `None` for non-LLM nodes. |
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
    OPENAI               = "openai"
    AZURE_OPENAI         = "azure_openai"
    ANTHROPIC            = "anthropic"
    GEMINI               = "gemini"
    OLLAMA               = "ollama"
    BEDROCK              = "bedrock"
    CLAUDE_CODE_SDK      = "claude_code_sdk"
    CLAUDE_CODE_SESSION  = "claude_code_session"
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
| `CLAUDE_CODE_SDK` | `ClaudeCodeModel(backend=ClaudeAgentSdkBackend(), model_name=...)` | `CLAUDE_CODE_BIN`, `CLAUDE_CODE_CWD`, `CLAUDE_CODE_PERMISSION_MODE`, `CLAUDE_CODE_SDK_TIMEOUT_SECONDS` |
| `CLAUDE_CODE_SESSION` | `ClaudeCodeModel(backend=BastionSessionBackend(), model_name=...)` | `CLAUDE_CODE_TMUX_SESSION`, `CLAUDE_CODE_WORKDIR`, `CLAUDE_CODE_IO_DIR`, `CLAUDE_CODE_SESSION_TIMEOUT_SECONDS` |

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
    task_context.update_node(
        node_name=self.node_name,
        next_node=next_node.node_name if next_node else None,
    )
    return task_context
```

Writes the routing decision as `{"next_node": "<ClassName>"}` (or `{"next_node": null}` when the
router terminates a branch) under the router's own key in `task_context.nodes`, then returns the
context. When `route()` returns `None` (e.g. `BlogDecisionRouterNode` on the digest-only path),
`next_node.node_name` would crash — the guard records `None` instead and lets the workflow engine
handle termination via `_handle_router()` returning `None`. `process()` writes via
`TaskContext.update_node` (a merge into the existing `{"result": ...}` dict for that node name)
rather than a direct `task_context.nodes[self.node_name] = ...` assignment, so a
`RouterNode.determine_next_node` implementation that stashes its own data on the router's node
name via `update_node` (e.g. `TaskQueueRouterNode` recording the dispatched task's fields under
its own `result` key) is preserved alongside the routing decision instead of being wiped out.

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
| `BastionSessionBackend` | `app/services/claude_code/bastion_backend.py` | Shells out to `bastion ask` to run the turn on a live Claude Code session managed in tmux by the `bastion` binary. Token/cost fields are `None` (session billing, not metered). |

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

---

## BastionSessionBackend

**Source:** `app/services/claude_code/bastion_backend.py`

```python
class BastionSessionBackend:
    async def run(
        self,
        prompt: str,
        *,
        system: str | None,
        model: str,
        schema: dict | None,
    ) -> ClaudeResult: ...
```

Concrete implementation of the `ClaudeCodeBackend` protocol that drives a **live Claude Code
session** managed in tmux by the `bastion` binary. Instead of spawning an ephemeral CLI subprocess,
it writes a prompt file and shells out to `bastion ask`, routing the turn through the session named
by `CLAUDE_CODE_TMUX_SESSION`. This makes each turn observable and attachable via `bastion sessions`.

### Behaviour

1. Resolves the bastion binary: `BASTION_BIN` env var → `shutil.which("bastion")` → falls back to
   the configured value verbatim (supports absolute paths). Raises `RuntimeError` only when `bastion`
   is bare and not found on `$PATH`.
2. Writes a `prompt-<uuid>.md` file to `CLAUDE_CODE_IO_DIR` containing the system prompt (if any)
   followed by the user prompt. When `schema` is not `None`, appends an instruction:
   `"Write ONLY a JSON object conforming to this schema: ..."`.
3. Runs `bastion ask --session <name> --prompt-file <path> --out <answer-path> --dir <workdir>
   --timeout <sec>` off the event loop via `asyncio.get_event_loop().run_in_executor`, preventing
   the async event loop from blocking. A 30-second subprocess timeout buffer is added so the
   in-session `bastion ask` timeout fires first and surfaces its own diagnostics.
4. Parses the answer file: `json.loads` for structured output, raw markdown string for free-text.
5. Returns `ClaudeResult` with `input_tokens`, `output_tokens`, `cost_usd`, and `session_id` all
   `None` (session billing — no per-call usage reporting available in v0.1.0).
6. Raises `RuntimeError` with stderr context on: non-zero exit, missing answer file, timeout, or
   invalid JSON in structured mode. Always removes both temp files in a `finally` block.

### Limitations

- Token usage fields (`input_tokens`, `output_tokens`, `cost_usd`) are always `None`. The
  `model` field in `ClaudeResult` is recorded as passed but is advisory only — the session's model
  is fixed at launch and is not switched per call in v0.1.0.

### Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `BASTION_BIN` | `bastion` (on `$PATH`) | Path to the `bastion` binary |
| `CLAUDE_CODE_TMUX_SESSION` | `orchestrator-claude` | tmux session name `bastion ask` targets |
| `CLAUDE_CODE_WORKDIR` | — | Pre-trusted working directory for the Claude Code session |
| `CLAUDE_CODE_IO_DIR` | `CLAUDE_CODE_WORKDIR` | Directory where prompt/answer temp files are written |
| `CLAUDE_CODE_SESSION_TIMEOUT_SECONDS` | `180` | Per-call timeout in seconds |

---

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

`ClaudeCodeModel`, `ClaudeAgentSdkBackend`, `BastionSessionBackend`, `ClaudeCodeBackend`, and `ClaudeResult` are all exported from `app/services/claude_code/__init__.py`:

```python
from services.claude_code import ClaudeCodeModel
from services.claude_code import ClaudeAgentSdkBackend
from services.claude_code import BastionSessionBackend
from services.claude_code import ClaudeCodeBackend, ClaudeResult
```

### Cross-repo coordination

The `ClaudeCodeBackend` protocol and `ClaudeCodeModel` are deliberately backend-agnostic. The
`CLAUDE_CODE_SESSION` (bastion) mode is implemented as `BastionSessionBackend`
(`app/services/claude_code/bastion_backend.py`) — a second backend that reuses the same protocol
and `ClaudeCodeModel` without any change to either. Provider routing is wired in
`app/core/nodes/agent.py`: `ModelProvider.CLAUDE_CODE_SDK` routes to `ClaudeAgentSdkBackend` and
`ModelProvider.CLAUDE_CODE_SESSION` routes to `BastionSessionBackend`, both through
`ClaudeCodeModel`. The cross-repo design and the contract for the bastion mode live in the
company-brain doc `agentic-portfolio/docs/integrations/claude-code-llm-provider.md`. See also
`docs/configuration.md` for the `CLAUDE_CODE_*` environment variables and host prerequisites.

**External dependency:** `CLAUDE_CODE_SESSION` is the only provider in this repo that shells out
to a binary built in another repo. `BastionSessionBackend.run` invokes the `bastion ask` command
(pinned at **v0.1.0** in §2 of the company-brain doc above) with the exact flag surface
`--session / --prompt-file / --out / --dir / --timeout`. The `bastion` binary must be built and on
the host `$PATH` (or pointed at via `BASTION_BIN`), and its tmux host must be logged into the Claude
Code subscription with the workdir pre-trusted. A mismatch in the `bastion ask` flag contract is a
breaking change for this provider.

**Relationship to the SDK-mode feature:** `CLAUDE_CODE_SESSION` is a sibling of the
`CLAUDE_CODE_SDK` provider added by the `feature-claude-code-sdk-provider` feature
(see [ClaudeAgentSdkBackend](#claudeagentsdkbackend)). Both ride the same `ClaudeCodeModel` +
`ClaudeCodeBackend` protocol; they differ only in how the turn is executed. SDK mode spawns an
**ephemeral** `claude` CLI subprocess (metered usage available); session mode routes the turn
through a **live, observable** tmux session via `bastion ask` (usage fields are `None` — session
billing). Choose SDK mode for fire-and-forget turns and session mode when the run must be visible
and attachable in `bastion sessions`.

---

## WorkflowRegistry

**Source:** `app/workflows/workflow_registry.py`

```python
from enum import Enum
from workflows.content_pipeline_workflow import ContentPipelineWorkflow
from workflows.customer_care_workflow import CustomerCareWorkflow
from workflows.document_ingest_workflow import DocumentIngestWorkflow
from workflows.document_qa_workflow import DocumentQAWorkflow
from workflows.proposal_generator_workflow import ProposalGeneratorWorkflow
from workflows.research_agent_workflow import ResearchAgentWorkflow

class WorkflowRegistry(Enum):
    CUSTOMER_CARE    = CustomerCareWorkflow
    CONTENT_PIPELINE = ContentPipelineWorkflow
    RESEARCH_AGENT   = ResearchAgentWorkflow
    PROPOSAL_GENERATOR = ProposalGeneratorWorkflow
    DOCUMENT_INGEST  = DocumentIngestWorkflow
    DOCUMENT_QA      = DocumentQAWorkflow
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
        model_provider=ModelProvider.CLAUDE_CODE_SDK,
        model_name="sonnet",
    )
```

Loads the system prompt from `app/prompts/content_summarizer.j2` via `PromptManager`.
Uses `ModelProvider.CLAUDE_CODE_SDK` with `"sonnet"` (subscription-billing default;
revert to `ModelProvider.ANTHROPIC` / `"claude-opus-4-8"` per-node when metered API
billing is needed). No prompt text is hardcoded in Python.

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

Five nodes implement the optional blog-generation branch for the content pipeline.
The branch is gated by `event.make_blog`: when false, the pipeline ends after storage;
when true it runs `BlogWriterNode → SelfCriticNode → ReviseNode → TranslatePtBrNode`
(linear, no cycle).

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

Loads `app/prompts/blog_writer.j2` via `PromptManager`; uses `ModelProvider.CLAUDE_CODE_SDK`
with `"sonnet"` (subscription-billing default; revert to `ModelProvider.ANTHROPIC` /
`"claude-opus-4-8"` per-node for metered API billing). No prompt text is hardcoded in Python.

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
`ModelProvider.CLAUDE_CODE_SDK` with `"sonnet"` (subscription-billing default; revert
to `ModelProvider.ANTHROPIC` / `"claude-opus-4-8"` per-node for metered API billing).

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

Applies the `SelfCriticNode` critique to the `BlogWriterNode` draft and produces the
final revised English post, then connects to `TranslatePtBrNode`. Threads both draft
and critique into one JSON user prompt.

#### `OutputType`

| Field | Type | Description |
|---|---|---|
| `title` | `str` | Revised (or unchanged) post title. |
| `body_markdown` | `str` | Full revised post body in Markdown. |

#### `get_agent_config() -> AgentConfig`

Loads `app/prompts/blog_reviser.j2` via `PromptManager`; uses
`ModelProvider.CLAUDE_CODE_SDK` with `"sonnet"` (subscription-billing default; revert
to `ModelProvider.ANTHROPIC` / `"claude-opus-4-8"` per-node for metered API billing).

#### `process(task_context) -> TaskContext`

Reads `BlogWriterNode` draft and `SelfCriticNode` critique via `get_node_output()`,
builds a combined `{"draft": ..., "critique": ...}` JSON user prompt,
calls `run_agent_recorded()`, and stores the revised `OutputType`.

### System Prompt

`app/prompts/blog_reviser.j2` — instructs the agent to apply critique changes while
preserving Brandon's voice; frontmatter included for `PromptManager` rendering.

---

### `TranslatePtBrNode`

**Source:** `app/workflows/content_pipeline_workflow_nodes/translate_ptbr_node.py`

```python
class TranslatePtBrNode(AgentNode):
```

Terminal node of the blog branch (no downstream connection). Translates the finished
English post from `ReviseNode` into Brazilian Portuguese (pt-BR) so a published post
serves the brand's PT+EN cadence. Ported from the site's `claude-translator.ts`
(blog-post content type, Brazil cultural adaptation, mixed technical terminology,
Markdown preserved).

#### `OutputType`

| Field | Type | Description |
|---|---|---|
| `translated_title` | `str` | Post title in pt-BR. |
| `translated_body_markdown` | `str` | Full post body in pt-BR, Markdown preserved. |
| `confidence` | `int` | Self-rated translation quality, 0–100 (default `80`). |
| `cultural_notes` | `list[str]` | Notes on any cultural-adaptation choices (default `[]`). |
| `technical_terms` | `list[TranslatedTerm]` | Non-obvious term decisions (default `[]`). |

`TranslatedTerm` is a nested model with `original`, `translation`, and `reasoning` fields.

#### `get_agent_config() -> AgentConfig`

Loads `app/prompts/translate_ptbr.j2` via `PromptManager`; uses `ModelProvider.CLAUDE_CODE_SDK`
with `"sonnet"` (subscription-billing default; revert to `ModelProvider.ANTHROPIC` /
`"claude-opus-4-8"` per-node for metered API billing; a natural Project H downgrade
candidate once local/open-weight swaps are measured).

#### `process(task_context) -> TaskContext`

Reads `ReviseNode`'s `result` via `get_node_output("ReviseNode")["result"]`, serialises
it with `model_dump_json()`, calls `run_agent_recorded()`, and stores the translation
`OutputType`.

### System Prompt

`app/prompts/translate_ptbr.j2` — professional EN→pt-BR translation rules: Brazil
cultural adaptation, mixed technical terminology, Markdown/code/identifier preservation.

---

## ProposalWriterNode

**Source:** `app/workflows/proposal_generator_workflow_nodes/proposal_writer_node.py`

```python
class ProposalWriterNode(AgentNode):
```

Concrete `AgentNode` that produces the client-facing `AutomationRoadmap` deliverable from
scored opportunities. It is the fourth node in the proposal generator pipeline
(`OpportunityIdentifierNode → ProposalWriterNode`).

Reads the full opportunity output from `OpportunityIdentifierNode` (sorted candidates plus
a recommended workflow) and asks the LLM to produce a four-section roadmap following The
Diagnostic deliverable template. Language (PT or EN) is threaded through the user-prompt
JSON from `event.language` (defaults to `"PT"` for Brazilian clients).

### `OutputType`

```python
class OutputType(AgentNode.OutputType):
    situation_summary: str
    candidates: list[ScoredCandidate]
    top_profiles: list[WorkflowProfile]
    recommended_workflow: str
    engagement_scope: str
    price_range_brl: tuple[int, int]
    body_pt: str | None = None
    body_en: str | None = None
```

Fields mirror `AutomationRoadmap` directly so the agent produces a single validated
object. `candidates` are expected pre-sorted composite-descending (guaranteed by
`OpportunityIdentifierNode`); `top_profiles` is capped at 3 by the `AutomationRoadmap`
validator.

### `get_agent_config() -> AgentConfig`

Returns an `AgentConfig` with:

| Field | Value |
|---|---|
| `system_prompt` | `PromptManager().get_prompt("proposal_writer")` |
| `output_type` | `ProposalWriterNode.OutputType` |
| `deps_type` | `None` |
| `model_provider` | `ModelProvider.CLAUDE_CODE_SDK` |
| `model_name` | `"sonnet"` |

### `process(task_context) -> TaskContext`

Reads:
- `OpportunityIdentifierNode` output via `task_context.get_node_output("OpportunityIdentifierNode")["result"]`
- `event.language` (`"PT"` or `"EN"`; handles both dict events and Pydantic event objects)

Serialises both into a JSON user prompt, calls `run_agent_recorded()`, validates the
raw output into an `AutomationRoadmap`, and writes the result under `ProposalWriterNode`
via `task_context.update_node()`.

### System Prompt

`app/prompts/proposal_writer.j2` — encodes all four required deliverable sections
(Situation & Opportunity, Ranked Candidates, Top Workflow Profiles, Recommended First
Engagement), the composite scoring rubric axis definitions and anchor descriptions
(`frequency × 0.35 + time_cost × 0.40 + buildability × 0.25`), and PT/EN language
dispatch instructions. No scoring computation occurs in Python — the formula is
embedded in the prompt for model-version stability.

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

## BrainDocument SQLAlchemy Model

**Source:** `app/database/brain_document.py`

```python
class BrainDocument(Base):
    __tablename__ = "brain_documents"
```

Persistence record for a single section-level chunk of the company brain (agentic-portfolio)
markdown corpus. Produced by `scripts/index_brain.py` (Layer 1 of the brain RAG pipeline).
Each markdown file is split by H2/H3 section header; every section yields one row carrying
the raw chunk text, its provenance, and a 1024-dim pgvector embedding for semantic retrieval.

This model is the **write path** for the brain RAG layer. The read/query path (vector
similarity search from `RetrieveChunksNode` corpus `"brain"`) is available as of Project D Task 3
— see [RetrieveChunksNode](#retrievechunksnode) below.

**Module-level constant:** `EMBEDDING_DIM = 1024`

### Columns

| Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID(as_uuid=True)` | No (PK) | `uuid.uuid4` | Primary key, UUID v4 generated at insert time. |
| `file_path` | `String(512)` | No | — | Relative path from brain repo root (e.g. `'docs/career.md'`). |
| `doc_type` | `String(50)` | No | — | Corpus category derived from the CORPUS map: `decision`, `project`, `career`, `brand`, `business`, `content`, `diagnostic`, `meta`, `plan`, `archived` (the `memory` type was retired when memory left the corpus). |
| `section` | `String(256)` | Yes | — | H2/H3 header the chunk falls under; empty string if the file has no headers. |
| `content` | `Text` | No | — | Raw chunk text (section header + body, up to ~500 tokens). |
| `embedding` | `Vector(1024)` | Yes | — | 1024-dim Voyage AI embedding (`voyage-2`) for semantic similarity search (pgvector). HNSW-indexed (`ix_brain_documents_embedding_hnsw`, cosine) so queries skip the brute-force scan. |
| `indexed_at` | `DateTime` | Yes | `datetime.now` | Timestamp when this chunk was last indexed; used for incremental skip logic. |
| `client_slug` | `String(128)` | Yes | `NULL` | Diagnostic client identifier (e.g. `'acme-sp-2026-07'`); `NULL` for non-diagnostic docs. |
| `workflow_patterns` | `ARRAY(String)` | Yes | `NULL` | Workflow pattern tags from diagnostic docs (e.g. `['WhatsApp order tracking']`); `NULL` for other doc types. |
| `doc_id` | `String(256)` | Yes | `NULL` | OKF `doc_id`; derived from the filename stem when absent. |
| `layer` | `ARRAY(String)` | Yes | `NULL` | OKF `layer` (e.g. `['brain', 'engine']`). Case-normalized to lowercase by the indexer; supports `layer`-filter array overlap. |
| `project` | `String(128)` | Yes | `NULL` | OKF `project` (e.g. `'orchestrator'`). Case-normalized to lowercase; supports `project`-filter scalar match. For chunks collected from a sub-repo's `planning/**/*.md` + root `CLAUDE.md` (OR.O widening — see `docs/brain-rag.md`), the indexer unconditionally stamps this with the manifest `brain.toml` slug, overriding any frontmatter `project:` value the file carries. |
| `status` | `String(32)` | Yes | `NULL` | OKF `status` (e.g. `'active'`, `'draft'`, `'archived'`). Case-normalized to lowercase; `'archived'` rows are excluded from default brain retrieval. |
| `keywords` | `ARRAY(String)` | Yes | `NULL` | OKF `keywords` tags; folded into `content_tsv` at FTS weight `'A'`. |
| `related` | `ARRAY(String)` | Yes | `NULL` | OKF `related` paths to related docs (stored on the document row; the traversable graph index is `BrainEdge`, populated from this field by mev's `emit-graph` + `scripts/load_brain_edges.py`, and walked at query time by `RetrieveChunksNode`'s structural expansion stage). |
| `is_section_title` | `Boolean` | No | `False` | `True` when the chunk is a header-only section (header-stripped body empty or `< 40` chars); drives the 2x section-title weight in `RetrieveChunksNode._fuse_and_rank`. |
| `title` | `String(512)` | Yes | `NULL` | OKF frontmatter `title`; stored for FTS (weight `'A'`) and citation display. |
| `description` | `Text` | Yes | `NULL` | OKF frontmatter `description`; stored for FTS (weight `'B'`) and citation display. |
| `content_tsv` | `TSVECTOR` | Yes | generated | **Read-only generated column** — Postgres maintains it from `title`+`keywords` (weight `'A'`), `description` (`'B'`), and `content` (`'C'`). GIN-indexed (`ix_brain_documents_content_tsv`) for graded `ts_rank` full-text search. The indexer must **never** write it. |

### Migration

The `brain_documents` table is created by migration `b3c4d5e6f7a8`
(`app/alembic/versions/b3c4d5e6f7a8_create_brain_documents_table.py`).
`down_revision` chains off the `a1b2c3d4e5f6` migration (learning_artifacts table).
Two later migrations extend it: `d1e2f3a4b5c6` adds the six OKF columns
(`doc_id`/`layer`/`project`/`status`/`keywords`/`related`) with their GIN/btree indexes, and
`e2f3a4b5c6d7` adds `is_section_title`/`title`/`description`, the generated `content_tsv`
column with its GIN index, and the HNSW ANN index on `embedding`.

**SQLite note:** The `ARRAY(String)`, `Vector`, and `TSVECTOR` columns are PostgreSQL-only
types. The SQLite-backed test fixtures exclude `brain_documents` from `create_all`; round-trip
tests that require a live table are skipped with a documented reason. Schema tests (which do not
require table creation) pass on SQLite.

### Session and Base

`BrainDocument` inherits from `Base = declarative_base()` defined in `app/database/session.py`.
The model is imported in `app/alembic/env.py` (`from database.brain_document import *`) so
Alembic autogenerate sees its metadata.

### Package Export

`BrainDocument` is exported from `app/database/__init__.py` alongside `LearningArtifact`, `ContentChunk`, and `ChatSession`:

```python
from database import BrainDocument, ChatSession, ContentChunk, LearningArtifact
```

### Indexer CLI

The `brain_documents` table is populated by `scripts/index_brain.py`, a standalone CLI that
walks the brain corpus, splits files by H2/H3 section, embeds each chunk via `EmbeddingService`,
and upserts into `brain_documents`. Incremental runs skip chunks whose `indexed_at` is newer
than the source file's `mtime`.

```bash
# From repo root
uv run python scripts/index_brain.py --brain-path ../agentic-portfolio --dry-run
uv run python scripts/index_brain.py --brain-path ../agentic-portfolio --rebuild
```

| Argument | Description |
|---|---|
| `--brain-path` | Root of the brain repo to walk (default: `../agentic-portfolio`). |
| `--rebuild` | Force re-index all files regardless of `indexed_at` vs `mtime`. |
| `--dry-run` | Print files that would be indexed; no DB writes or API calls. |

---

## BrainEdge SQLAlchemy Model

**Source:** `app/database/brain_edge.py`

```python
class BrainEdge(Base):
    __tablename__ = "brain_edges"
```

Persistence record for one directed `related:` edge between company-brain documents, as
emitted by mev's `emit-graph` command over the OKF `related` frontmatter field. This is the
**traversal layer** that makes `BrainDocument.related` queryable as a graph: `RetrieveChunksNode`'s
structural neighborhood-expansion stage (Stage 1b, brain corpus only) walks these rows to widen
the semantic candidate set with a query's neighboring documents (OR.G).

### Columns

| Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID(as_uuid=True)` | No (PK) | `uuid.uuid4` | Primary key, UUID v4 generated at insert time. |
| `source_node_id` | `String(512)` | No | — | Canonical `scope:doc_id` of the edge source (mev `emit-graph` `edges[].from`). |
| `source_doc_id` | `String(256)` | No | — | The source node's authored `doc_id`, for joining to `brain_documents.doc_id`. Indexed (`ix_brain_edges_source_doc_id`). |
| `to_ref` | `String(512)` | No | — | The raw authored `related:` entry (bare `doc_id` or already-scoped `scope:doc_id`). |
| `target_node_id` | `String(512)` | Yes | `NULL` | Resolved canonical `scope:doc_id` of the edge target, read from mev emit-graph v2's already-resolved `target_node_id` field; `NULL` when dangling (unresolvable on mev's side). |
| `target_doc_id` | `String(256)` | Yes | `NULL` | Resolved target `doc_id`, for joining to `brain_documents.doc_id`, read from mev's `target_doc_id` field; `NULL` when dangling. Indexed (`ix_brain_edges_target_doc_id`). |
| `kind` | `String(64)` | No | `"related"` | Edge kind as emitted by mev (currently always `"related"`). |
| `scope` | `String(128)` | Yes | `NULL` | Optional scope of the source node (mev `emit-graph` `nodes[].scope`). |
| `indexed_at` | `DateTime` | Yes | `datetime.now` | Timestamp when this edge row was last (re)loaded. |

A `UniqueConstraint` on `(source_node_id, to_ref)` (`uq_brain_edges_source_node_id_to_ref`) keeps
one row per authored edge — reloads replace rather than duplicate.

**On dangling edges:** an edge whose mev-resolved `target_node_id`/`target_doc_id` are `NULL` is
kept as a row rather than dropped, preserving authoring intent for later resolution. An edge whose
*source* doesn't resolve against the payload's `nodes[]` is skipped entirely (`source_doc_id` is a
required non-null column with no fallback).

### Migration

The `brain_edges` table is created by migration `e5f6a7b8c9d0`
(`app/alembic/versions/e5f6a7b8c9d0_create_brain_edges_table.py`).

**SQLite note:** all columns are plain `String`/`DateTime`/`UUID` types (no `ARRAY`, `Vector`, or
`TSVECTOR`), so unlike `BrainDocument` this model is SQLite-compatible and not excluded from
`create_all` in test fixtures.

### Session and Base

`BrainEdge` inherits from `Base = declarative_base()` defined in `app/database/session.py`. The
model is imported in `app/alembic/env.py` (`from database.brain_edge import *`) so Alembic
autogenerate sees its metadata.

### Package Export

`BrainEdge` is exported from `app/database/__init__.py` alongside the other models:

```python
from database import BrainDocument, BrainEdge, ChatSession, ContentChunk, LearningArtifact
```

### Loader CLI

The `brain_edges` table is populated by `scripts/load_brain_edges.py`, an idempotent loader that
reads mev's `emit-graph` v2 JSON output (`nodes[]` + `edges[]`) and its already-resolved
`target_node_id`/`target_doc_id` edge fields directly — mev's `resolve_edge()` is the single
source of truth for edge resolution — then clear-then-reloads the whole table in one transaction
so repeated runs stay consistent (`brain_edges` is a read-only derived index, not a source of
truth — see `docs/scripts.md` § `load_brain_edges.py`).

### Test coverage

`tests/database/test_brain_edge.py` — model/schema tests (columns, constraints, migration).
`tests/test_load_brain_edges.py` — 15 tests covering the loader: the version=='2' guard,
resolved-target read-through, dangling-edge preservation, unresolvable-source skip, and
clear-then-reload idempotency, mocking the session/repository seam (no live DB).

---

## ContentChunk SQLAlchemy Model

**Source:** `app/database/content_chunk.py`

```python
class ContentChunk(Base):
    __tablename__ = "content_chunks"
```

Persistence record for a single text chunk produced by the document ingestion pipeline (Project D
`DOCUMENT_INGEST` workflow). Each ingested document yields one or more rows. The `is_section_title`
flag identifies standalone heading chunks; `RetrieveChunksNode` applies a 2x weight boost to these
rows during hybrid re-ranking (ported from the rag-engine-rs two-stage retrieval pattern).

**Module-level constant:** `EMBEDDING_DIM = 1024`

### Columns

| Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID(as_uuid=True)` | No (PK) | `uuid.uuid4` | Primary key, UUID v4 generated at insert time. |
| `doc_id` | `UUID(as_uuid=True)` | No | — | Groups all chunks of one ingested document. Indexed (`ix_content_chunks_doc_id`). |
| `position` | `Integer` | No | — | 0-based chunk order within the document. |
| `section_title` | `String(256)` | Yes | — | Markdown header this chunk falls under; `None` for top-of-file content. |
| `is_section_title` | `Boolean` | No | `False` | `True` for standalone heading chunks; drives the 2x retrieval weight boost. |
| `content` | `Text` | No | — | The chunk text content. |
| `embedding` | `Vector(1024)` | Yes | — | 1024-dim Voyage AI embedding written at storage time (pgvector). |
| `created_at` | `DateTime` | Yes | `datetime.now` | Timestamp when the chunk was created. |

### Migration

The `content_chunks` table is created by migration `c4d5e6f7a8b9`
(`app/alembic/versions/c4d5e6f7a8b9_create_content_chunks_and_chat_sessions.py`).
`down_revision` chains off `b3c4d5e6f7a8` (brain_documents table). The migration also
creates the `ix_content_chunks_doc_id` index. Downgrade drops the index and both tables.

**SQLite note:** The `Vector(1024)` column is a pgvector type. SQLite silently accepts it in
tests (no PostgreSQL extension required), but per decision D31, tests that exercise the embedding
column in round-trips should be marked `pytest.mark.skip` under SQLite. See the note in the
review report for Task 1 regarding a deferred D31 skip marker.

### Session and Base

`ContentChunk` inherits from `Base = declarative_base()` defined in `app/database/session.py`.

### Package Export

`ContentChunk` is exported from `app/database/__init__.py`:

```python
from database import ChatSession, ContentChunk
```

---

## ChatSession SQLAlchemy Model

**Source:** `app/database/chat_session.py`

```python
class ChatSession(Base):
    __tablename__ = "chat_sessions"
```

Persistence record for a per-document Q&A conversation session (Project D `DOCUMENT_QA`
workflow). Each session is scoped to one ingested document (`doc_id`) and holds an ordered list
of conversation turns as JSON. `UpdateSessionMemoryNode` appends a new turn after each Q&A cycle,
enabling grounded multi-turn conversations over ingested documents.

### Columns

| Column | SQLAlchemy Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID(as_uuid=True)` | No (PK) | `uuid.uuid4` | Primary key, UUID v4 generated at insert time. |
| `doc_id` | `UUID(as_uuid=True)` | No | — | The ingested document this session is scoped to. |
| `turns` | `JSON` | Yes | `list` | Ordered list of `{role, content}` conversation turns. |
| `topics_covered` | `JSON` | Yes | `list` | Topics surfaced across the conversation. |
| `created_at` | `DateTime` | Yes | `datetime.now` | Timestamp when the session was created. |
| `updated_at` | `DateTime` | Yes | `datetime.now` | Last-updated timestamp; `onupdate=datetime.now` is honored by the SQLAlchemy ORM. |

### Migration

The `chat_sessions` table is created by the same migration as `content_chunks`: `c4d5e6f7a8b9`
(`app/alembic/versions/c4d5e6f7a8b9_create_content_chunks_and_chat_sessions.py`).

### Session and Base

`ChatSession` inherits from `Base = declarative_base()` defined in `app/database/session.py`.

### Package Export

`ChatSession` is exported from `app/database/__init__.py`:

```python
from database import ChatSession, ContentChunk
```

---

## RetrieveChunksNode

**Source:** `app/workflows/document_qa_workflow_nodes/retrieve_chunks_node.py`

```python
class RetrieveChunksNode(Node):
```

Two-stage hybrid retrieval node for the `DOCUMENT_QA` workflow (Phase 1 Project D Task 3).
Implements the semantic-then-keyword re-rank pattern ported from the rag-engine-rs
`two_stage_retrieval.rs` and `query.rs` modules.

**Retrieval pipeline:**

1. **Stage 1 — semantic candidate set:** pgvector cosine-distance query (HNSW-indexed for the
   brain corpus) returns the top-20 closest chunks from the target corpus table. For the brain
   corpus, `status='archived'` rows are excluded unless `include_archived=True`.
2. **Stage 2 — keyword re-rank:** scoped to the Stage-1 candidate IDs. The path depends on the
   corpus:
   - **Brain corpus** (declares a `tsv_field`): a graded Postgres full-text query against the
     generated `content_tsv` column — `ts_rank(content_tsv, plainto_tsquery('english', query))`.
     Returns a `dict[id -> ts_rank]`. `plainto_tsquery` strips English stop words and stems
     natively, and `setweight` makes a term in a doc's `title`/`keywords` (weight `'A'`) outrank
     the same term in body text (weight `'C'`).
   - **Content corpus** (no `tsv_field`): the legacy binary ILIKE match (each whitespace-separated
     query term, punctuation-stripped, matched case-insensitively against the content field),
     returning a `set` of matched IDs.
2b. **Stage 1b — structural neighborhood expansion** (brain corpus only, `supports_structural`):
   when `expand_structural=True` (default), the top `_STRUCTURAL_SEED_COUNT` (5) Stage-1 semantic
   hits are used to walk `brain_edges` (loaded by `scripts/load_brain_edges.py` from mev's
   `emit-graph` output) for their resolved `related:`-neighbors. Neighbor docs not already present
   among the semantic candidates are fetched and merged in, each flagged `via="structural"` for
   explainability (OR.G). No-op for corpora that don't declare `supports_structural` or when no
   candidate carries a `doc_id`.
3. **Additive score fusion:** `score = (1.0 − distance) × title_weight + keyword_contribution`,
   where `title_weight = 2.0` for `is_section_title=True` chunks (section-title 2x weight). The
   keyword contribution is graded for FTS corpora (`_KW_WEIGHT × ts_rank`) and a flat `_KW_BOOST`
   for the legacy set path. NaN distances are filtered out before sorting (mirrors the Rust
   `total_cmp` guard).

**Corpus dispatch** — controlled by the `corpus` field on the incoming event:

| `corpus` value | Table queried | Model |
|---|---|---|
| `"content"` (default) | `content_chunks` | `ContentChunk` |
| `"brain"` | `brain_documents` | `BrainDocument` |

Adding a third corpus requires one entry in the module-level `_CORPUS_CONFIG` dict.

### `process(task_context: TaskContext) -> TaskContext`

Reads `event.question`, `event.corpus` (defaults to `"content"`), `event.filters`,
`event.include_archived`, and `event.expand_structural` (all via `getattr` defensive read —
defaulting to `None`/`False`/`True` respectively) from the task context, calls `retrieve()` with
`k=5`, `filters`, `include_archived`, and `expand_structural`, and writes the result:

```python
task_context.update_node(node_name=self.node_name, result={"chunks": chunks})
```

Downstream nodes read via:

```python
output = task_context.get_node_output("RetrieveChunksNode")
chunks = output["result"]["chunks"]
```

### `retrieve(query, corpus="content", k=5, threshold=0.0, *, filters=None, include_archived=False, expand_structural=True) -> list[dict]`

Public retrieval method. Embeds `query` via `EmbeddingService`, runs the two-stage (plus optional
structural) pipeline, and returns up to `k` normalized chunk dicts sorted by fused score
descending.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `str` | — | User question text to search. |
| `corpus` | `str` | `"content"` | Target corpus: `"content"` or `"brain"`. |
| `k` | `int` | `5` | Maximum number of chunks to return. |
| `threshold` | `float` | `0.0` | Minimum fused score; chunks below are excluded. |
| `filters` | `dict \| None` | `None` | Optional metadata filters (keyword-only). Applied only when the corpus declares `filter_fields`. See `DocumentQAEventSchema` for accepted keys. |
| `include_archived` | `bool` | `False` | Keyword-only. When `False`, brain-corpus results exclude `status='archived'` docs. No effect on the content corpus. |
| `expand_structural` | `bool` | `True` | Keyword-only. When `True` and the corpus declares `supports_structural` (currently `"brain"` only), widens the Stage-1 semantic candidate set through the `related:`-neighborhood of the top hits before keyword re-rank. No-op for `"content"` or when `False`. |

**Return schema** — each element of the returned list contains:

| Key | Type | Description |
|---|---|---|
| `content` | `str` | Chunk text. |
| `section_title` | `str \| None` | Markdown section header the chunk falls under. |
| `score` | `float` | Fused retrieval score (higher = more relevant). |
| `source` | `str` | Display label: `section_title` or `"General"` if none. |
| `file_path` | `str \| None` | Provenance: source file path (brain corpus; `None` when the row lacks it). |
| `doc_id` | `str \| None` | Provenance: OKF `doc_id` of the source doc. |
| `title` | `str \| None` | Provenance: OKF `title` of the source doc, for citation display. |
| `via` | `str` | Provenance: `"semantic"` (Stage 1) or `"structural"` (Stage 1b neighborhood expansion). |

### Internal methods (mockable test seams)

| Method | Description |
|---|---|
| `_semantic_search(vector, corpus, limit, filters=None, include_archived=False)` | Stage 1: pgvector cosine-distance query. Accepts optional `filters` dict; when present and the corpus declares `filter_fields`, delegates to `_apply_metadata_filters` before executing. When the corpus declares `default_status_exclude` and `include_archived` is `False`, also filters out that status (NULL status kept). Isolated for unit-test patching without a live DB. |
| `_structural_expand(candidates, corpus, vector, filters=None, include_archived=False)` | Stage 1b: when the corpus declares `supports_structural`, resolves the `related:`-neighborhood of the top `_STRUCTURAL_SEED_COUNT` (5) semantic candidates via `_resolve_neighbor_doc_ids` (queries `brain_edges` by `source_doc_id`) and `_fetch_neighbor_candidates` (fetches the resolved `target_doc_id` rows, respecting `filters`/`include_archived`), tagging results `via="structural"`. Short-circuits with no DB call when the corpus doesn't support structural expansion or no candidate carries a `doc_id`. |
| `_merge_structural_candidates(candidates, structural)` | Static helper: unions structural candidates into the semantic set, deduped by `id` — a structural candidate whose id already appears among `candidates` is dropped so the semantic candidate wins ties rather than duplicating the row. |
| `_keyword_search(query, candidate_ids, corpus)` | Stage 2 dispatcher. Returns a `dict[id -> ts_rank]` for corpora declaring a `tsv_field` (graded FTS) or a `set[id]` for the legacy ILIKE path; returns the matching empty shape when `candidate_ids` is empty. Delegates to one of the two helpers below. |
| `_keyword_search_fts(query, candidate_ids, config, tsv_field)` | Graded full-text search (brain corpus). Builds `ts_rank(content_tsv, plainto_tsquery('english', query))` scoped to candidate IDs, returns `dict[id -> float ts_rank]`. Stop-word removal and stemming come from `plainto_tsquery`. |
| `_keyword_search_ilike(query, candidate_ids, config)` | Legacy binary ILIKE (content corpus). Query terms are stripped of non-word characters before matching (e.g. `"RAG?"` → `"RAG"`); ORs in any `keyword_extra_fields` columns. Returns a `set` of matched IDs. |
| `_apply_metadata_filters(query, model, filters, filter_fields)` | Module-level helper. Translates `{field: value}` pairs to SQLAlchemy WHERE clauses: scalar fields use `col == value`; array fields (e.g. `layer`) use `.overlap([value])`. Applied inside `_semantic_search`; extracted to keep `_semantic_search` under the pylint locals limit and to make filter logic independently testable. |
| `_fuse_and_rank(candidates, keyword_matches, k, threshold)` | Pure: score fusion, NaN filtering, threshold cut, top-k. Grades the keyword contribution when `keyword_matches` is a `dict` (`_KW_WEIGHT × ts_rank`) and applies a flat `_KW_BOOST` when it is a `set`. Carries `file_path`/`doc_id`/`title`/`via` provenance through to each result. No DB calls. |

### Test coverage

`tests/workflows/test_retrieve_chunks_node.py` — 60 tests covering: score ordering,
keyword boost, section-title 2x weight, threshold filtering, top-k, NaN safety,
corpus `"brain"` threading, TaskContext output contract (`{"result": {"chunks": [...]}}` shape),
exact score formula verification, punctuation stripping in keyword terms, `filters` forwarding
from event through `process()` → `retrieve()` → `_semantic_search()`, defensive `getattr`
fallback when event has no `filters` attribute, brain corpus ORing the `keywords` column in
keyword search, content corpus query unchanged by new config, scalar-filter exclusion of
non-matching rows, and the structural neighborhood-expansion stage (`_structural_expand`,
`_merge_structural_candidates`, `expand_structural` toggle on/off, `via="structural"` tagging,
no-DB-call short-circuit for corpora without `supports_structural`). An additional end-to-end
suite, `tests/workflows/test_brain_graph_retrieval.py`, proves the headline OR.G acceptance: a
`related:`-neighbor answer is retrieved and flagged `via="structural"` when absent from the
semantic-only path, and structural-on/off results are identical when no useful neighbor exists
(dangling edge).

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

## ProposalGenerator StorageNode

**Source:** `app/workflows/proposal_generator_workflow_nodes/storage_node.py`

```python
class StorageNode(Node):
```

Terminal persistence node for the proposal generator workflow. Reads the final
`AutomationRoadmap` from whichever writer branch ran, embeds a summary string via
`EmbeddingService`, and stores a `BrainDocument` row through `GenericRepository` using
the shared `db_session` factory (rule 7 — no deployment logic inside the node).

The artifact id is captured from `task_context.event.artifact_id` **before** the session
commits. SQLAlchemy's default `expire_on_commit` would clear ORM attributes on the
detached instance after the session closes; reading `doc.id` post-commit would silently
return `None` or raise `DetachedInstanceError`. Reading from the event schema instead
avoids this entirely.

### `process(task_context) -> TaskContext`

1. Calls `_read_final_roadmap(task_context)` to get the authoritative `AutomationRoadmap`.
2. Captures `artifact_id` and `company_name` from `task_context.event` before any commit.
3. Calls `_build_embed_text(roadmap)` → `EmbeddingService().embed_text(embed_text)`.
4. Constructs `BrainDocument(id=artifact_id, file_path=f"proposals/{artifact_id}/roadmap.json", doc_type="proposal", section="AutomationRoadmap", content=embed_text, embedding=embedding)`.
5. Calls `self._persist(doc)`.
6. Records `{"artifact_id", "file_path", "company_name", "embedded": True, "doc_type": "proposal"}` via `task_context.update_node()`.

### `_read_final_roadmap(task_context) -> AutomationRoadmap`

Returns the authoritative roadmap from whichever terminal writer ran. Checks
`task_context.nodes.get("ProposalReviseNode")` first — if the revise branch ran, its output
is authoritative and is reconstructed via `_roadmap_from_revise_output`. Otherwise falls
back to `task_context.get_node_output("ProposalWriterNode")["result"]`.
If `roadmap_data` is already an `AutomationRoadmap` instance it is returned directly;
otherwise `AutomationRoadmap.model_validate(roadmap_data)` is called to coerce from dict.

### `_roadmap_from_revise_output(revise_result) -> AutomationRoadmap`

Reconstructs an `AutomationRoadmap` from a `ProposalReviseNode.OutputType` payload.
`ProposalReviseNode` stores candidates and top_profiles as JSON-encoded strings
(`candidates_json`, `top_profiles_json`) because pydantic-ai does not support nested
Pydantic models in structured output. This helper decodes those strings and validates
the full roadmap, combining revise fields with the original writer output fields
(`situation_summary`, `recommended_workflow`, `engagement_scope`, `price_range_brl`).

### `_build_embed_text(roadmap) -> str`

Constructs the string passed to `EmbeddingService.embed_text`. Format:
`f"{roadmap.situation_summary}\n{'; '.join(c.name for c in roadmap.candidates)}"`.
Encodes situation context and candidate names so future semantic search queries can
retrieve past proposals by domain or problem type.

### `_persist(doc) -> None`

Single persistence seam. Opens the shared `db_session` context manager, creates a
`GenericRepository(session=session, model=BrainDocument)`, and calls `.create(doc)`.
Tests monkeypatch this method so no real database is touched.

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

## API Security and CORS

**Sources:** `app/api/security.py`, `app/main.py`

### `require_api_key`

**Source:** `app/api/security.py`

```python
def require_api_key(x_api_key: str | None = Header(None)) -> None:
```

FastAPI dependency that enforces `X-API-Key` authentication on protected routes. The
expected key is read from the `ORCHESTRATION_API_KEY` environment variable **at request
time**; it is never cached at startup, so the key can be rotated without a restart.

**Applied to:** `POST /events/` (via `dependencies=[Depends(require_api_key)]`).

**Not applied to:** `GET /health` and `GET /workflows*` — these remain publicly
accessible so that readiness probes and workflow graph inspection do not require auth.
The choice is intentional: the graph and health endpoints expose no sensitive data and
their openness simplifies downstream tooling.

**Behaviour:**

| Condition | HTTP status | Meaning |
|---|---|---|
| `ORCHESTRATION_API_KEY` env var is unset | `503 Service Unavailable` | Operator misconfiguration — fail-closed so a missing var cannot silently open access. |
| `X-API-Key` header absent or value mismatch | `401 Unauthorized` | Bad or missing credential. |
| `X-API-Key` matches `ORCHESTRATION_API_KEY` | passes | Request proceeds to the endpoint handler. |

Key comparison uses `hmac.compare_digest` to guard against timing-based side-channel
attacks. Declaring the header as `Header(None)` (optional at the FastAPI level) ensures
a missing header returns `401` rather than FastAPI's default `422 Unprocessable Entity`.

### `CORSMiddleware`

**Source:** `app/main.py`

Mounted at application startup via:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`_get_allowed_origins()` reads the `ALLOWED_ORIGINS` environment variable (comma-separated
list of origin strings) and returns a parsed `list[str]`. If the variable is unset, the
default `["https://learn-agentic-ai.com"]` is used.

To permit additional origins in development (e.g. `http://localhost:3000`), set:

```
ALLOWED_ORIGINS=https://learn-agentic-ai.com,http://localhost:3000
```

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

### `POST /events/`

**Source:** `app/api/endpoint.py`

```
POST /events/  X-API-Key: <key>  {"workflow_type": "CONTENT_PIPELINE", "data": {...}}
  → 202 TaskAcceptedResponse(task_id="...", message="...")
  → 401 if X-API-Key is absent or wrong
  → 503 if ORCHESTRATION_API_KEY is unset (operator misconfiguration)
  → 422 if workflow_type is unknown or data fails schema validation
```

Dispatches a workflow run. Requires the `X-API-Key` request header (see
[`require_api_key`](#require_api_key)). On success, the event row is flushed (not
committed) before `send_task` — the transaction rolls back if Celery dispatch fails,
preventing ghost rows (see CLAUDE.md core hardening table).

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
    WorkflowRegistry.CUSTOMER_CARE.name:      CustomerCareEventSchema,
    WorkflowRegistry.CONTENT_PIPELINE.name:   ContentPipelineEventSchema,
    WorkflowRegistry.RESEARCH_AGENT.name:     ResearchAgentEventSchema,
    WorkflowRegistry.PROPOSAL_GENERATOR.name: ProposalGeneratorEventSchema,
    WorkflowRegistry.DOCUMENT_INGEST.name:    DocumentIngestEventSchema,
    WorkflowRegistry.DOCUMENT_QA.name:        DocumentQAEventSchema,
}
```

Maps `WorkflowRegistry` enum member names (strings) to their corresponding event
schema classes. The generic dispatcher in `endpoint.py` resolves the correct schema
by looking up `payload.workflow_type` in this dict.

**Every new workflow must add an entry here.** If the entry is missing, requests for
that `workflow_type` return `422 Unprocessable Entity` with a descriptive error
message. See [WorkflowRegistry — Adding a New Entry](#adding-a-new-entry) for the
complete checklist.

---

## DocumentIngestEventSchema

**Source:** `app/schemas/document_ingest_schema.py`

```python
class DocumentIngestEventSchema(BaseModel):
```

Inbound event schema for the `DOCUMENT_INGEST` workflow. Accepts either raw text or
base64-encoded binary content. A `model_validator` enforces that at least one content
field is present.

### Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `doc_id` | `UUID` | `uuid4()` | Stable identity for all `ContentChunk` rows produced by this ingest run. Auto-generated if not supplied by the caller. |
| `title` | `str` | required | Human-readable document title. |
| `content` | `str \| None` | `None` | Raw document text (text path). |
| `content_b64` | `str \| None` | `None` | Base64-encoded document bytes (binary path, e.g. PDF). |
| `mime_type` | `str` | `"text/plain"` | MIME type for the binary path. Supported: `text/plain`, `application/pdf`. |
| `chunk_size` | `int` | `500` | Maximum token count per chunk (passed to `ChunkingService`). |
| `overlap` | `int` | `50` | Token overlap between adjacent chunks. |

### Validation

`_require_content_or_b64` (mode `"after"`): raises `ValueError` if both `content`
and `content_b64` are `None`.

---

## ParseDocumentNode

**Source:** `app/workflows/document_ingest_workflow_nodes/parse_document_node.py`

```python
class ParseDocumentNode(Node):
```

First node in the `DocumentIngestWorkflow` linear DAG. Normalises the ingest event into
a plain-text string, handling two input paths:

- **Text path** — `event.content` is not `None`: the value is used directly.
- **Binary path** — `event.content_b64` is not `None`: base64-decoded, then decoded
  as UTF-8 (`text/plain`) or extracted page-by-page via `fitz.open`
  (`application/pdf`). Unsupported MIME types raise `ValueError`.

`fitz` is imported at module level so that tests can patch
`workflows.document_ingest_workflow_nodes.parse_document_node.fitz.open`.

### `process(task_context) -> TaskContext`

Output written via `task_context.update_node(node_name=..., result={"text": <str>})`.

---

## ChunkDocumentNode

**Source:** `app/workflows/document_ingest_workflow_nodes/chunk_document_node.py`

```python
class ChunkDocumentNode(Node):
```

Second node in the `DocumentIngestWorkflow` DAG. Reads the plain-text output of
`ParseDocumentNode` and splits it into section-aware, overlapping token chunks.

### Section-aware chunking algorithm

1. `_split_into_sections(text)` scans for markdown headers (`#`, `##`, `###`) using
   `re.MULTILINE` so that `^` matches any line start. Returns a list of
   `(header_text | None, body_text)` pairs.
2. For each section with a non-`None` header, a standalone
   `is_section_title=True` chunk is emitted first (content = header text,
   `section_title` = header text). This mirrors the rag-engine-rs title-weighting hook
   that `RetrieveChunksNode` will use for a 2× boost.
3. The section body is passed to `ChunkingService.chunk_text(body, chunk_size,
   overlap)`. Each resulting chunk is emitted with `is_section_title=False` and
   `section_title` set to the current header (or `None` for pre-header content).
4. A global `position` counter increments monotonically across all emitted chunks so
   reading order is recoverable at retrieval time.

### `process(task_context) -> TaskContext`

Reads `task_context.get_node_output("ParseDocumentNode")["result"]["text"]`.
Chunk size and overlap come from `task_context.event.chunk_size` and
`task_context.event.overlap` (defaults: 500 / 50).

Output: `result = {"chunks": [{"position", "section_title", "is_section_title", "content"}, ...]}`.

---

## EmbedChunksNode

**Source:** `app/workflows/document_ingest_workflow_nodes/embed_chunks_node.py`

```python
class EmbedChunksNode(Node):
```

Third node in the `DocumentIngestWorkflow` DAG. Reads the chunk list produced by
`ChunkDocumentNode` and embeds all chunk texts in a single batched Voyage API call.

`EmbeddingService` is instantiated inside `process()` (not at import time or in
`__init__`) so tests can patch
`workflows.document_ingest_workflow_nodes.embed_chunks_node.EmbeddingService` without
requiring a real Voyage API key.

### `process(task_context) -> TaskContext`

1. Reads `task_context.get_node_output("ChunkDocumentNode")["result"]["chunks"]`.
2. Extracts all `content` strings into a list.
3. Calls `EmbeddingService().embed_batch(texts)` — one network round-trip for the
   whole document.
4. Zips vectors back onto chunk dicts (`zip(..., strict=True)` — `embed_batch` must
   return one vector per input).

Output: `result = {"chunks": [<chunk_dict_with_embedding>, ...]}`.

---

## DocumentIngest StoreChunksNode

**Source:** `app/workflows/document_ingest_workflow_nodes/store_chunks_node.py`

```python
class StoreChunksNode(Node):
```

Terminal node of the `DocumentIngestWorkflow` DAG. Builds `ContentChunk` ORM objects
from the embedded chunk dicts and persists them via `GenericRepository` using the shared
`db_session` factory (no deployment logic in the node — rule 7).

`doc_id` is read from `task_context.event` **before** the persist call. The ORM's
default `expire_on_commit` would clear attributes on the detached instance after the
session closes; reading from the event schema avoids `DetachedInstanceError`.

### `process(task_context) -> TaskContext`

1. Reads `task_context.get_node_output("EmbedChunksNode")["result"]["chunks"]`.
2. Captures `doc_id = task_context.event.doc_id`.
3. Constructs a `ContentChunk` ORM object per chunk (columns: `doc_id`, `position`,
   `section_title`, `is_section_title`, `content`, `embedding`).
4. Calls `self._persist(orm_chunks)`.

Output: `result = {"doc_id": <str>, "chunks_stored": <int>, "embedded": True}`.

### `_persist(chunks) -> None`

Single persistence seam. Opens `db_session`, creates
`GenericRepository(session=session, model=ContentChunk)`, and calls `.create(chunk)`
for each chunk. Tests monkeypatch this method so no real database is touched.

---

## DocumentIngestWorkflow

**Source:** `app/workflows/document_ingest_workflow.py`

```python
class DocumentIngestWorkflow(Workflow):
```

Linear DAG workflow for the `DOCUMENT_INGEST` event type (Phase 1 Project D Task 2).
Ingests a document (plain text or PDF), splits it into section-aware chunks, embeds all
chunks in a single Voyage batch call, and persists one `ContentChunk` row per chunk.

```
ParseDocumentNode
    -> ChunkDocumentNode
        -> EmbedChunksNode
            -> StoreChunksNode
```

No router nodes. `StoreChunksNode` is the terminal node.

### `workflow_schema`

| Property | Value |
|---|---|
| `event_schema` | `DocumentIngestEventSchema` |
| `start` | `ParseDocumentNode` |
| `nodes` | `[ParseDocumentNode, ChunkDocumentNode, EmbedChunksNode, StoreChunksNode]` |
| Connections | Linear: each node connects to the next; `StoreChunksNode.connections = []` |

### Test coverage

- `tests/workflows/test_document_ingest_nodes.py` — 18 node-level unit tests (ParseDocumentNode, ChunkDocumentNode, EmbedChunksNode, StoreChunksNode) plus schema validation.
- `tests/workflows/test_document_ingest_workflow.py` — workflow wiring, DAG structure, `WorkflowValidator` acceptance.
- `tests/workflows/test_document_ingest_e2e.py` — 8 end-to-end tests running all four nodes in sequence on the same `TaskContext` (external services mocked). Verifies cross-node key contracts: each node reads what the previous node actually wrote.

---

## DocumentQAEventSchema

**Source:** `app/schemas/document_qa_schema.py`

```python
class DocumentQAEventSchema(BaseModel):
```

Event payload for `POST /events/` with `workflow_type="DOCUMENT_QA"`. Validates the
inbound Q&A request; `session_id` defaults to a fresh UUID so callers can start a new
session without generating an id client-side.

### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `doc_id` | `UUID` | Yes | — | The ingested document to answer over (must exist in `content_chunks`). |
| `question` | `str` | Yes | — | The user question text. |
| `session_id` | `UUID` | No | `uuid4()` | Q&A session identifier; a new UUID is generated if absent (new session). |
| `corpus` | `str` | No | `"content"` | Corpus to retrieve from: `"content"` (content_chunks) or `"brain"` (brain_documents). |
| `filters` | `dict \| None` | No | `None` | Optional metadata filters for `"brain"` corpus retrieval. Accepted keys: `"project"` (scalar), `"layer"` (array overlap), `"status"` (scalar). Omitting or passing `None` reproduces current behavior exactly; ignored for `"content"` corpus. |
| `include_archived` | `bool` | No | `False` | When `False`, the `"brain"` corpus excludes `status='archived'` docs from retrieval. Set `True` to surface archived historical context. No effect on the `"content"` corpus. |
| `expand_structural` | `bool` | No | `True` | When `True`, the `"brain"` corpus retrieval widens the Stage-1 semantic candidate set through the `related:`-neighborhood (from `brain_edges`) of the top hits before keyword re-rank. Set `False` to disable the structural expansion stage. No effect on the `"content"` corpus. |

### Validation

All seven fields accept their Python-native types; Pydantic coerces UUID strings automatically.
A missing `doc_id` or `question` raises a `ValidationError`. `corpus` is not constrained by the
schema — the `RetrieveChunksNode` corpus dispatch handles unknown values. `filters` keys that are
not declared in `filter_fields` for the target corpus are silently ignored. `include_archived` and
`expand_structural` are explicit boolean fields (not `filters` keys) so both overrides are
type-checked and self-documenting.

---

## EmbedQuestionNode

**Source:** `app/workflows/document_qa_workflow_nodes/embed_question_node.py`

```python
class EmbedQuestionNode(Node):
```

First node in the `DocumentQAWorkflow` linear DAG. Embeds the question text via
`EmbeddingService` and stores both the question string and its embedding vector in
`TaskContext` so downstream nodes can reference the question without re-reading the event.

`RetrieveChunksNode` re-embeds the question internally for its two-stage retrieval call —
that overlap is intentional so the retrieval node remains self-contained and reusable across
workflows. `EmbedQuestionNode` exists to name the step explicitly in the DAG and to expose
the embedding if a future consumer needs it.

### `process(task_context: TaskContext) -> TaskContext`

1. Reads `task_context.event.question`.
2. Calls `EmbeddingService().embed_text(question)` — one network round-trip to the Voyage AI
   embedding endpoint.
3. Writes `{"question": <str>, "embedding": <list[float]>}` under `EmbedQuestionNode` via
   `task_context.update_node(...)`.

### Output contract

```python
task_context.nodes["EmbedQuestionNode"] = {
    "result": {
        "question": "<question text>",
        "embedding": [0.0, ...],   # float vector
    }
}
```

---

## AssembleContextNode

**Source:** `app/workflows/document_qa_workflow_nodes/assemble_context_node.py`

```python
class AssembleContextNode(Node):
```

Third node in the `DocumentQAWorkflow` DAG (after `EmbedQuestionNode` → `RetrieveChunksNode`).
Combines two inputs into a structured context block for `AnswerNode`:

1. **RAG context** — retrieved chunks from `RetrieveChunksNode`, each formatted as
   `Section: <title> (relevance: X.XX)\n<content>` (porting the `build_rag_prompt` format
   from `chat_server.rs` in the rag-engine-rs).
2. **Session history** — prior `{role, content}` turns from the existing `ChatSession`, if
   one exists for the current `session_id`.

### `process(task_context: TaskContext) -> TaskContext`

**Reads:**
- `RetrieveChunksNode` output: `chunks` list of dicts with `content`, `section_title`, `score`.
- `task_context.event.session_id` — used to load prior turns.
- `task_context.event.question` — passed through for `AnswerNode`.

**Writes** `{"context": <str>, "history": <list[dict]>, "question": <str>}` under
`AssembleContextNode` via `task_context.update_node(...)`.

Chunks with a `None` `section_title` are rendered as `"General"`. The context block joins
all formatted chunks with `"\n\n"` separators.

### Output contract

```python
task_context.nodes["AssembleContextNode"] = {
    "result": {
        "context": "Section: Intro (relevance: 0.92)\n...\n\nSection: ...",
        "history": [{"role": "user", "content": "..."}, ...],
        "question": "<question text>",
    }
}
```

### `_load_session(session_id) -> ChatSession | None`

Mockable DB seam. Loads the `ChatSession` by `session_id` via `GenericRepository` inside a
`db_session` context manager. Tests monkeypatch this method to inject a fixture session or
`None` without any real database connection.

---

## AnswerNode

**Source:** `app/workflows/document_qa_workflow_nodes/answer_node.py`

```python
class AnswerNode(AgentNode):
```

Fourth node in the `DocumentQAWorkflow` DAG. `AgentNode` subclass that generates a grounded
answer from the assembled RAG context and prior session memory produced by `AssembleContextNode`.

The system prompt is loaded from `app/prompts/document_qa_answer.j2` via `PromptManager` — no
prompt is hardcoded in Python (CLAUDE.md rule 2). `run_agent_recorded` is used (not
`self.agent.run_sync`) so per-node telemetry (input tokens, output tokens, model) is captured
and surfaced in the data contract read by Bastion (D30).

### `OutputType`

```python
class OutputType(AgentNode.OutputType):
    answer: str
    cited_sections: list[str]
```

| Field | Type | Description |
|---|---|---|
| `answer` | `str` | The grounded answer to the user question. |
| `cited_sections` | `list[str]` | Section titles cited in the answer (may be empty). |

### `get_agent_config() -> AgentConfig`

Returns an `AgentConfig` with:

| Key | Value |
|---|---|
| `system_prompt` | `PromptManager().get_prompt("document_qa_answer")` (from `.j2`) |
| `output_type` | `AnswerNode.OutputType` |
| `deps_type` | `None` |
| `model_provider` | `ModelProvider.CLAUDE_CODE_SDK` |
| `model_name` | `"sonnet"` |

### `process(task_context: TaskContext) -> TaskContext`

**Reads:**
- `AssembleContextNode` output: `context`, `history`, `question`.

**User prompt shape** — a JSON object passed to the agent:
```json
{
  "prior_conversation": [...],
  "document_context": "...",
  "question": "..."
}
```

**Writes** the serialized `OutputType` under `AnswerNode` via `task_context.update_node(...)`.

### Output contract

```python
task_context.nodes["AnswerNode"] = {
    "result": {
        "answer": "<grounded answer>",
        "cited_sections": ["Intro", ...],
    }
}
```

---

## UpdateSessionMemoryNode

**Source:** `app/workflows/document_qa_workflow_nodes/update_session_memory_node.py`

```python
class UpdateSessionMemoryNode(Node):
```

Terminal node of the `DocumentQAWorkflow` DAG. Loads or creates the `ChatSession` for the
current `session_id`, appends the user question and assistant answer as a new turn pair,
extends `topics_covered` with any cited sections (deduplicated), and persists the session via
`GenericRepository` (CLAUDE.md rule 7 — no deployment logic inside the node).

### `process(task_context: TaskContext) -> TaskContext`

**Reads:**
- `AssembleContextNode` output: `question`.
- `AnswerNode` output: `answer` and `cited_sections` (handles both Pydantic model instance and
  dict forms, since `run_agent_recorded` may store either depending on the `node_run` path).
- `task_context.event`: `session_id`, `doc_id`.

**Logic:**
1. Loads the existing `ChatSession` via `_load_session(session_id)`.
2. If none exists, creates a new `ChatSession(id=session_id, doc_id=doc_id, turns=[], topics_covered=[])`.
3. Appends `{"role": "user", "content": question}` and `{"role": "assistant", "content": answer}`.
4. Extends `topics_covered` with `cited_sections`, skipping duplicates.
5. Calls `_persist(chat_session)` — `create` for new sessions, `update` (merge) for existing.
6. Writes `{"session_id": <str>, "turns": <int>}` under `UpdateSessionMemoryNode`.

### Output contract

```python
task_context.nodes["UpdateSessionMemoryNode"] = {
    "result": {
        "session_id": "<uuid-str>",
        "turns": 2,   # total turns after append (always even: user+assistant pairs)
    }
}
```

### `_load_session(session_id) -> ChatSession | None`

Mockable DB seam. Loads `ChatSession` by id via `GenericRepository` inside `db_session`.

### `_persist(chat_session: ChatSession) -> None`

Mockable DB seam. Uses `GenericRepository.exists(id=...)` to decide `create` vs `update`.
Tests monkeypatch both seams to avoid any real database connection.

---

## DocumentQAWorkflow

**Source:** `app/workflows/document_qa_workflow.py`

```python
class DocumentQAWorkflow(Workflow):
```

Grounded Q&A workflow over ingested documents (Phase 1 Project D). Embeds the user question,
retrieves the most relevant chunks via two-stage hybrid retrieval, assembles the RAG context
alongside prior session turns, generates a grounded answer, and persists the new turn to the
`ChatSession`.

**Graph (linear DAG — no router):**

```
EmbedQuestionNode
    -> RetrieveChunksNode
        -> AssembleContextNode
            -> AnswerNode
                -> UpdateSessionMemoryNode
```

### `workflow_schema`

| Property | Value |
|---|---|
| `event_schema` | `DocumentQAEventSchema` |
| `start` | `EmbedQuestionNode` |
| `nodes` | `[EmbedQuestionNode, RetrieveChunksNode, AssembleContextNode, AnswerNode, UpdateSessionMemoryNode]` |
| Connections | Linear: each node connects to the next; `UpdateSessionMemoryNode.connections = []` |

### Test coverage

- `tests/workflows/test_document_qa_nodes.py` — 24 node-level unit tests covering all five nodes, including the `AnswerNode` telemetry recording path (`run_agent_recorded` with `node_runs` populated) and the `UpdateSessionMemoryNode` Pydantic-model output path.
- `tests/workflows/test_document_qa_workflow.py` — workflow wiring, DAG structure, `WorkflowValidator` acceptance.
- `tests/workflows/test_document_qa_e2e.py` — 9 end-to-end tests running all five nodes in sequence (external services and DB calls mocked). Explicitly asserts that `AnswerNode` stores a Pydantic `OutputType` instance (not a dict) and that `UpdateSessionMemoryNode` handles it correctly end-to-end.
