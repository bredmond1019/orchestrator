---
type: Reference
title: RouterNode & BaseRouter — How They Work
description: How RouterNode and BaseRouter work — conditional branching in a workflow graph.
doc_id: router-node
layer: [engine]
project: python-orchestration
status: active
keywords: [RouterNode, BaseRouter, conditional branching, workflow graph, routing]
related: [app-architecture-overview, api-reference]
---

# RouterNode & BaseRouter — How They Work

`app/core/nodes/router.py`

---

## The big picture

Routing is how a workflow branches. After several analysis nodes have run and written their results into `TaskContext`, a router reads those results and decides which node to execute next — send to `EscalateNode`, or `GenerateResponseNode`, or `CloseTicketNode`?

The routing system has two parts:
- **`BaseRouter`** — the node that sits in the workflow graph and runs the routing logic.
- **`RouterNode`** — individual routing rules, each one answering a yes/no question: "should we go *here*?"

You compose routing logic by writing one `RouterNode` subclass per decision, then assembling them inside a `BaseRouter` subclass.

---

## Step 1 — `RouterNode`: one rule, one answer

```python
# app/core/nodes/router.py
class RouterNode(ABC):
    @abstractmethod
    def determine_next_node(self, task_context: TaskContext) -> Optional[Node]:
        pass

    @property
    def node_name(self):
        return self.__class__.__name__
```

`RouterNode` is an abstract class with a single method: `determine_next_node()`.

- If this rule's condition is met → return the next `Node` instance to run.
- If this rule's condition is **not** met → return `None` (pass to the next rule).

Here are three concrete `RouterNode` implementations from the Customer Care workflow:

```python
# app/workflows/customer_care_workflow_nodes/ticket_router_node.py

class CloseTicketRouter(RouterNode):
    def determine_next_node(self, task_context: TaskContext) -> Optional[Node]:
        output: FilterSpamNode.OutputType = task_context.nodes["FilterSpamNode"]["result"].output
        if not output.is_human and output.confidence > 0.8:
            return CloseTicketNode()    # ← condition met: route here
        return None                     # ← condition not met: fall through

class EscalationRouter(RouterNode):
    def determine_next_node(self, task_context: TaskContext) -> Optional[Node]:
        analysis = task_context.nodes["DetermineTicketIntentNode"]["result"].output
        if analysis.intent.escalate or analysis.escalate:
            return EscalateTicketNode()
        return None

class InvoiceRouter(RouterNode):
    def determine_next_node(self, task_context: TaskContext) -> Optional[Node]:
        analysis = task_context.nodes["DetermineTicketIntentNode"]["result"].output
        if analysis.intent == CustomerIntent.BILLING_INVOICE:
            return ProcessInvoiceNode()
        return None
```

Each rule reads whatever it needs from `task_context.nodes` (results written by earlier nodes), checks its condition, and returns either a destination node or `None`.

---

## Step 2 — `BaseRouter`: runs the rules in order

```python
class BaseRouter(Node):
    def process(self, task_context: TaskContext) -> TaskContext:
        next_node = self.route(task_context)
        task_context.nodes[self.node_name] = {"next_node": next_node.node_name if next_node else None}
        return task_context

    def route(self, task_context: TaskContext) -> Node:
        for route_node in self.routes:
            next_node = route_node.determine_next_node(task_context)
            if next_node:
                return next_node
        return self.fallback if self.fallback else None
```

`BaseRouter` is itself a `Node` — it has a `process()` method and fits into the workflow graph like any other node.

When `process()` is called:

1. It calls `self.route(task_context)`.
2. `route()` loops through `self.routes` — a list of `RouterNode` instances — and calls `determine_next_node()` on each in order.
3. The **first** rule that returns a non-`None` node wins. The loop stops immediately.
4. If no rule matches, `self.fallback` is used (a default destination).
5. The winning node's name is recorded in `task_context.nodes` for traceability.
6. process() returns TaskContext (return task_context — see the code block above). The winning node instance is NOT surfaced to the workflow engine from this call. After process() returns, Workflow._get_next_node_class() detects is_router=True, creates a fresh router instance, and calls route() a second time inside _handle_router() — that second call is what produces the node class the engine jumps to. (See Step 4 for the full double-invocation explanation.)

