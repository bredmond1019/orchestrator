---
type: Reference
title: WorkflowSchema & NodeConfig — How They Work
description: How WorkflowSchema and NodeConfig work — declaring a workflow's start, nodes, and connections.
doc_id: workflow-schema
layer: [engine]
project: python-orchestration
status: active
keywords: [WorkflowSchema, NodeConfig, DAG declaration, workflow graph, schema.py]
related: [app-architecture-overview, api-reference]
---

# WorkflowSchema & NodeConfig — How They Work

`app/core/schema.py`

---

## The big picture

Before a single line of your workflow logic runs, you have to declare the graph. `WorkflowSchema` and `NodeConfig` are that declaration — they describe the shape of your workflow as data, not as code.

Think of them as a blueprint: which nodes exist, how they connect to each other, which one runs first, and which ones run in parallel or perform routing.

The workflow engine (`Workflow` class in `workflow.py`) reads this blueprint at startup, validates it, and uses it to walk the graph at runtime.

---

## Step 1 — `NodeConfig`: one node's slot in the graph

```python
# app/core/schema.py
class NodeConfig(BaseModel):
    node: Type[Node]
    connections: List[Type[Node]] = Field(default_factory=list)
    is_router: bool = False
    description: Optional[str] = None
    parallel_nodes: Optional[List[Type[Node]]] = Field(default_factory=list)
```

Each `NodeConfig` instance describes **one node** in the workflow. Its fields:

- **`node`** — the node *class* itself (not an instance). e.g. `FilterSpamNode`.
- **`connections`** — a list of node classes this node can hand off to when it finishes. A normal node has exactly one connection (the next node). A router node can list several possible destinations. An end node has none.
- **`is_router`** — set to `True` if this node has multiple connections and uses routing logic to choose between them. The validator enforces this: multiple connections without `is_router=True` raises an error.
- **`description`** — optional human-readable description of what this node does. Not used at runtime.
- **`parallel_nodes`** — if this is a `ParallelNode`, list the node classes to run in parallel inside it. The `ParallelNode` reads this list at runtime from `task_context.metadata["nodes"][self.__class__]`.

---

## Step 2 — `WorkflowSchema`: the whole graph

```python
class WorkflowSchema(BaseModel):
    description: Optional[str] = None
    event_schema: Type[BaseModel]
    start: Type[Node]
    nodes: List[NodeConfig]
```

- **`description`** — optional human-readable label for the whole workflow.
- **`event_schema`** — the Pydantic model class used to validate incoming events before the workflow starts. e.g. `CustomerCareEventSchema`. If the incoming JSON doesn't validate against this, the workflow rejects it before any node runs.
- **`start`** — the node class to run first. The workflow engine instantiates this class and calls its `process()` method to kick things off.
- **`nodes`** — the list of `NodeConfig` objects for nodes that have explicit outgoing connections. Terminal nodes (no outgoing edges) and parallel children do not need their own `NodeConfig` entry here — they are auto-registered by `_initialize_nodes()`. The Step 3 example correctly shows only three `NodeConfig` entries even though the customer care workflow has many more nodes.

---

## Step 3 — Reading a real example

Here's the actual Customer Care workflow schema from `app/workflows/customer_care_workflow.py`:

```python
WorkflowSchema(
    description="",
    event_schema=CustomerCareEventSchema,
    start=AnalyzeTicketNode,
    nodes=[
        NodeConfig(
            node=AnalyzeTicketNode,
            connections=[TicketRouterNode],
            parallel_nodes=[
                DetermineTicketIntentNode,
                FilterSpamNode,
                ValidateTicketNode,
            ],
        ),
        NodeConfig(
            node=TicketRouterNode,
            connections=[
                CloseTicketNode,
                EscalateTicketNode,
                GenerateResponseNode,
                ProcessInvoiceNode,
            ],
            is_router=True,
        ),
        NodeConfig(
            node=GenerateResponseNode,
            connections=[SendReplyNode],
        ),
    ],
)
```

Notice how short this is — **only three `NodeConfig` entries**, not one per node in the graph. You don't need to declare terminal nodes (like `CloseTicketNode`, `SendReplyNode`) or the parallel children (`FilterSpamNode`, etc.) as their own `NodeConfig` entries. The engine handles them automatically:

