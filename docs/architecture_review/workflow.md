---
type: Reference
title: Workflow (workflow.py) — How It Works
description: How workflow.py works — the Workflow base class and its execution loop.
---

# How `workflow.py` Works — Step-by-Step

`app/core/workflow.py` is the orchestration engine. It reads a graph definition,
validates it, and walks it node-by-node at runtime — passing a shared state object
through every step. Everything else in the framework plugs into this loop.

---

## The big picture before reading any code

Think of a workflow as a conveyor belt through a factory. Each station (Node) does
one thing and hands the part to the next station. The `Workflow` class is the
factory manager: it checks the blueprint before starting, sets up every station,
then drives the belt from start to finish.

The core data-flow is:

```
raw event dict
     │
     ▼
TaskContext (shared state container)
     │
     ▼
Node 1.process(ctx) → ctx  ─┐
Node 2.process(ctx) → ctx   │  same ctx object, accumulated results
Node 3.process(ctx) → ctx  ─┘
     │
     ▼
final TaskContext returned to caller
```

---

## Step 1 — The class declaration and `workflow_schema`

```python
class Workflow(ABC):
    workflow_schema: ClassVar[WorkflowSchema]
```

`Workflow` is an **Abstract Base Class**. You never instantiate it directly — you
subclass it and declare one class variable: `workflow_schema`. That variable holds the
entire graph definition (which node is first, what connects to what, what Pydantic
schema validates the incoming event).

`ClassVar` means the schema is shared across all instances of a subclass — it
belongs to the class, not to any particular run.

A concrete subclass looks like this:

```python
class CustomerCareWorkflow(Workflow):
    workflow_schema = WorkflowSchema(
        description="Support ticket processing",
        event_schema=CustomerCareEventSchema,
        start=AnalyzeTicketNode,
        nodes=[
            NodeConfig(node=AnalyzeTicketNode, connections=[TicketRouterNode]),
            NodeConfig(node=TicketRouterNode, connections=[...], is_router=True),
            ...
        ]
    )
```

That single `workflow_schema` declaration is the complete blueprint for how events
flow through the pipeline.

---

## Step 2 — `__init__`: validate first, then build

```python
def __init__(self):
    self.validator = WorkflowValidator(self.workflow_schema)
    self.validator.validate()                          # raises ValueError on bad graph
    self.nodes: Dict[Type[Node], NodeConfig] = self._initialize_nodes()
    load_dotenv()
```

Three things happen before the workflow can be used:

1. **Validate** — `WorkflowValidator` runs two checks on the graph:
   - DFS cycle detection (no node should be its own ancestor).
   - BFS reachability (every declared node must be reachable from `start`).
   If either check fails, a `ValueError` is raised immediately — the workflow
   never reaches a broken state at runtime.

2. **Initialize nodes** — `_initialize_nodes()` builds a lookup table mapping each
   node *class* to its `NodeConfig`. This is the internal registry the DAG-walk loop
   uses to know what connections each node has.

3. **Load env** — `load_dotenv()` ensures any `.env` file is loaded so that API keys
   and config values are available to nodes when they run.

`WorkflowValidator.validate()` calls two methods, which together run three sub-checks:

```python
def validate(self):
    self._validate_dag()          # sub-checks: cycle detection + reachability
    self._validate_connections()  # sub-check: connection-count rule
```

- `_validate_dag()`:
  - `_has_cycle()` — DFS traversal; returns True if a cycle is detected. The raise ValueError('Workflow schema contains a cycle') is in its caller, _validate_dag() (validate.py), which raises when _has_cycle() returns True.
  - `_get_reachable_nodes()` — BFS from `start`; returns a Set[Type[Node]] of reachable nodes. The raise ValueError for unreachable nodes is in its caller, _validate_dag(), which compares the returned set against all declared nodes and raises if any are missing.
- `_validate_connections()` — iterates every `NodeConfig`; raises if a non-router node
  has more than one connection. This is the enforcement that gives linear nodes their
  "one outgoing edge only" guarantee.

---

## Step 3 — `_initialize_nodes`: build the class → config registry