---

## Step 3 — `TicketRouterNode`: a complete `BaseRouter` subclass

```python
class TicketRouterNode(BaseRouter):
    def __init__(self):
        self.routes = [
            CloseTicketRouter(),
            EscalationRouter(),
            InvoiceRouter(),
        ]
        self.fallback = GenerateResponseNode()
```

That's it — just `__init__`. The routing logic is entirely in the `RouterNode` instances in `self.routes`. The `BaseRouter` parent class handles calling them in order.

**Important:** BaseRouter declares no `routes` or `fallback` attributes at class level and defines no `__init__` method. There is no enforcement of these assignments — a subclass that omits either raises `AttributeError` at runtime on the first call to `process()` or `route()`, not at instantiation time. Always ensure your BaseRouter subclass assigns both `self.routes = [...]` and `self.fallback = SomeNode()` (or `None`) in its own `__init__`.

The **order matters**: `CloseTicketRouter` is checked first. If the ticket is spam with high confidence, it routes to `CloseTicketNode` without even checking escalation or invoice. Only if spam check fails does it check escalation, and so on.

The **fallback** (`GenerateResponseNode`) handles everything that doesn't match any rule — in this case, a normal human ticket that doesn't need escalation or invoice processing.

---

## Step 4 — How the workflow engine uses the router's output

`BaseRouter.process()` stores the winning node's *name* in `task_context` for traceability:

```python
task_context.nodes[self.node_name] = {"next_node": next_node.node_name if next_node else None}
```

This entry is an **audit trail only** — it is NOT how the engine decides where to go next.
When `route()` returns `None` (terminal router, e.g. digest-only path), `None` is recorded rather
than crashing on `None.node_name`. The engine's `_handle_router()` independently handles the
`None` return to stop the walk.

After the router's `process()` returns, the engine calls `_get_next_node_class()`, which detects `is_router=True`, then independently instantiates a second fresh router and calls `route()` again directly:

```python
# in workflow.py — _get_next_node_class()
if node_config.is_router:
    router: BaseRouter = self.nodes[current_node_class].node()   # new instance
    return self._handle_router(router, task_context)             # calls route() again

# _handle_router:
next_node = router.route(task_context)
return next_node.__class__ if next_node else None
```

So the routing logic runs **twice** per router step: once inside `process()` (to write the traceability entry) and once inside `_get_next_node_class()` (to return the actual next class to the walk loop). For stateless routers — which they always should be — this is harmless, but it's a redundancy worth knowing about.

The `task_context.nodes[router_name]["next_node"]` string is useful for inspecting the stored task context in the database after a run, but the engine never reads it to make a routing decision.

---

## Mental model: first-match routing

```
                     ┌─ CloseTicketRouter: is spam & confidence > 0.8? ──► CloseTicketNode
                     │         ↓ no
TicketRouterNode ───►├─ EscalationRouter: needs escalation? ─────────────► EscalateTicketNode
                     │         ↓ no
                     ├─ InvoiceRouter: billing question? ────────────────► ProcessInvoiceNode
                     │         ↓ no
                     └─ fallback ────────────────────────────────────────► GenerateResponseNode
```

Each rule is independent. Each one looks at whatever it needs in `task_context`. The first match wins; the rest are skipped. If nothing matches, the fallback handles it.

---

## Known limitation: hard-coded route key strings

Inside each `RouterNode`, the route keys are plain strings:

```python
task_context.nodes["FilterSpamNode"]["result"].output
```

Two distinct failure modes exist: (1) if a node's class name changes, the task_context.nodes lookup raises a loud KeyError at runtime; (2) if routing logic contains a silent mistake (e.g., accessing the wrong key without raising), the router proceeds with unexpected data and routes to the wrong destination with no error. CLAUDE.md documents this as a 'silent miss' concern — the second failure mode is the dangerous one.
