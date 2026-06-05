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

This is the only method on `TaskContext`. It's how nodes write their output back into
the shared ledger.

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

Node names are currently hard-coded strings — this is flagged as a known bug in
`CLAUDE.md` (router nodes). The same risk applies anywhere a node reads another
node's output by string key: a rename or typo produces a silent `KeyError` miss
instead of a clear error.

---

## Step 3 — Serialization to the database

When the workflow finishes, the caller (the Celery task) serializes the final
`TaskContext` to JSON and stores it in the `task_context` column of the `events`
table in PostgreSQL:

```python
# app/worker/tasks.py (conceptually)
task_context = workflow.run(event)
repo.update(event_id, task_context=task_context.model_dump())
```

Because `TaskContext` is a Pydantic model, `.model_dump()` produces a plain Python
dict that is JSON-serializable — the full ledger of every node's output, the parsed
event, and any residual metadata.

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

- **String keys are the current weak point** — `nodes["AnalyzeTicketNode"]` works,
  but it's a stringly-typed interface. A rename, a typo, or reading a key before the
  writing node has run all produce runtime errors rather than type errors. The
  pattern to watch for when extending: always use `self.node_name` when writing,
  and consider whether the reading node has a hard dependency on execution order.

- **`metadata` is the escape hatch** — it's where the framework injects things nodes
  might need that don't belong in the event (the node registry, feature flags,
  per-run config). Keep it for framework concerns; don't use it as a secondary
  `nodes` dict for node-to-node communication.
