"""SDLCFlowWorkflow — sequential, shared-worktree SDLC pipeline (OR.Z).

Wires every node built in Tasks 1-8 into one ``WorkflowSchema``: setup the
isolated worktree, load (or bootstrap) the structured task state, then loop
over pending tasks (implement -> test -> triage -> [retry | review] ->
[re-implement | update status]) until none remain, then patch docs, wrap up,
and open a PR.

Graph::

    SetupWorktreeNode
        -> LoadTaskStateNode
            -> TaskQueueRouterNode (router) ────────────────────┐
                    │ (pending task found)          (no tasks left)
                    v                                            v
                ImplementTaskNode <────────────┐             PatchDocsNode
                    │                            │                │
                    v                            │ retry           v
                TestTaskNode                     │             WrapUpNode
                    │                            │                │
                    v                            │                v
                TriageTaskNode                    │            PullRequestNode
                    │                            │
                    v                            │
                TriageRouterNode (router) ───────┤ (RETRYABLE)
                    │ (PASS)         (MAJOR_BAIL)│
                    v                    v        │
                ConsolidatedReviewNode  WrapUpNode │
                    │                              │
                    v                              │
                ReviewRouterNode (router) ─────────┘ (FAIL/PARTIAL, minor)
                    │ (PASS)      (structural FAIL)
                    v                  v
                UpdateTaskStatusNode  WrapUpNode
                    │
                    v
                SaveStateNode
                    │
                    v
                TaskQueueRouterNode (loop back for the next task)

Cyclic loop-backs (``TriageRouterNode``/``ReviewRouterNode`` -> retry via
``ImplementTaskNode``, and ``SaveStateNode`` -> ``TaskQueueRouterNode`` for
the next task) are **not** declared as ``NodeConfig.connections`` edges —
they are bounded, runtime-only routing decisions made inside each router's
``determine_next_node``/``_TaskQueueRouter`` implementation (see
``Workflow._handle_router``, which calls ``router.route()`` directly rather
than consulting the declared connections). ``WorkflowValidator._has_cycle``
skips traversing a router node's own declared connections for exactly this
reason (see ``core/validate.py``), so the declared graph below is acyclic
while the actual runtime execution graph loops.

``ImplementTaskNode`` is still listed as a declared connection of
``TaskQueueRouterNode`` (and ``WrapUpNode`` is a declared connection of both
``TriageRouterNode`` and ``ReviewRouterNode``) purely so
``WorkflowValidator``'s reachability (BFS) check finds every node — the
retry-only back-edges into ``ImplementTaskNode`` from ``TriageRouterNode`` /
``ReviewRouterNode`` are deliberately omitted from the declared connections
(``ImplementTaskNode`` is already reachable via ``TaskQueueRouterNode``),
which is what keeps the declared graph acyclic.
"""

from core.schema import NodeConfig, WorkflowSchema
from core.workflow import Workflow
from schemas.sdlc_schema import SDLCFlowEventSchema

from workflows.sdlc_flow_workflow_nodes.consolidated_review_node import (
    ConsolidatedReviewNode,
)
from workflows.sdlc_flow_workflow_nodes.implement_task_node import ImplementTaskNode
from workflows.sdlc_flow_workflow_nodes.load_task_state_node import LoadTaskStateNode
from workflows.sdlc_flow_workflow_nodes.patch_docs_node import PatchDocsNode
from workflows.sdlc_flow_workflow_nodes.pull_request_node import PullRequestNode
from workflows.sdlc_flow_workflow_nodes.review_router_node import ReviewRouterNode
from workflows.sdlc_flow_workflow_nodes.save_state_node import SaveStateNode
from workflows.sdlc_flow_workflow_nodes.setup_worktree_node import SetupWorktreeNode
from workflows.sdlc_flow_workflow_nodes.task_queue_router_node import (
    TaskQueueRouterNode,
)
from workflows.sdlc_flow_workflow_nodes.test_task_node import TestTaskNode
from workflows.sdlc_flow_workflow_nodes.triage_task_node import (
    TriageRouterNode,
    TriageTaskNode,
)
from workflows.sdlc_flow_workflow_nodes.update_task_status_node import (
    UpdateTaskStatusNode,
)
from workflows.sdlc_flow_workflow_nodes.wrap_up_node import WrapUpNode


