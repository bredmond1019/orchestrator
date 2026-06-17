---
type: Reference
title: WorkflowValidator — How It Works
description: How WorkflowValidator works — validating a workflow graph before execution.
---

# WorkflowValidator — How It Works

`app/core/validate.py`

---

## The big picture

`WorkflowValidator` is a safety net. Before any workflow runs a single node, the validator checks that the graph you declared in `WorkflowSchema` is actually a valid directed acyclic graph (DAG). If it's not — cycles, unreachable nodes, or misconfigured routers — it raises a `ValueError` immediately with a clear message.

This runs inside `Workflow.__init__()`, which means bad graphs are caught at startup, not mid-run after half your nodes have already executed.

---

## Step 1 — The entry point: `validate()`

```python
class WorkflowValidator:
    def __init__(self, workflow_schema: WorkflowSchema):
        self.workflow_schema = workflow_schema

    def validate(self):
        self._validate_dag()
        self._validate_connections()
```

`validate()` runs two independent checks in sequence:
1. **`_validate_dag()`** — checks the graph structure: no cycles, all nodes reachable.
2. **`_validate_connections()`** — checks routing configuration: only routers have multiple connections.

If either raises a `ValueError`, the workflow never starts.

---

## Step 2 — `_validate_dag()`: structural correctness

```python
def _validate_dag(self):
    if self._has_cycle():
        raise ValueError("Workflow schema contains a cycle")

    reachable_nodes = self._get_reachable_nodes()
    all_nodes = set(nc.node for nc in self.workflow_schema.nodes)
    unreachable_nodes = all_nodes - reachable_nodes
    if unreachable_nodes:
        raise ValueError(
            f"The following nodes are unreachable: {unreachable_nodes}"
        )
```

Two things checked here:

1. **No cycles** — runs `_has_cycle()` (DFS, described below). A cycle would mean the workflow could loop forever.
2. **All nodes reachable** — runs `_get_reachable_nodes()` (BFS from the start node), then checks whether any declared node isn't reachable. An unreachable node is dead code — probably a wiring mistake.

---

## Step 3 — `_has_cycle()`: cycle detection with DFS

```python
def _has_cycle(self) -> bool:
    visited = set()
    rec_stack = set()

    def dfs(node: Type[Node]) -> bool:
        visited.add(node)
        rec_stack.add(node)

        node_config = next(
            (nc for nc in self.workflow_schema.nodes if nc.node == node), None
        )
        if node_config:
            for neighbor in node_config.connections:
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

        rec_stack.remove(node)
        return False

    for node_config in self.workflow_schema.nodes:
        if node_config.node not in visited:
            if dfs(node_config.node):
                return True

    return False
```