```python
def _initialize_nodes(self) -> Dict[Type[Node], NodeConfig]:
    nodes = {}
    for node_config in self.workflow_schema.nodes:
        nodes[node_config.node] = node_config          # register the declared node
        for connected_node in node_config.connections:
            if connected_node not in nodes:
                connected_node_config = NodeConfig(node=connected_node)
                nodes[connected_node] = connected_node_config   # register sink nodes too
    return nodes
```

The `workflow_schema.nodes` list contains `NodeConfig` objects for nodes that have
outgoing connections. But terminal nodes (leaf nodes with no outgoing edges) may only
appear in a `connections` list, not as their own `NodeConfig` entry.

This loop handles that: for every connection target that hasn't been seen yet, it
creates a bare `NodeConfig` with empty connections and registers it. After this runs,
`self.nodes` is a complete registry of every node class in the graph — you can look
up any node by its class and get its config.

Example: if the schema declares `AnalyzeNode → RouterNode → [ResponseNode, EscalateNode]`,
after `_initialize_nodes` the dict will have entries for all four classes, even if
`ResponseNode` and `EscalateNode` were only mentioned as connection targets.

**Important:** `_initialize_nodes()` only iterates `node_config.connections` — it does not register nodes listed in `node_config.parallel_nodes`. Nodes declared exclusively in `parallel_nodes` are not added to `self.nodes` here; `ParallelNode` resolves them at runtime from `task_context.metadata['nodes']` instead.

**Note:** `Workflow` also defines a static `_instantiate_node()` method but it is never called by the run loop or by `_get_next_node_class`. Node instantiation always happens inline (`current_node()` in `run()`, `self.nodes[current_node_class].node()` in `_get_next_node_class`). Treat `_instantiate_node` as dead code.

---

## Step 4 — `run()`: the DAG-walk loop

This is the heart of the framework. Read it carefully.

```python
def run(
    self,
    event: Any,
    on_progress: Callable[[TaskContext], None] | None = None,
) -> TaskContext:
    task_context = TaskContext(event=event)                      # 1. create shared state
    task_context.event = self.workflow_schema.event_schema(**event)  # 2. parse + validate event
    task_context.metadata["nodes"] = self.nodes                  # 3. inject registry

    # 4. seed all nodes PENDING + emit initial snapshot
    for node_cls in self.nodes:
        task_context.node_runs.setdefault(node_cls.__name__, NodeRun(status=NodeStatus.PENDING))
    if on_progress:
        on_progress(task_context)

    current_node_class = self.workflow_schema.start              # 5. begin at start node

    while current_node_class:                                    # 6. walk until None
        current_node = self.nodes[current_node_class].node
        with self.node_context(current_node_class.__name__, task_context):  # 7. stamp envelope + log
            task_context = current_node().process(task_context)  # 8. execute node

        if on_progress:                                          # 9. emit boundary snapshot
            on_progress(task_context)

        current_node_class = self._get_next_node_class(         # 10. advance
            current_node_class, task_context
        )

    task_context.metadata.pop("nodes")                          # 11. clean up
    return task_context
```

Walk through each numbered step:

**1. Create `TaskContext`** — A fresh Pydantic model is created with the raw event dict
in `event`. This object is the single shared state that every node reads from and
writes to.

**2. Parse and validate the event** — The raw dict is parsed through the workflow's
`event_schema` (e.g., `CustomerCareEventSchema(**event)`). This replaces the raw dict
with a typed Pydantic model, so every downstream node gets a validated, type-checked
event object — not an arbitrary dict.

**3. Inject the node registry** — `self.nodes` (the class → NodeConfig map) is stored
inside `task_context.metadata`. This makes it available to nodes that need to know
about the graph structure — most nodes don't need this, but parallel nodes and routers
do.

**4. Seed all nodes `PENDING` and emit the initial snapshot** — Every node in
`self.nodes` is seeded with `NodeStatus.PENDING` in `task_context.node_runs` using
`setdefault` (so a `NodeRun` already stamped by a prior step is never overwritten). If
`on_progress` is provided, it is invoked once here — this gives an observer the full DAG
in `PENDING` state before any node runs. Passing `None` (the default) skips this entirely.

