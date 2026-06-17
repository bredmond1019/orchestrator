---
type: Reference
title: ParallelNode — How It Works
description: How ParallelNode works — fan-out execution of child nodes.
---

# ParallelNode — How It Works

`app/core/nodes/parallel.py`

---

## The big picture

`ParallelNode` lets you run multiple nodes at the same time, in parallel threads, instead of sequentially. It's used when several independent analysis steps can happen concurrently — each one reads from the shared `TaskContext` and writes its result back to it.

In the Customer Care workflow, `AnalyzeTicketNode` runs three analysis nodes simultaneously (spam filter, intent detection, ticket validation) rather than waiting for each one to finish before starting the next.

---

## Step 1 — The class definition

```python
# app/core/nodes/parallel.py
class ParallelNode(Node, ABC):
    def execute_nodes_in_parallel(self, task_context: TaskContext):
        ...

    @abstractmethod
    def process(self, task_context: TaskContext) -> TaskContext:
        pass
```

`ParallelNode` inherits from `Node`, so it still has a `process()` method you must implement. The key addition is the `execute_nodes_in_parallel()` helper method — you call this inside your `process()` implementation to trigger the concurrent execution.

---

## Step 2 — `execute_nodes_in_parallel`: how it runs nodes concurrently

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

Walk through this line by line:

**Line 1 — look up the config for this node:**
```python
node_config: NodeConfig = task_context.metadata["nodes"][self.__class__]
```
The `TaskContext` carries a `metadata["nodes"]` dict that maps each node class to its `NodeConfig`. The `NodeConfig` for a `ParallelNode` has a `parallel_nodes` list — that's the list of node classes to run in parallel. This is how the parallel node knows *which* child nodes to spawn without them being hardcoded in the class itself.

Lifecycle note: task_context.metadata['nodes'] is injected by Workflow.run() at the start of each execution and removed via metadata.pop('nodes') before run() returns (workflow.py line 131). ParallelNode's dependency on this key is therefore only valid during active workflow execution — not on a TaskContext retrieved from the database.

**Lines 2–6 — submit each node as a thread:**
```python
with ThreadPoolExecutor() as executor:
    for node in node_config.parallel_nodes:
        future = executor.submit(node().process, task_context)
        future_list.append(future)
```
For each node class in `parallel_nodes`, it:
1. Instantiates the node (`node()`).
2. Submits `node_instance.process(task_context)` to the thread pool.
3. `executor.submit(...)` returns a `Future` immediately — it does not wait for the node to finish.

All nodes are submitted before any of them complete, so they run concurrently.

**Line 7 — wait for all to finish:**
```python
results = [future.result() for future in future_list]
```
`future.result()` blocks until that specific future is done. Iterating through all futures in order means this line won't return until every parallel node has completed.

Exception propagation: if any parallel node's process() raises an exception, future.result() re-raises it in the calling thread. Since the list comprehension iterates futures in submission order, an exception in an earlier future aborts collection before later futures' results are retrieved. No already-submitted futures are cancelled. The exception propagates up through AnalyzeTicketNode.process() and is caught and logged by Workflow's node_context context manager before being re-raised to Celery.

---

## Step 3 — A concrete example: `AnalyzeTicketNode`

```python
# app/workflows/customer_care_workflow_nodes/analyze_ticket_node.py
class AnalyzeTicketNode(ParallelNode):
    def process(self, task_context: TaskContext) -> TaskContext:
        self.execute_nodes_in_parallel(task_context)
        return task_context
```

That's the entire class — four lines. The subclass just calls the helper and returns the context. The `parallel_nodes` list (which nodes actually run) is declared in the `WorkflowSchema`, not here:

```python
# in customer_care_workflow.py (WorkflowSchema declaration)
NodeConfig(
    node=AnalyzeTicketNode,
    connections=[TicketRouterNode],
    description="",
    parallel_nodes=[DetermineTicketIntentNode, FilterSpamNode, ValidateTicketNode],
)
```

This separation is intentional: the node class contains the *mechanism* (run things in parallel), and the schema contains the *configuration* (which things to run in parallel).

---

## Step 4 — How results get back into `TaskContext`

Each parallel node is a regular `Node` — it calls `task_context.update_node(self.node_name, ...)` inside its own `process()` method before returning. Since all parallel nodes share the same `task_context` object, their results accumulate in `task_context.nodes` as they complete:

```
task_context.nodes["FilterSpamNode"]          → spam result
task_context.nodes["DetermineTicketIntentNode"] → intent result
task_context.nodes["ValidateTicketNode"]       → validation result
```

After `execute_nodes_in_parallel()` returns, any downstream node can read all three of those results by key.

---

## The known gap: thread safety

Each parallel node *writes* to `task_context.nodes[self.node_name]`. Because each node writes to a **different key**, they don't actually conflict — Python's GIL and dict operations make this safe in practice for this pattern.

However, the `results` list returned by `execute_nodes_in_parallel()` is currently discarded by `AnalyzeTicketNode.process()`. The line:

```python
self.execute_nodes_in_parallel(task_context)   # returns a list — ignored
return task_context
```

This works because the side effect (writing to `task_context`) is how data is communicated. The return value of each parallel node's `process()` is redundant. This is noted as a design smell in the architecture docs — the intended fix is to have each parallel node write to a uniquely keyed slot (which they already do) and then explicitly merge after, rather than relying on the shared-object side effect.

---

## Mental model

Think of `ParallelNode` as a fan-out gate in the workflow:

```
                  ┌─ FilterSpamNode ──────────────┐
                  │                               │
AnalyzeTicketNode ├─ DetermineTicketIntentNode ───┼─► TicketRouterNode
                  │                               │
                  └─ ValidateTicketNode ───────────┘
```

All three branches run at the same time. The gate doesn't close (i.e., `execute_nodes_in_parallel` doesn't return) until all three are done. Then the workflow continues to `TicketRouterNode`, which can read all three results from `task_context.nodes`.
