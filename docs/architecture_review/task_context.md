# How `task.py` Works — Step-by-Step

`app/core/task.py` is one of the smallest files in the codebase and one of the most
important. It defines `TaskContext` — the single shared state object that flows
through every node in a workflow. If `workflow.py` is the factory manager, `TaskContext`
is the clipboard that every station writes to and reads from.

---

## The big picture before reading any code

Every node in a workflow receives `task_context` as input and returns it as output.
This means every node can see everything every previous node has produced. There is no
explicit "pass data from node A to node B" wiring — the context is the wire.

```
event arrives
     │
     ▼
TaskContext created
     │
   .event = CustomerCareEventSchema(...)   ← the validated incoming event
   .nodes = {}                             ← empty; nodes will fill this
   .metadata = {}                          ← framework config (e.g. node registry)
     │
     ▼
AnalyzeTicketNode.process(ctx)
  → ctx.nodes["AnalyzeTicketNode"] = {"intent": "refund", "confidence": 0.94}
     │
     ▼
TicketRouterNode.process(ctx)
  → reads ctx.nodes["AnalyzeTicketNode"]["intent"]
  → ctx.nodes["TicketRouterNode"] = {"next_node": "ProcessInvoiceNode"}
     │
     ▼
ProcessInvoiceNode.process(ctx)
  → reads ctx.nodes["AnalyzeTicketNode"]["confidence"]
  → ctx.nodes["ProcessInvoiceNode"] = {"invoice_id": "INV-881", "status": "issued"}
     │
     ▼
final TaskContext — full ledger of every node's output
```

The `nodes` dict is the ledger. Every node appends its own row. Any downstream node
can read any upstream row.

---

## Step 1 — The model definition

```python
class TaskContext(BaseModel):
    event: Any
    nodes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Stores results and state from each node's execution",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Stores workflow-level metadata and configuration",
    )
```

`TaskContext` inherits from Pydantic's `BaseModel`. That gives it:
- **Type validation** on construction.
- **Serialization to JSON** (`.model_dump()`) — so the entire context can be stored
  in the `task_context` JSON column in PostgreSQL after the workflow finishes.
- **Immutable field definitions** — the schema is explicit; you can't accidentally
  introduce a new top-level field without declaring it.

### The three fields

**`event: Any`**

The original trigger event. Set twice in the workflow:

1. First as the raw Python dict when `TaskContext` is constructed:
   ```python
   task_context = TaskContext(event=event)   # event is a dict here
   ```

2. Then immediately replaced with the validated Pydantic model:
   ```python
   task_context.event = self.workflow_schema.event_schema(**event)
   ```

After step 2, `task_context.event` is a typed object — e.g., a
`CustomerCareEventSchema` instance with `.ticket_id`, `.customer_email`, etc. Every
node accesses the event through this typed object, never a raw dict.

**`nodes: Dict[str, Any]`**

The accumulating output ledger. Keys are node names (the class name as a string,
e.g. `"AnalyzeTicketNode"`). Values are whatever the node chose to store — typically
a dict of named fields.

`default_factory=dict` means every new `TaskContext` starts with an empty dict, not
`None`. This is standard Pydantic for mutable defaults (you never write
`nodes: dict = {}` in Pydantic — that would share one dict across all instances).

**`metadata: Dict[str, Any]`**

Workflow-level configuration and framework internals. The `Workflow` class uses this
to inject the node registry before the run loop starts:

```python
task_context.metadata["nodes"] = self.nodes   # the class → NodeConfig map
```

Nodes that need to know about the graph (parallel nodes, certain routers) read from
here. The registry is stripped out before the context is returned:

```python
task_context.metadata.pop("nodes")
```

This field is also where you'd put workflow-level configuration that shouldn't live
in the event schema — priority flags, feature flags, per-run overrides.

---

## Step 2 — `update_node`: the write interface

```python
def update_node(self, node_name: str, **kwargs):
    self.nodes[node_name] = {**self.nodes.get(node_name, {}), **kwargs}
```

This is how most nodes write their output back into the shared ledger. Exception: `BaseRouter.process()` (`router.py`) writes directly to `task_context.nodes[self.node_name] = {'next_node': next_node.node_name}` without calling `update_node` — bypassing the merge semantics. For all non-router nodes, `update_node` is the correct and idiomatic write interface.

**How it works:**

`self.nodes.get(node_name, {})` — fetch any existing dict stored under this node's
name, or an empty dict if this is the first write.

`{**existing, **kwargs}` — merge the existing dict with the new kwargs. If the same
key appears in both, the new value wins.

`self.nodes[node_name] = ...` — store the merged result.

**Why merge instead of replace?**

A node might call `update_node` multiple times (e.g., writing a preliminary result,
then adding a confidence score after a second API call). Merging preserves earlier
writes rather than wiping them.

**How a node uses it:**

```python
class AnalyzeTicketNode(AgentNode):
    def process(self, task_context: TaskContext) -> TaskContext:
        result = self._run_agent(task_context.event.body)    # AI call
        task_context.update_node(
            self.node_name,
            intent=result.intent,
            confidence=result.confidence,
            summary=result.summary,
        )
        return task_context
```

`self.node_name` is a `@property` defined on the `Node` base class:

