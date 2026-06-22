"""CompanyResearchNode — raw Anthropic SDK tool-use loop for company research."""

import logging

from core.nodes.tool_use import ToolUseNode
from core.task import TaskContext
from schemas.research_agent_schema import ResearchBriefOutput
from services.prompt_loader import PromptManager
from services.search_service import SearchService

log = logging.getLogger(__name__)


class CompanyResearchNode(ToolUseNode):
    """Research a company using a raw Anthropic tool-use loop.

    Exposes two tools to the model:
    - ``web_search``: delegates to ``SearchService`` (Tavily) to gather public info.
    - ``submit_research_brief``: the model calls this once it has enough data;
      the call validates into ``ResearchBriefOutput`` and stores it on
      ``task_context``.

    The loop is bounded by the inherited ``max_iterations`` guard. The system
    prompt is loaded from ``research_agent_brief.j2`` via ``PromptManager`` —
    no prompt text appears in this file. Model is injected via ``TOOL_USE_MODEL``.
    """

    @property
    def tools(self) -> list[dict]:
        return [
            {
                "name": "web_search",
                "description": (
                    "Search the web for information about a company or topic. "
                    "Returns titles, URLs, and content snippets."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query to run",
                        }
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "submit_research_brief",
                "description": (
                    "Submit the completed research brief once you have gathered "
                    "enough information. Call this exactly once."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "company_name": {
                            "type": "string",
                            "description": "Name of the company researched",
                        },
                        "what_they_do": {
                            "type": "string",
                            "description": "Short description of the company's business and market",
                        },
                        "likely_time_sinks": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Processes where the company likely bleeds time (non-empty)"
                            ),
                            "minItems": 1,
                        },
                        "automation_hypothesis": {
                            "type": "string",
                            "description": "One concrete hypothesis for highest-ROI automation",
                        },
                    },
                    "required": [
                        "company_name",
                        "what_they_do",
                        "likely_time_sinks",
                        "automation_hypothesis",
                    ],
                },
            },
        ]

    def _build_initial_messages(self, task_context: TaskContext) -> list[dict]:
        """Seed the loop with a system prompt loaded from .j2 and the company name."""
        event = task_context.event
        if isinstance(event, dict):
            company_name = event.get("company_name", "")
        else:
            company_name = getattr(event, "company_name", "")
        system_prompt = PromptManager.get_prompt(
            "research_agent_brief", company_name=company_name
        )
        return [
            {
                "role": "user",
                "content": (
                    f"Please research the following company and produce a brief: "
                    f"{company_name}\n\nSystem context:\n{system_prompt}"
                ),
            }
        ]

    def handle_tool_call(
        self,
        tool_name: str,
        tool_input: dict,
        task_context: TaskContext,
    ) -> str:
        """Dispatch tool calls to the appropriate backend."""
        if tool_name == "web_search":
            return self._handle_web_search(tool_input)
        if tool_name == "submit_research_brief":
            return self._handle_submit_brief(tool_input, task_context)
        log.warning("CompanyResearchNode received unknown tool call: %s", tool_name)
        return f"Unknown tool: {tool_name}"

    def _handle_web_search(self, tool_input: dict) -> str:
        """Run a Tavily search and format results as a compact string."""
        query = tool_input.get("query", "")
        results = SearchService().search(query)
        if not results:
            return "No results found."
        lines = []
        for r in results:
            lines.append(f"Title: {r.title}")
            lines.append(f"URL: {r.url}")
            lines.append(f"Snippet: {r.content}")
            lines.append("")
        return "\n".join(lines).strip()

    def _handle_submit_brief(
        self, tool_input: dict, task_context: TaskContext
    ) -> str:
        """Validate the tool input into ResearchBriefOutput and store it."""
        brief = ResearchBriefOutput(**tool_input)
        # Store under the 'brief' key so the parent process's text-extraction
        # write (which uses 'output') does not overwrite the structured result.
        task_context.update_node(
            self.node_name, brief=brief.model_dump()
        )
        log.info(
            "CompanyResearchNode stored brief for company: %s", brief.company_name
        )
        return (
            f"Brief submitted successfully for {brief.company_name}. "
            f"Found {len(brief.likely_time_sinks)} time sinks."
        )
