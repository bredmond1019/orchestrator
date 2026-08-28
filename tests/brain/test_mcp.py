"""Tests for `app/brain/mcp.py` (OR.R task 2).

This file is the contract pin for `docs/mcp-contract.md` (task 4): the
tool-name set and each tool's full `inputSchema` are asserted as literals
here, and bastion's vendored Rust MCP client is written against exactly
this contract. A future editor of either file should find the other.

Reuses the mock-the-core-at-its-import-site pattern from
``tests/api/test_read.py`` — here the import site is ``app.brain.mcp``
(``brain.mcp`` at runtime, since only ``app/`` is on ``sys.path``).
"""

import asyncio
import json
import pathlib
from unittest.mock import patch

import anyio
import pytest
from brain import mcp
from brain.cli import _build_parser
from mcp import types as mcp_types
from mcp.client.session import ClientSession
from mcp.shared.memory import (
    create_client_server_memory_streams,
    create_connected_server_and_client_session,
)
from sqlalchemy.exc import OperationalError

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Schema pin
# ---------------------------------------------------------------------------

EXPECTED_TOOL_NAMES = frozenset({"brain_recall", "brain_walk", "brain_pulse"})

EXPECTED_SCHEMAS = {
    "brain_recall": {
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
    "brain_walk": {
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
    "brain_pulse": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def test_tool_definitions_returns_exactly_three_tools():
    """The tool-name set is exactly the three declared tools — no more, no fewer.

    A subset/issubset assertion would not catch an ADDED tool, which is
    exactly the drift a cross-repo client breaks on, so this compares the
    full frozenset with `==`.
    """
    tools = mcp.tool_definitions()
    names = frozenset(tool.name for tool in tools)
    assert names == EXPECTED_TOOL_NAMES
    assert len(tools) == 3


@pytest.mark.parametrize("tool_name", sorted(EXPECTED_SCHEMAS))
def test_tool_input_schema_matches_literal(tool_name):
    """Each tool's full inputSchema is pinned field-for-field against a literal."""
    tools = {tool.name: tool for tool in mcp.tool_definitions()}
    assert tools[tool_name].inputSchema == EXPECTED_SCHEMAS[tool_name]


# ---------------------------------------------------------------------------
# Dispatch tests
# ---------------------------------------------------------------------------


class _FakePulseReport:
    """Stand-in for `PulseReport` whose `to_dict()` matches the real shape."""

    def to_dict(self) -> dict:
        return {"healthy": True, "errors": []}


def test_call_brain_recall_passes_arguments_verbatim():
    """brain_recall passes query/limit/hybrid/workspace through verbatim plus surface="mcp"."""
    with patch("brain.mcp.retrieval") as mock_retrieval:
        mock_retrieval.recall.return_value = [{"doc_id": "D20"}]
        session = object()
        result = mcp.call_tool(
            "brain_recall",
            {"query": "what is D20", "limit": 3, "hybrid": True, "workspace": "orchestrator"},
            session=session,
        )

    mock_retrieval.recall.assert_called_once_with(
        "what is D20",
        limit=3,
        hybrid=True,
        workspace="orchestrator",
        session=session,
        surface="mcp",
    )
    assert len(result) == 1
    assert json.loads(result[0].text) == [{"doc_id": "D20"}]


def test_call_brain_recall_uses_declared_defaults_when_only_query_supplied():
    """With only `query` supplied, limit/hybrid/workspace fall back to schema defaults."""
    with patch("brain.mcp.retrieval") as mock_retrieval:
        mock_retrieval.recall.return_value = []
        session = object()
        mcp.call_tool("brain_recall", {"query": "hello"}, session=session)

    mock_retrieval.recall.assert_called_once_with(
        "hello",
        limit=5,
        hybrid=False,
        workspace=None,
        session=session,
        surface="mcp",
    )


def test_call_brain_recall_preserves_result_order():
    """The adapter must not re-rank — score polarity is higher-is-better on every path."""
    ordered = [{"doc_id": "A", "score": 0.9}, {"doc_id": "B", "score": 0.1}]
    with patch("brain.mcp.retrieval") as mock_retrieval:
        mock_retrieval.recall.return_value = ordered
        result = mcp.call_tool("brain_recall", {"query": "q"}, session=object())

    assert json.loads(result[0].text) == ordered


def test_call_brain_walk_passes_arguments_verbatim():
    """brain_walk passes doc_id and depth through verbatim."""
    with patch("brain.mcp.graph") as mock_graph:
        mock_graph.walk.return_value = {"root": "D20", "depth": 2, "levels": [], "nodes": {}}
        session = object()
        result = mcp.call_tool("brain_walk", {"doc_id": "D20", "depth": 2}, session=session)

    mock_graph.walk.assert_called_once_with("D20", depth=2, session=session)
    assert json.loads(result[0].text)["root"] == "D20"


def test_call_brain_walk_uses_default_depth_when_absent():
    """With only `doc_id` supplied, depth falls back to the schema default of 1."""
    with patch("brain.mcp.graph") as mock_graph:
        mock_graph.walk.return_value = {"root": "D20", "depth": 1, "levels": [], "nodes": {}}
        session = object()
        mcp.call_tool("brain_walk", {"doc_id": "D20"}, session=session)

    mock_graph.walk.assert_called_once_with("D20", depth=1, session=session)


def test_call_brain_pulse_calls_pulse_core_with_no_extra_arguments():
    """brain_pulse calls the pulse core with no arguments beyond the session."""
    with patch("brain.mcp.pulse_core") as mock_pulse_core:
        mock_pulse_core.pulse.return_value = _FakePulseReport()
        session = object()
        result = mcp.call_tool("brain_pulse", {}, session=session)

    mock_pulse_core.pulse.assert_called_once_with(session=session)
    assert json.loads(result[0].text) == {"healthy": True, "errors": []}


def test_call_brain_pulse_ignores_arguments_dict_when_none():
    """brain_pulse tolerates `arguments=None` (an MCP client may omit the field)."""
    with patch("brain.mcp.pulse_core") as mock_pulse_core:
        mock_pulse_core.pulse.return_value = _FakePulseReport()
        session = object()
        mcp.call_tool("brain_pulse", None, session=session)

    mock_pulse_core.pulse.assert_called_once_with(session=session)


# ---------------------------------------------------------------------------
# Result-shape tests
# ---------------------------------------------------------------------------


def test_call_tool_returns_single_text_content_with_parseable_json():
    """Every successful call returns exactly one TextContent whose text is valid JSON."""
    with patch("brain.mcp.graph") as mock_graph:
        mock_graph.walk.return_value = {"root": "D20", "depth": 1, "levels": [], "nodes": {}}
        result = mcp.call_tool("brain_walk", {"doc_id": "D20"}, session=object())

    assert len(result) == 1
    assert result[0].type == "text"
    json.loads(result[0].text)  # must not raise


# ---------------------------------------------------------------------------
# Error-mapping tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_name,patch_target,call_kwargs,dispatch_attr",
    [
        (
            "brain_recall",
            "brain.mcp.retrieval",
            {"query": "q"},
            "recall",
        ),
        (
            "brain_walk",
            "brain.mcp.graph",
            {"doc_id": "D20"},
            "walk",
        ),
        (
            "brain_pulse",
            "brain.mcp.pulse_core",
            {},
            "pulse",
        ),
    ],
)
def test_operational_error_maps_to_brain_backend_unavailable(
    tool_name, patch_target, call_kwargs, dispatch_attr
):
    """A stubbed sqlalchemy OperationalError from any core maps to brain_backend_unavailable."""
    with patch(patch_target) as mock_core:
        getattr(mock_core, dispatch_attr).side_effect = OperationalError("stmt", {}, Exception())
        result = mcp.call_tool(tool_name, call_kwargs, session=object())

    payload = json.loads(result[0].text)
    assert payload["error"] == "brain_backend_unavailable"


@pytest.mark.parametrize(
    "tool_name,patch_target,call_kwargs,dispatch_attr",
    [
        ("brain_recall", "brain.mcp.retrieval", {"query": "q"}, "recall"),
        ("brain_walk", "brain.mcp.graph", {"doc_id": "D20"}, "walk"),
        ("brain_pulse", "brain.mcp.pulse_core", {}, "pulse"),
    ],
)
def test_chained_connection_error_maps_to_brain_backend_unavailable(
    tool_name, patch_target, call_kwargs, dispatch_attr
):
    """A RuntimeError raised `from` a ConnectionError still maps to brain_backend_unavailable.

    Exercises the __cause__ chain walk: a dependency error wrapped in a
    generic exception must still be recognised as a dependency failure.
    """

    def _raise(*_args, **_kwargs):
        try:
            raise ConnectionError("no route to host")
        except ConnectionError as exc:
            raise RuntimeError("wrapped") from exc

    with patch(patch_target) as mock_core:
        getattr(mock_core, dispatch_attr).side_effect = _raise
        result = mcp.call_tool(tool_name, call_kwargs, session=object())

    payload = json.loads(result[0].text)
    assert payload["error"] == "brain_backend_unavailable"


@pytest.mark.parametrize(
    "tool_name,patch_target,call_kwargs,dispatch_attr,expected_key",
    [
        ("brain_recall", "brain.mcp.retrieval", {"query": "q"}, "recall", "recall_failed"),
        ("brain_walk", "brain.mcp.graph", {"doc_id": "D20"}, "walk", "walk_failed"),
        ("brain_pulse", "brain.mcp.pulse_core", {}, "pulse", "pulse_failed"),
    ],
)
def test_bare_runtime_error_maps_to_tool_specific_failed_key(
    tool_name, patch_target, call_kwargs, dispatch_attr, expected_key
):
    """A bare (unclassified) RuntimeError maps to the tool's own `*_failed` key."""
    with patch(patch_target) as mock_core:
        getattr(mock_core, dispatch_attr).side_effect = RuntimeError("boom")
        result = mcp.call_tool(tool_name, call_kwargs, session=object())

    payload = json.loads(result[0].text)
    assert payload["error"] == expected_key


def test_unknown_tool_name_returns_unknown_tool_key():
    """An unrecognised tool name returns the distinct `unknown_tool` error key."""
    result = mcp.call_tool("brain_does_not_exist", {}, session=object())
    payload = json.loads(result[0].text)
    assert payload["error"] == "unknown_tool"


# ---------------------------------------------------------------------------
# Server shell + `syn mcp` subcommand (task 3)
# ---------------------------------------------------------------------------


def test_syn_mcp_is_a_registered_subcommand_with_no_arguments():
    """`syn mcp` parses with no arguments and sets `command == "mcp"`."""
    parser = _build_parser()
    args = parser.parse_args(["mcp"])
    assert args.command == "mcp"


def test_build_server_registers_list_tools_handler_matching_tool_definitions():
    """The registered `list_tools` handler returns exactly `tool_definitions()`.

    Drives the handler registered on the real `mcp.server.Server` directly —
    no subprocess and no live stdio transport.
    """
    server = mcp.build_server()
    handler = server.request_handlers[mcp_types.ListToolsRequest]

    result = asyncio.run(handler(mcp_types.ListToolsRequest(method="tools/list")))

    returned_tools = result.root.tools
    expected_tools = mcp.tool_definitions()
    assert [tool.name for tool in returned_tools] == [tool.name for tool in expected_tools]
    assert [tool.inputSchema for tool in returned_tools] == [
        tool.inputSchema for tool in expected_tools
    ]


# ---------------------------------------------------------------------------
# Protocol handshake replay (task 5)
#
# This block's headline acceptance criterion — "bastion's vendored MCP
# client connects to this server and invokes a Brain query tool end-to-end"
# — is declared `gateable: false` in the OR.R block record: its evidence
# lives in bastion, a sibling repo whose code this repo's checks cannot
# compile or run. `TestProtocolHandshakeReplay` does NOT prove that
# criterion. It proves protocol conformance on THIS side of the seam only,
# standing in for the missing cross-repo gate; the live run against
# bastion's Rust client remains an operator verification (see
# docs/mcp-contract.md).
# ---------------------------------------------------------------------------


def _load_handshake_fixture() -> dict:
    """Load the recorded initialize/tools-list/tools-call exchange fixture.

    Stored as an explicit JSON file (`tests/brain/fixtures/mcp_handshake.json`)
    rather than constructed ad hoc inside each assertion, so a reviewer can
    diff it against `docs/mcp-contract.md` by eye and a future
    protocol-version bump shows up as a fixture change rather than a silent
    behaviour change.
    """
    return json.loads((FIXTURES_DIR / "mcp_handshake.json").read_text(encoding="utf-8"))


class TestProtocolHandshakeReplay:
    """Drives the server's REGISTERED HANDLERS through a real MCP client session.

    Uses `mcp.shared.memory.create_connected_server_and_client_session`, which
    wires a real `mcp.client.session.ClientSession` to the real
    `mcp.server.lowlevel.server.Server` built by `mcp.build_server()` over
    in-memory `anyio` streams — no subprocess, no real stdin/stdout, no live
    Postgres. The read core is mocked (this task tests the protocol surface,
    not retrieval), and every assertion is on the SERVER'S RESPONSES as a
    protocol-conformant client would observe them, replaying the fixture in
    `tests/brain/fixtures/mcp_handshake.json`: `initialize`, then
    `tools/list`, then `tools/call` for `brain_recall`, then `tools/call` for
    a tool name that does not exist.

    See the module-level note above: this stands in for a cross-repo gate
    this repo structurally cannot run, and does not itself prove that
    bastion's vendored client interoperates — that remains an operator
    verification.
    """

    @pytest.fixture(name="handshake")
    def fixture_handshake(self):
        """The recorded exchange this replay drives and asserts against."""
        return _load_handshake_fixture()

    async def test_initialize_negotiates_the_declared_server_name(self, handshake):
        """`initialize` — the client session's real InitializeRequest/Result
        round trip over in-memory streams — reports this server's name.

        Captured by hand (rather than via `create_connected_server_and_client_
        session`, which discards the `InitializeResult`) so the assertion is
        against the actual negotiated `serverInfo`, not `Server.name`.
        """
        server = mcp.build_server()
        async with create_client_server_memory_streams() as (client_streams, server_streams):
            client_read, client_write = client_streams
            server_read, server_write = server_streams
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(
                    lambda: server.run(
                        server_read, server_write, server.create_initialization_options()
                    )
                )
                async with ClientSession(read_stream=client_read, write_stream=client_write) as client_session:
                    init_result = await client_session.initialize()
                task_group.cancel_scope.cancel()

        assert init_result.serverInfo.name == handshake["server_name"]

    async def test_tools_list_matches_the_recorded_tool_names(self, handshake):
        """`tools/list` returns exactly the fixture's recorded tool names, in order."""
        server = mcp.build_server()
        async with create_connected_server_and_client_session(server) as client_session:
            result = await client_session.list_tools()

        step = next(s for s in handshake["steps"] if s["step"] == "tools/list")
        assert [tool.name for tool in result.tools] == step["expected_tool_names"]
        # Schemas must match the same contract pinned above, not merely names.
        by_name = {tool.name: tool for tool in result.tools}
        for tool_name, expected_schema in EXPECTED_SCHEMAS.items():
            assert by_name[tool_name].inputSchema == expected_schema

    async def test_tools_call_brain_recall_returns_parseable_content(self, handshake):
        """A successful `tools/call` returns content a client can parse as JSON
        without further unwrapping, matching the fixture's recorded result."""
        step = next(
            s
            for s in handshake["steps"]
            if s["step"] == "tools/call" and s["tool"] == "brain_recall"
        )
        server = mcp.build_server()
        with patch("brain.mcp.retrieval") as mock_retrieval:
            mock_retrieval.recall.return_value = step["expected_result_json"]
            async with create_connected_server_and_client_session(server) as client_session:
                result = await client_session.call_tool("brain_recall", step["arguments"])

        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert json.loads(result.content[0].text) == step["expected_result_json"]

    async def test_tools_call_unknown_tool_returns_error_envelope_not_raise(self, handshake):
        """An unknown tool name comes back as the `unknown_tool` error envelope,
        not a raised exception — an exception escaping the handler is how a
        client sees a hang rather than a clean error response."""
        step = next(
            s
            for s in handshake["steps"]
            if s["step"] == "tools/call" and s["tool"] == "brain_does_not_exist"
        )
        server = mcp.build_server()
        async with create_connected_server_and_client_session(server) as client_session:
            result = await client_session.call_tool(step["tool"], step["arguments"])

        assert len(result.content) == 1
        payload = json.loads(result.content[0].text)
        assert payload["error"] == step["expected_error_key"]