```python
@property
def node_name(self) -> str:
    return self.__class__.__name__
```

It returns the class name as a string. Using it as the key guarantees the ledger
entry matches the class that wrote it — no manual string maintenance needed.

**How a downstream node reads it:**

```python
class ProcessInvoiceNode(AgentNode):
    def process(self, task_context: TaskContext) -> TaskContext:
        intent = task_context.nodes["AnalyzeTicketNode"]["intent"]
        if intent == "refund":
            ...
```

**How a router node reads it (preferred):**

```python
class TicketRouterNode(BaseRouter):
    def determine_next_node(self, task_context: TaskContext):
        output = task_context.get_node_output("AnalyzeTicketNode")
        if output["intent"] == "refund":
            return ProcessRefundNode()
        return None
```

Node names are hard-coded strings — a rename or typo produces a `KeyError`. For
router nodes, `get_node_output()` is preferred over direct dict access because it
raises a descriptive error naming the missing node and listing completed nodes.
Direct `task_context.nodes[name]` access still works in non-router nodes where the
execution order is fixed and obvious.

---

## Step 3 — `get_node_output`: the safe read interface

```python
def get_node_output(self, node_name: str) -> Any:
```

Added alongside `update_node` to give router nodes a safe way to read upstream
output without silently absorbing a misuse. When a router calls
`task_context.get_node_output("AnalyzeTicketNode")` and that node has not run yet,
the raised `KeyError` includes three pieces of diagnostic information:

1. The name of the node that was requested.
2. The list of nodes that *have* completed so far.
3. A suggestion to check the node's position in the `WorkflowSchema`.

Compare the two patterns:

```python
# Before — raw dict access; produces unhelpful "KeyError: 'AnalyzeTicketNode'"
intent = task_context.nodes["AnalyzeTicketNode"]["intent"]

# After — descriptive error that names the problem and the fix
output = task_context.get_node_output("AnalyzeTicketNode")
intent = output["intent"]
```

The method is additive — existing code that uses `task_context.nodes[name]` directly
continues to work unchanged. New router nodes should prefer `get_node_output()`.

**Caveat:** `get_node_output()` detects execution-order problems at runtime, not at
schema-definition time. A mis-ordered `WorkflowSchema` still fails during a workflow
run — the improvement is that the error message makes the cause obvious rather than
leaving the developer to infer it from a bare key miss.

---

## Step 4 — Serialization to the database

When the workflow finishes, the caller (the Celery task) serializes the final
`TaskContext` to JSON and stores it in the `task_context` column of the `events`
table in PostgreSQL:

```python
# Conceptual — actual tasks.py chains the call:
task_context = workflow.run(db_event.data).model_dump(mode="json")
db_event.task_context = task_context
repository.update(obj=db_event)
```

Because `TaskContext` is a Pydantic model, `.model_dump(mode='json')` produces a
JSON-serializable dict. The `mode='json'` argument is required — without it, Pydantic
returns Python-native types (datetime, UUID, Enum, nested model instances) that are
not guaranteed to be JSON-serializable. The actual production code in tasks.py uses
`.model_dump(mode='json')` explicitly.

> **Note on `mode='json'`:** The `mode='json'` argument to `.model_dump()` is what
> actually enforces JSON safety. This is not a detail — it is the mechanism. A bare
> `.model_dump()` call returns Python-native types that will cause JSON serialization
> to fail downstream.

This is how you inspect a run after the fact: query the `events` table, pull the
`task_context` JSON column, and you have a complete audit trail of what every node
produced.

---

## Complete field summary

| Field | Type | Set by | Read by |
|---|---|---|---|
| `event` | `Any` → typed Pydantic model | `Workflow.run()` | Every node (typed access via `.event.field`) |
| `nodes` | `Dict[str, Any]` | Each node via `update_node()` | Any downstream node, the router, the caller |
| `metadata` | `Dict[str, Any]` | `Workflow.run()` (injects node registry) | Parallel nodes, routers; stripped before return |

---

## Key design properties worth knowing

- **One object, one source of truth** — there is no implicit parameter threading
  between nodes. If Node 3 needs Node 1's output, it reads `task_context.nodes["Node1"]`.
  The context is the only communication channel.

- **Nodes are stateless; the context is stateful** — nodes are instantiated fresh on
  every call and carry no instance state. Everything that must persist across nodes
  lives in `TaskContext`. This makes individual nodes easy to test in isolation.

- **String keys — use `get_node_output()` for reads** — `nodes["AnalyzeTicketNode"]`
  works, but it's a stringly-typed interface. A rename or typo produces a bare
  `KeyError`. Reading a key before the writing node has run does too. New router nodes
  should call `task_context.get_node_output("AnalyzeTicketNode")` instead: the method
  raises a descriptive `KeyError` that names the missing node, lists nodes completed
  so far, and points to the `WorkflowSchema` ordering as the fix. The pattern to
  watch for when extending: always use `self.node_name` when writing, and use
  `get_node_output()` when reading in a router.

- **`metadata` is the escape hatch** — it's where the framework injects things nodes
  might need that don't belong in the event (the node registry, feature flags,
  per-run config). Keep it for framework concerns; don't use it as a secondary
  `nodes` dict for node-to-node communication.