- **Terminal router destinations** (`CloseTicketNode`, `EscalateTicketNode`, `ProcessInvoiceNode`) appear only in `TicketRouterNode`'s `connections` list. `Workflow._initialize_nodes()` auto-registers them with a bare `NodeConfig` (no connections) when it processes the connection list. Note: `SendReplyNode` is also a terminal node, but it is `GenerateResponseNode`'s connection target, not the router's.
- **Parallel children** (`DetermineTicketIntentNode`, `FilterSpamNode`, `ValidateTicketNode`) are declared in `parallel_nodes` on `AnalyzeTicketNode`'s config. They are launched by `execute_nodes_in_parallel()` inside `AnalyzeTicketNode.process()`, not walked to directly by the engine.

Reading this schema, you can reconstruct the whole workflow:

- **Entry point:** `AnalyzeTicketNode`.
- **First step:** runs three nodes in parallel, then hands off to `TicketRouterNode`.
- **Router:** `TicketRouterNode` (4 possible destinations).
- **Normal path:** `GenerateResponseNode` → `SendReplyNode`.
- **Everything else** is a terminal node reached directly from the router.

---

## Step 4 — How `NodeConfig` is used at runtime

When the workflow starts, `Workflow._initialize_nodes()` builds a complete lookup dict — one entry per node class, including connection targets that don't have their own explicit `NodeConfig`:

```python
# app/core/workflow.py — _initialize_nodes()
nodes = {}
for node_config in self.workflow_schema.nodes:
    nodes[node_config.node] = node_config          # register declared nodes
    for connected_node in node_config.connections:
        if connected_node not in nodes:
            nodes[connected_node] = NodeConfig(node=connected_node)  # auto-register targets
return nodes
```

This dict is stored in `task_context.metadata["nodes"]`. That's how `ParallelNode.execute_nodes_in_parallel()` finds its `parallel_nodes` list even though the parallel children don't appear as top-level keys:

```python
node_config: NodeConfig = task_context.metadata["nodes"][self.__class__]
parallel_nodes = node_config.parallel_nodes   # declared on AnalyzeTicketNode's config
```

`metadata["nodes"]` has two distinct consumers: **(1)** `ParallelNode.execute_nodes_in_parallel()` uses it to resolve its `parallel_nodes` list at runtime; **(2)** the workflow engine's `_get_next_node_class()` does **NOT** use it — it scans `self.workflow_schema.nodes` instead. These are different lookup mechanisms for different purposes.

**How the engine determines the next node** (`_get_next_node_class()`, workflow.py lines 146–158):

```python
# Simplified from workflow.py _get_next_node_class()
node_config = next(
    (nc for nc in self.workflow_schema.nodes if nc.node == current_node_class),
    None,
)
if not node_config or not node_config.connections:
    return None                    # terminal node — stops the run() while loop

if node_config.is_router:
    return self._handle_router(...)  # evaluates routing rules

return node_config.connections[0]    # linear node — one connection only
```

`_get_next_node_class()` scans `self.workflow_schema.nodes`, not `metadata["nodes"]`. Terminal nodes — those auto-registered by `_initialize_nodes()` because they appear only as connection targets — are absent from `self.workflow_schema.nodes`, so the scan returns `None`, which terminates the `while` loop in `run()`. This is the mechanism that ends every workflow.

**Lifecycle:** `task_context.metadata["nodes"]` is injected at the start of `run()` and removed via `metadata.pop("nodes")` before `run()` returns (workflow.py line 131). A `TaskContext` retrieved from the database will **NOT** have `metadata["nodes"]` — it is only present during active workflow execution.

**Termination:** the `run()` while loop terminates when `_get_next_node_class()` returns `None`. This happens when the current node is not found in `self.workflow_schema.nodes` (terminal nodes auto-registered by `_initialize_nodes()` are absent from this list) or when a found `NodeConfig` has an empty `connections` list. There is no explicit "stop" marker — terminal nodes stop the workflow by being absent from the schema's node list.

---

## Mental model: schema as a data structure, not code

The schema is pure data. It's Pydantic models all the way down — no logic, no side effects. This separation means:

- You can validate the whole graph before running it (the `WorkflowValidator` does this).
- You can serialise the schema to JSON and inspect it.
- The workflow engine (`workflow.py`) is completely generic — it doesn't know anything about Customer Care tickets. It just walks whatever graph you give it.
- Adding a new workflow means writing a new `WorkflowSchema` with new `NodeConfig` entries — zero changes to the engine.