**5. Set `current_node_class` to the start node** — The `start` field on the schema
names the entry point. Execution always begins there.

**6. `while current_node_class:`** — The loop runs as long as there's a next node. When
`_get_next_node_class` returns `None` (no more connections), the loop exits. There's
no index, no list — just follow the graph edges until the trail ends.

**7. `node_context` — stamp run envelope + log** — The context manager (covered below)
stamps the per-node `NodeRun` envelope in `task_context.node_runs` (`RUNNING` on entry,
`SUCCESS` or `FAILED` with timestamps on exit) and emits log lines. If the node raises,
it stamps `FAILED` + the error message and re-raises, so the caller (the Celery task)
sees a clean exception with context and the envelope carries the failure detail.

**8. Instantiate and execute the node** — `current_node().process(task_context)`:
- `current_node()` — creates a fresh instance of the node class each time it runs.
- `.process(task_context)` — calls the node's one required method, which reads from
  `task_context`, does its work (an AI call, a DB write, a calculation), writes results
  back to `task_context.nodes`, and returns the updated context.

Note: the node is re-instantiated on every execution. Nodes are stateless — all state
lives in `task_context`.

**9. Emit boundary snapshot** — After `node_context` exits (whether success or failure),
`on_progress(task_context)` is invoked if a callback was provided. The envelope for the
just-completed node already carries `SUCCESS` or `FAILED` at this point. This is the
per-boundary observability hook: a worker closure can use it to flush the updated
`task_context` to the database after each node rather than only at the end.

**10. Advance to the next node** — `_get_next_node_class` is called with the current
node class and the (now-updated) context. It returns either the next node class or
`None`. For linear workflows this is trivial: take `connections[0]`. For router nodes
it evaluates routing logic against the context.

**11. Clean up and return** — Before returning, `nodes` is removed from
`task_context.metadata`. This prevents the internal node registry (which contains
Python class references) from being serialized to JSON when the context is persisted
to the database.

---

## Step 5 — `node_context`: the observability envelope

```python
@contextmanager
def node_context(self, node_name: str, task_context: TaskContext):
    run = task_context.node_runs.setdefault(node_name, NodeRun())
    run.status = NodeStatus.RUNNING
    run.started_at = datetime.now(UTC).isoformat()
    logging.info("Starting node: %s", node_name)
    try:
        yield
    except Exception as e:
        run.status = NodeStatus.FAILED
        run.error = str(e)
        run.completed_at = datetime.now(UTC).isoformat()
        logging.error("Error in node %s: %s", node_name, str(e))
        raise
    else:
        run.status = NodeStatus.SUCCESS
        run.completed_at = datetime.now(UTC).isoformat()
    finally:
        logging.info("Finished node: %s", node_name)
```

A standard Python context manager using `@contextmanager`. It wraps every node
execution and does two things: stamps the per-node `NodeRun` envelope and emits
structured log lines.

**Envelope lifecycle:**
- On entry: creates a `NodeRun` (if not present) in `task_context.node_runs[node_name]`,
  sets `status = RUNNING`, records `started_at` as a UTC ISO-8601 string.
- On clean exit (`else` branch): sets `status = SUCCESS`, records `completed_at`.
- On exception (`except` branch): sets `status = FAILED`, records `error` (stringified
  exception) and `completed_at`, then re-raises.

`SUCCESS` is set in the `else` branch (not `finally`) so it is only stamped on a
clean exit — `FAILED` and `SUCCESS` are mutually exclusive.

The `raise` is important: this does not swallow exceptions. The error is logged and
the envelope is stamped for observability, then the original exception propagates up
to the Celery task. Node implementations never touch `node_runs` directly.

---

## Step 6 — `_get_next_node_class`: advance or route

