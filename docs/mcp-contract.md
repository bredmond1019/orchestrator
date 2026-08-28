---
type: Reference
title: Brain MCP Contract
description: The client-server contract for the Brain MCP server (syn mcp) — tool names, argument schemas, result shapes, and the error envelope that bastion's vendored Rust MCP client is written against.
doc_id: mcp-contract
layer: [brain]
project: synapse
status: active
keywords: [mcp, brain_recall, brain_walk, brain_pulse, stdio, contract, bastion]
related: [scripts, api-reference, workspace-contract]
---

# Brain MCP Contract

`syn mcp` serves the Brain read path (`recall` / `walk` / `pulse`) as an MCP server over stdio.
It is the **third** thin adapter over the same `app/brain` read core that `syn` itself (`app/brain/cli.py`,
OR.N1) and the HTTP router (`app/api/read.py`, OR.Q2/OR.3.B) already front — no second retrieval or
traversal implementation exists, so ranking, fusion and traversal output stay byte-identical across
all three surfaces.

**Consumer:** bastion's vendored Rust MCP client (`workflow-engine-mcp`, D26 split) is written
against this contract. `tests/brain/test_mcp.py` is the pin on this side of the seam — the schema
and dispatch tests fail loudly on any drift. **A change to any tool name or argument schema here is
a cross-repo contract change and requires a matching update in bastion.**

## Starting the server

```bash
uv run syn mcp
```

Serves over stdio; the process blocks until its stdin closes. No arguments.

## Tools

### `brain_recall`

Fronts `app.brain.retrieval.recall`. Every call is tagged `surface="mcp"` for the OR.K1 query log.

| Argument | Type | Required | Default | Bounds |
|---|---|---|---|---|
| `query` | string | yes | — | — |
| `limit` | integer | no | `5` | `1`–`50` |
| `hybrid` | boolean | no | `false` | — |
| `workspace` | string | no | `null` | — (OR.C workspace scoping) |

Arguments are passed through verbatim to `retrieval.recall` — the adapter does not re-implement
clamping or validation.

### `brain_walk`

Fronts `app.brain.graph.walk`.

| Argument | Type | Required | Default | Bounds |
|---|---|---|---|---|
| `doc_id` | string | yes | — | — |
| `depth` | integer | no | `1` | `1`–`5` |

### `brain_pulse`

Fronts `app.brain.pulse.pulse`. No arguments.

## Result shape

Every successful call returns a single-item list containing one `TextContent` (`type: "text"`)
whose `text` is one JSON document — a client parses exactly one payload per call, never prose:

- `brain_recall` → the JSON-serialized list `retrieval.recall` returns, in the core's original
  order (the adapter never re-sorts — score polarity is higher-is-better on every path, OR.K2).
- `brain_walk` → the JSON-serialized result of `graph.walk`.
- `brain_pulse` → the JSON-serialized `PulseReport` (via its own field serialization, not `str()`).

## Error envelope

A failure never raises out of `call_tool` and never hangs the transport. It is returned as the same
single-`TextContent` shape, with the text being a JSON object `{"error": <key>, "message": <str>}`:

| Key | When |
|---|---|
| `brain_backend_unavailable` | A dependency failure — pgvector/Postgres or the embedding backend unreachable — from any of the three cores. Classified by walking the exception's `__cause__`/`__context__` chain, so a dependency error wrapped in a generic exception is still recognised (`SQLAlchemy OperationalError`/`InterfaceError`, `ConnectionError`, `TimeoutError`, `OSError`). |
| `recall_failed` | Any other failure from `brain_recall`'s dispatch. |
| `walk_failed` | Any other failure from `brain_walk`'s dispatch. |
| `pulse_failed` | Any other failure from `brain_pulse`'s dispatch. |
| `unknown_tool` | The requested tool name is not one of the three above. |

## Versioning

The schema tables above and `tests/brain/test_mcp.py`'s literal pins must agree. Bump this doc and
the test pin together whenever a tool name, argument, default, or bound changes, and coordinate the
matching bastion-side client update before either side ships independently.

## What this doc does NOT verify

The headline cross-repo criterion — bastion's vendored Rust MCP client actually connecting to this
server and invoking a Brain query tool end-to-end — cannot be gated from this repo: the evidence
lives in a sibling repo whose code this repo's checks cannot compile or run. `tests/brain/test_mcp.py`'s
handshake-replay fixture (`TestProtocolHandshakeReplay`) drives this server's registered handlers
in-process through a recorded `initialize` / `tools/list` / `tools/call` exchange and proves protocol
conformance on this side of the seam only. **The live end-to-end run against bastion's client remains
an operator verification**, not something this repo's gate can observe.
