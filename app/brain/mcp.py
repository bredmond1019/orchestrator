"""app/brain/mcp.py — the MCP server adapter over the `app.brain` read core.

This is the THIRD thin adapter over the same `app/brain` read core that
`app/brain/cli.py` (`syn recall`/`syn walk`/`syn pulse`, OR.N1) and
`app/api/read.py` (the HTTP `/recall`, `/walk`, `/pulse` routes, OR.Q2/
OR.3.B) already front. It exposes exactly three MCP tools —
``brain_recall``, ``brain_walk``, ``brain_pulse`` — as thin dispatches onto
``app.brain.retrieval.recall``, ``app.brain.graph.walk`` and
``app.brain.pulse.pulse``.

Adapter discipline (mirrors `app/api/read.py`'s docstring exactly): this
module opens no session of its own beyond the injected/opened one, issues
no direct SQL, and implements no second retrieval or traversal logic —
ranking, fusion and traversal output stay byte-identical to what
`syn recall` / `syn walk` / `syn pulse` return today. Every call is tagged
`surface="mcp"` for the OR.K1 query log.

The tool schema and dispatch logic (`tool_definitions()`, `call_tool()`)
are pure, transport-free functions so they are testable without a live
stdio transport. The `mcp.server.Server` wiring and `stdio_server()` loop
(task 3) are a thin shell over them — no schema, no dispatch, and no error
classification live outside these two functions.
"""

import json
from typing import Any

from mcp import types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from sqlalchemy.exc import InterfaceError, OperationalError

from brain import graph, retrieval
from brain import pulse as pulse_core

SERVER_NAME = "synapse-brain"

# pylint: disable=duplicate-code
# Identical to app/api/read.py's dependency-error tuple + _classify_dependency_failure
# below, by design (see the function's docstring): each adapter classifies failures
# on its own so the MCP adapter has no import dependency on the HTTP adapter module.
_DEPENDENCY_ERROR_TYPES = (
    OperationalError,
    InterfaceError,
    ConnectionError,
    TimeoutError,
    OSError,
)