```python
def _get_next_node_class(
    self, current_node_class: Type[Node], task_context: TaskContext
) -> Optional[Type[Node]]:
    node_config = next(
        (nc for nc in self.workflow_schema.nodes if nc.node == current_node_class),
        None,
    )

    if not node_config or not node_config.connections:
        return None                             # terminal node — stop

    if node_config.is_router:
        router: BaseRouter = self.nodes[current_node_class].node()
        return self._handle_router(router, task_context)

    return node_config.connections[0]           # linear — take the one connection
```

Three cases:

1. **No config or no connections** — this is a terminal node. Return `None`, loop ends.

2. **`is_router=True`** — instantiate the router and call `_handle_router`, which
   evaluates the routing rules against the current context and returns whichever node
   class matches.

   **Important — the router runs twice per pass.** By the time `_get_next_node_class`
   is reached, `current_node().process(task_context)` has already run the router as a
   normal node. `BaseRouter.process()` calls `route()` internally and writes the
   decision to `task_context.nodes`:

   ```python
   def process(self, task_context: TaskContext) -> TaskContext:
       next_node = self.route(task_context)
       task_context.nodes[self.node_name] = {"next_node": next_node.node_name}
       return task_context
   ```

   Then `_get_next_node_class` creates a *second* fresh router instance and calls
   `route()` again via `_handle_router` — this time to produce the node *class* the
   loop should jump to. The routing logic therefore executes twice per router step.
   For stateless routers (which they always should be) this is harmless, but it's
   a redundancy worth knowing about.

3. **Linear node** — take `connections[0]`. Linear nodes are only allowed one
   connection (enforced by the validator), so `[0]` is always the right pick.

Notice that looking up the node config is done by scanning the `workflow_schema.nodes`
list, not `self.nodes`. The schema list is the source of truth for declared
connections; `self.nodes` is only the class → config registry for lookup during
execution.

---

## Step 7 — `_handle_router`: evaluate routing rules

```python
def _handle_router(
    self, router: BaseRouter, task_context: TaskContext
) -> Optional[Type[Node]]:
    next_node = router.route(task_context)
    return next_node.__class__ if next_node else None
```

`router.route(task_context)` evaluates the `BaseRouter`'s list of `RouterNode` rules
in order (first match wins), returning a *node instance* (not a class). This method
then extracts the class from that instance with `.__class__` — because the DAG walk
works in terms of classes, not instances. If no rule matches and there's no fallback,
`None` is returned and the workflow ends.

---

## Complete data-flow diagram

```
Workflow.__init__()
  ├── WorkflowValidator.validate()
  │     ├── _validate_dag()
  │     │     ├── _has_cycle()    (DFS — returns bool)
  │     │     └── _get_reachable_nodes()  (BFS — returns Set[Type[Node]])
  │     └── _validate_connections()
  └── _initialize_nodes() → self.nodes: {NodeClass → NodeConfig}

Workflow.run(event)
  ├── TaskContext(event=event)
  ├── event_schema(**event)  → typed Pydantic event
  ├── metadata["nodes"] = self.nodes
  │
  └── while current_node_class:
        ├── node_context(name, task_context)  → stamps NodeRun envelope + logs
        ├── NodeClass().process(task_context)  → updated task_context
        └── _get_next_node_class(current, task_context)
              ├── no connections → None  (exit loop)
              ├── is_router → _handle_router() → router.route() → NodeClass
              └── linear   → connections[0]
```

---

## Key design properties worth knowing

- **Stateless nodes** — every node is instantiated fresh on each execution. No node
  carries state between runs. All state is in `TaskContext`.

- **No hardcoded model or DB calls** — `Workflow.run()` knows nothing about AI models
  or databases. Those are the concern of individual nodes. The framework instantiates
  every node bare — `current_node()` with no arguments — so nodes must source their own
  config (e.g., from environment variables via `load_dotenv`).

- **Fail fast** — validation runs at `__init__` time, not at `run()` time. A broken
  graph is caught when the workflow is first instantiated (typically at Celery worker
  startup), not when the first event arrives in production.

- **Single responsibility** — the loop in `run()` only knows how to walk a graph and
  call `process()`. Routing logic lives in `BaseRouter`; per-node logic lives in the
  node; shared state lives in `TaskContext`. Each layer has exactly one job.