DFS cycle detection uses two sets:
- **`visited`** — every node we've ever started exploring.
- **`rec_stack`** — nodes currently on the *active recursion path* (i.e., we're inside their DFS subtree right now).

The logic: when we visit a node, add it to both sets. Then recurse into its neighbours. If we encounter a neighbour that's already in `rec_stack`, that means we've found a path back to an ancestor — a cycle. When we finish a node's DFS (all its descendants explored), we remove it from `rec_stack` (but not `visited`).

**Concrete example — no cycle:**

```
A → B → C → D
```

1. Start DFS at A. `visited={A}`, `rec_stack={A}`.
2. Go to B. `visited={A,B}`, `rec_stack={A,B}`.
3. Go to C. `visited={A,B,C}`, `rec_stack={A,B,C}`.
4. Go to D. `visited={A,B,C,D}`, `rec_stack={A,B,C,D}`.
5. D has no connections. Remove D from `rec_stack`. Return False.
6. Back at C. Remove C. Back at B. Remove B. Back at A. Remove A.
7. No cycle found → return False.

**Concrete example — cycle detected:**

```
A → B → C → B   (C points back to B)
```

1. DFS at A → B → C. `rec_stack={A,B,C}`.
2. C's connection is B. B is already in `rec_stack` → cycle detected → return True.

---

## Step 4 — `_get_reachable_nodes()`: reachability with BFS

```python
def _get_reachable_nodes(self) -> Set[Type[Node]]:
    reachable = set()
    queue = deque([self.workflow_schema.start])

    while queue:
        node = queue.popleft()
        if node not in reachable:
            reachable.add(node)
            node_config = next(
                (nc for nc in self.workflow_schema.nodes if nc.node == node), None
            )
            if node_config:
                queue.extend(node_config.connections)

    return reachable
```

BFS from the `start` node. Each node's `connections` are its edges. Every node that can be reached by following connections from `start` ends up in the `reachable` set.

Then `_validate_dag()` does:

```python
all_nodes = set(nc.node for nc in self.workflow_schema.nodes)
unreachable_nodes = all_nodes - reachable_nodes
```

Set difference: anything declared in `nodes` but not reachable from `start` is flagged.

**Example — unreachable node caught:**

```python
WorkflowSchema(
    start=NodeA,
    nodes=[
        NodeConfig(node=NodeA, connections=[NodeB]),
        NodeConfig(node=NodeB, connections=[]),
        NodeConfig(node=NodeC, connections=[]),  # ← nobody connects to NodeC
    ]
)
```

BFS from `NodeA` reaches `{NodeA, NodeB}`. `all_nodes = {NodeA, NodeB, NodeC}`. Unreachable = `{NodeC}`. Validator raises: `"The following nodes are unreachable: {NodeC}"`.

---

## Step 5 — `_validate_connections()`: router config check

```python
def _validate_connections(self):
    for node_config in self.workflow_schema.nodes:
        if len(node_config.connections) > 1 and not node_config.is_router:
            raise ValueError(
                f"Node {node_config.node.__name__} has multiple connections but is not marked as a router."
            )
```

A simple rule: only nodes marked with `is_router=True` are allowed to have more than one connection. If a regular node has multiple connections, the workflow engine wouldn't know which one to follow — the validator catches this misconfiguration before runtime.

This forces you to be explicit: if you want branching, you must declare a router. Accidental forks are rejected.

---

## When does this run?

`WorkflowValidator` is instantiated and `validate()` is called inside `Workflow.__init__()`:

```python
# app/core/workflow.py
class Workflow(ABC):
    workflow_schema: ClassVar[WorkflowSchema]  # declared on each subclass

    def __init__(self):
        self.validator = WorkflowValidator(self.workflow_schema)
        self.validator.validate()               # raises ValueError on bad graph
        self.nodes = self._initialize_nodes()
        load_dotenv()
```

> **Note:** `Workflow.__init__` takes no parameters. `workflow_schema` is a `ClassVar` declared on each subclass — the validator reads `self.workflow_schema`, not a constructor argument. After validation, `_initialize_nodes()` builds the node registry and `load_dotenv()` ensures `.env` is loaded.

So if you misconfigure your schema — wrong connections, missing node, accidental cycle — you'll know immediately when the workflow class is instantiated, not when a real event arrives.

---

## Mental model: fail early, fail clearly

The validator runs inside `Workflow.__init__()` — meaning it executes every time a `Workflow` subclass is instantiated. In practice, Celery workers instantiate the workflow once per task, so validation runs per-task. A broken graph is detected at task-pickup time, before any node executes, not at module import time. It can't tell you if your *logic* is correct (that's what tests are for), but it guarantees the *structure* is sound: the graph is a DAG, every declared node is reachable, and routing is explicit. Any workflow that passes validation is safe to walk.

---

## Known limitations

**Validation scope:** `WorkflowValidator` does not inspect `NodeConfig.parallel_nodes`. Nodes declared exclusively in `parallel_nodes` lists are not checked for reachability, router configuration, or cycles. The validator guarantees the explicit `connections` graph is a valid DAG; it makes no guarantees about the parallel subgraph.

**Known gap:** the validator never verifies that `WorkflowSchema.start` is present in the `workflow_schema.nodes` list. A schema where `start` is not declared in `nodes` passes validation, but causes a `KeyError` at runtime inside `Workflow.run()` when the engine tries to look up the start node's config.