def _classify_dependency_failure(exc: BaseException) -> bool:
    """Return True if `exc` (or a chained cause/context) is a dependency
    failure — pgvector/Postgres or the embedding backend unreachable —
    rather than an unexpected internal error.

    Walks `__cause__`/`__context__` so a dependency error wrapped in a
    generic exception (`raise RuntimeError(...) from ConnectionError(...)`)
    is still recognised. Identical logic to `app/api/read.py`'s
    `_classify_dependency_failure`, duplicated rather than imported so this
    adapter has no dependency on the HTTP adapter module. The duplication is
    intentional (adapter independence); the `duplicate-code` disable above
    documents that this block is knowingly identical to its HTTP-adapter twin.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, _DEPENDENCY_ERROR_TYPES):
            return True
        current = current.__cause__ or current.__context__
    return False
# pylint: enable=duplicate-code


def _error_content(key: str, message: str) -> list[types.TextContent]:
    """Build the single-item TextContent error envelope `{"error", "message"}`."""
    return [
        types.TextContent(
            type="text",
            text=json.dumps({"error": key, "message": message}),
        )
    ]


def _classified_error(exc: Exception, *, generic_error: str) -> list[types.TextContent]:
    """Return the typed error envelope for a read-core failure.

    `brain_backend_unavailable` for a classified dependency failure, else
    `generic_error` (the tool-specific `*_failed` key).
    """
    if _classify_dependency_failure(exc):
        return _error_content("brain_backend_unavailable", str(exc))
    return _error_content(generic_error, str(exc))


def tool_definitions() -> list[types.Tool]:
    """Return the three MCP tools this server exposes.

    Exactly `brain_recall`, `brain_walk`, `brain_pulse` — no more, no
    fewer. `tests/brain/test_mcp.py` pins this set and each tool's full
    `inputSchema` literally: bastion's vendored Rust MCP client is written
    against this contract, so an added, removed or renamed argument must
    fail the suite rather than drift silently.

    Returns:
        A list of three `mcp.types.Tool` objects.
    """
    return [
        types.Tool(
            name="brain_recall",
            description="Search the Brain corpus. Fronts app.brain.retrieval.recall.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {
                        "type": "integer",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "hybrid": {"type": "boolean", "default": False},
                    "workspace": {"type": "string"},
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="brain_walk",
            description="Traverse brain_edges from a document. Fronts app.brain.graph.walk.",
            inputSchema={
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                    "depth": {
                        "type": "integer",
                        "default": 1,
                        "minimum": 1,
                        "maximum": 5,
                    },
                },
                "required": ["doc_id"],
            },
        ),
        types.Tool(
            name="brain_pulse",
            description="Report Brain corpus health. Fronts app.brain.pulse.pulse.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
    ]


def _call_brain_recall(arguments: dict[str, Any], *, session) -> list[types.TextContent]:
    """Dispatch `brain_recall` onto `retrieval.recall`, tagged `surface="mcp"`."""
    try:
        results = retrieval.recall(
            arguments["query"],
            limit=arguments.get("limit", 5),
            hybrid=arguments.get("hybrid", False),
            workspace=arguments.get("workspace"),
            session=session,
            surface="mcp",
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Intentionally broad: any failure from the read core (dependency
        # outage or an unexpected bug) must be classified below, never left
        # to raise out of call_tool and into the transport.
        return _classified_error(exc, generic_error="recall_failed")
    return [types.TextContent(type="text", text=json.dumps(results))]


def _call_brain_walk(arguments: dict[str, Any], *, session) -> list[types.TextContent]:
    """Dispatch `brain_walk` onto `graph.walk`."""
    try:
        result = graph.walk(
            arguments["doc_id"],
            depth=arguments.get("depth", 1),
            session=session,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Intentionally broad: see _call_brain_recall's identical justification.
        return _classified_error(exc, generic_error="walk_failed")
    return [types.TextContent(type="text", text=json.dumps(result))]


def _call_brain_pulse(_arguments: dict[str, Any], *, session) -> list[types.TextContent]:
    """Dispatch `brain_pulse` onto `pulse_core.pulse`."""
    try:
        report = pulse_core.pulse(session=session)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Intentionally broad: see _call_brain_recall's identical justification.
        return _classified_error(exc, generic_error="pulse_failed")
    return [types.TextContent(type="text", text=json.dumps(report.to_dict()))]


_DISPATCH = {
    "brain_recall": _call_brain_recall,
    "brain_walk": _call_brain_walk,
    "brain_pulse": _call_brain_pulse,
}


def call_tool(
    name: str, arguments: dict[str, Any] | None, *, session=None
) -> list[types.TextContent]:
    """Dispatch one MCP tool call onto the read core and return its result.

    Missing optional arguments fall back to the defaults declared in
    `tool_definitions()`; supplied arguments are passed through verbatim —
    this function does not re-implement clamping or validation, so the read
    core sees exactly what the client sent.

    Args:
        name: The tool name (`brain_recall` / `brain_walk` / `brain_pulse`).
        arguments: The tool's arguments as sent by the client, or `None`.
        session: An open SQLAlchemy session (injected; each dispatched core
            opens its own via `database.session.db_session` when omitted).

    Returns:
        A single-item list of `types.TextContent` carrying either the
        JSON-serialized result or a JSON error envelope
        `{"error": <stable key>, "message": <str>}`. Never raises: a
        dependency-unreachable failure from any of the three cores maps to
        `brain_backend_unavailable`; any other failure maps to the tool's
        own `*_failed` key; an unrecognised tool name maps to
        `unknown_tool`.
    """
    handler = _DISPATCH.get(name)
    if handler is None:
        return _error_content("unknown_tool", f"unknown tool: {name!r}")

    return handler(arguments or {}, session=session)


def build_server() -> Server:
    """Build the `mcp.server.Server` wired to `tool_definitions()`/`call_tool()`.

    A thin shell only: it registers the two handlers below and contains no
    schema, no dispatch logic and no error classification of its own — all
    three live in `tool_definitions()` and `call_tool()` above, which is
    why those stay testable without a running transport. Mirrors
    `app/brain/cli.py`'s `_run_recall`/`_run_walk`/`_run_pulse` session
    convention: no session is opened or threaded through here, so each
    dispatched core opens (and closes) its own per call via its `session=
    None` default — the same pattern `syn recall`/`syn walk`/`syn pulse`
    already use, not a third session convention.
    """
    server = Server(SERVER_NAME)

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        """Return the three MCP tools this server exposes."""
        return tool_definitions()

    @server.call_tool()
    async def _call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[types.TextContent]:
        """Dispatch one MCP tool call onto the read core; never raises."""
        return call_tool(name, arguments)

    return server


async def serve() -> None:
    """Run the Brain read path as an MCP server over stdio.

    Blocks until stdin closes. Backs the `syn mcp` subcommand
    (`app/brain/cli.py`).
    """
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=SERVER_NAME,
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
