---
name: build-node
description: Standardized instructions for creating Python-native workflow Nodes (Node, AgentNode, RouterNode) in the orchestrator pipeline.
---

# Build Node Skill

This skill enforces the architectural standards for creating new Python-native nodes in the orchestration framework.

## 1. Node Types & Selection

Always choose the correct base class from `core.nodes`:

- **`Node`** (`core.nodes.base.Node`): For deterministic, programmatic tasks (e.g., executing shell commands, file I/O, regex parsing, API calls). Fast and cheap.
- **`AgentNode`** (`core.nodes.agent.AgentNode`): For LLM-driven tasks. Automatically integrates with `pydantic-ai` and handles prompt execution, tool use, and structured outputs.
- **`BaseRouter` / `RouterNode`** (`core.nodes.router.BaseRouter`): For branching workflow logic. Analyzes context and returns the next node to execute.
- **`ParallelNode`** (`core.nodes.parallel.ParallelNode`): For concurrent execution. *Rule:* Parallel nodes must write their outputs to uniquely keyed slots in `TaskContext.nodes` to prevent clobbering. Merging must happen in a subsequent sequential node.

## 2. AgentNode Implementation Standard

When building an `AgentNode`, follow these strict rules:

1. **Output Types:** If the node returns structured data, define it as an inner class inheriting from `AgentNode.OutputType`.
2. **Config Generation:** Implement `get_agent_config(self) -> AgentConfig`.
    - Provide `system_prompt` (ALWAYS loaded via `PromptManager`, NEVER hardcoded).
    - Provide `output_type` (or `None`).
    - Provide `model_provider` and `model_name`. Remember the hardware strategy (Sonnet/Opus for coding/reasoning, smaller models for triage/summary).
3. **Processing:**
    - Read input from upstream nodes using `task_context.get_node_output("UpstreamNodeName")`.
    - Call `self.run_agent_recorded(task_context, user_prompt)` to automatically record telemetry (tokens, duration). DO NOT use `self.agent.run_sync()` directly.
    - Save output via `task_context.update_node(node_name=self.node_name, result=result.output)` (See GEMINI.md Rule #9).

```python
from core.nodes.agent import AgentConfig, AgentNode, ModelProvider
from core.task import TaskContext
from services.prompt_loader import PromptManager
from pydantic import Field

class MyAgentNode(AgentNode):
    class OutputType(AgentNode.OutputType):
        analysis: str = Field(description="The analysis result")

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt=PromptManager().get_prompt("my_prompt"),
            output_type=self.OutputType,
            deps_type=None,
            model_provider=ModelProvider.CLAUDE_CODE_SDK,
            model_name="sonnet",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        user_prompt = "..." # build from context
        result = self.run_agent_recorded(task_context, user_prompt)
        task_context.update_node(node_name=self.node_name, result=result.output)
        return task_context
```

## 3. Regular Node Standard

For non-LLM tasks:
1. Implement `process(self, task_context: TaskContext) -> TaskContext`.
2. Ensure it handles exceptions gracefully or lets the framework's `node_context` envelope catch them for a standard `FAILED` state.
3. Update state using `task_context.update_node(self.node_name, output=...)`.

## 4. Router Node Standard

For routing:
1. Subclass `BaseRouter`.
2. Implement `route(self, task_context: TaskContext) -> Node | None`.
3. Extract `task_context.get_node_output(...)` to make decisions, return the instantiated next Node class, or `None` (or fallback).

## 5. Core Architectural Rules

- **No Hardcoded Deployments:** Keep deployment choices (DB logic, endpoints) out of nodes. Use `GenericRepository` via the shared `db_session` factory (Rule #7).
- **Static Model Tiering:** Model choices must be statically baked into `get_agent_config` at design time based on offline evaluation (e.g., local 8B models for simple extractions vs. Claude 3.5 Sonnet for complex reasoning/consolidation). Do not implement runtime/dynamic model routing logic within the node.
- **Rule #9 - Test Contracts:** Tests must mock node outputs exactly as they are produced. If an `AgentNode` does `update_node(node_name="X", result=Y)`, tests must seed `ctx.nodes["X"] = {"result": Y}`, not just `ctx.nodes["X"] = Y`.
- **Stateless Execution:** Nodes must be strictly stateless. Do not store intermediate values on `self` to share between node executions. All state goes in `TaskContext`.
- **Graceful Fault Tolerance:** Use `task_context.nodes.get("NodeName")` with fallback logic if a non-critical upstream node might have failed or skipped. Use `get_node_output()` when an upstream node is strictly required.