class SDLCFlowWorkflow(Workflow):
    """Sequential SDLC pipeline: setup -> load state -> task loop -> docs -> PR."""

    workflow_schema = WorkflowSchema(
        description=(
            "SDLC pipeline: setup -> load state -> task loop "
            "(implement -> test -> triage -> review) -> patch docs -> wrap up -> PR."
        ),
        event_schema=SDLCFlowEventSchema,
        start=SetupWorktreeNode,
        nodes=[
            NodeConfig(
                node=SetupWorktreeNode,
                connections=[LoadTaskStateNode],
                description="Create or reattach to the isolated git worktree.",
            ),
            NodeConfig(
                node=LoadTaskStateNode,
                connections=[TaskQueueRouterNode],
                description="Load or bootstrap the durable SDLCState for this run.",
            ),
            NodeConfig(
                node=TaskQueueRouterNode,
                connections=[ImplementTaskNode, PatchDocsNode],
                description=(
                    "Dispatch the next PENDING task (-> ImplementTaskNode) or, once "
                    "none remain, end the loop (-> PatchDocsNode)."
                ),
                is_router=True,
            ),
            NodeConfig(
                node=ImplementTaskNode,
                connections=[TestTaskNode],
                description="Drive Claude Code to implement the current task.",
            ),
            NodeConfig(
                node=TestTaskNode,
                connections=[TriageTaskNode],
                description="Run the planning/harness.json validation suite.",
            ),
            NodeConfig(
                node=TriageTaskNode,
                connections=[TriageRouterNode],
                description="Classify a failing TestTaskNode result (or PASS through).",
            ),
            NodeConfig(
                node=TriageRouterNode,
                connections=[ConsolidatedReviewNode, WrapUpNode],
                description=(
                    "Routes PASS -> ConsolidatedReviewNode, MAJOR_BAIL -> WrapUpNode. "
                    "RETRYABLE also routes back to ImplementTaskNode at runtime; that "
                    "back-edge is intentionally not declared here (see module docstring)."
                ),
                is_router=True,
            ),
            NodeConfig(
                node=ConsolidatedReviewNode,
                connections=[ReviewRouterNode],
                description="Review the full task diff against acceptance criteria.",
            ),
            NodeConfig(
                node=ReviewRouterNode,
                connections=[UpdateTaskStatusNode, WrapUpNode],
                description=(
                    "Routes PASS -> UpdateTaskStatusNode, structural FAIL -> WrapUpNode. "
                    "Minor FAIL/PARTIAL also routes back to ImplementTaskNode at runtime; "
                    "that back-edge is intentionally not declared here (see module docstring)."
                ),
                is_router=True,
            ),
            NodeConfig(
                node=UpdateTaskStatusNode,
                connections=[SaveStateNode],
                description="Mutate the current task's status + telemetry in SDLCState.",
            ),
            NodeConfig(
                node=SaveStateNode,
                connections=[TaskQueueRouterNode],
                description=(
                    "Persist SDLCState to disk and commit it, then loop back to the "
                    "task queue router for the next pending task."
                ),
            ),
            NodeConfig(
                node=PatchDocsNode,
                connections=[WrapUpNode],
                description="Patch documentation referencing the run's modified files.",
            ),
            NodeConfig(
                node=WrapUpNode,
                connections=[PullRequestNode],
                description="Summarize the run's telemetry into a log entry and report.",
            ),
            NodeConfig(
                node=PullRequestNode,
                connections=[],
                description="Push the branch and open a PR for human review (no auto-merge).",
            ),
        ],
    )
