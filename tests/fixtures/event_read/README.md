---
type: ProjectContext
title: "Golden fixtures — GET /events/{event_id} response bodies"
description: Pinned response-body fixtures for the event read API, one per derived status, used to catch response-shape drift in tests/api/test_event_read_golden.py.
doc_id: event-read-fixtures
layer: [engine]
project: orchestrator
status: active
keywords: [event read api, golden fixtures, data contract, derived status, task_context, event_id]
related: [or-y-event-read-api-tasks, data-contract]
---

# `event_read` fixtures — provenance and consumer contract

One pinned `GET /events/{event_id}` response body per status value in `api.event_status.EventStatus`:
`queued.json`, `running.json`, `succeeded.json`, `failed.json`, `cancelled.json`, `halted.json`. Each
file is a **full response body** — all six `EventStatusResponse` fields (`event_id`, `workflow_type`,
`status`, `created_at`, `updated_at`, `task_context`) — with a `task_context` shaped per
`docs/data-contract.md` §5/§6: a realistic `node_runs` map and, for the terminal-annotation states,
the run-level `metadata.failure` / `metadata.cancellation` / `metadata.budget` marker documented there.

## What these are for

`tests/api/test_event_read_golden.py` seeds a row carrying each fixture's `task_context`, calls the
live `GET /events/{event_id}` route, and asserts the response's key set matches the fixture's exactly
and the derived `status` equals the fixture's `status`. A drifting response shape (a renamed or
dropped field) or a status-derivation regression fails here first, before it reaches a consumer.

## Who consumes these

This repo owns the fixtures (D20's owner-owns-it pattern — see `tests/fixtures/task_context/README.md`
for the precedent). External consumers of the read API — `bastion-web`'s `BW.1.D` brain-rag query
surface, and any other client that polls `GET /events/{event_id}` — hand-type this contract against
their own language's model (there is no `typeshare` or codegen step for Python), and should stub
their read path against these files rather than hand-guessing the shape from `docs/data-contract.md`
prose alone.

## Re-publishing

These are **hand-authored**, not code-path-captured (unlike `tests/fixtures/task_context/`) — they
exist to pin the *response shape and status vocabulary*, not to assert byte-for-byte conformance of
one real workflow's output. Re-publish (edit these files) whenever `docs/data-contract.md` §5
(`task_context` shape, the `metadata.failure`/`cancellation`/`budget` markers) or §7 (the
`GET /events/{event_id}` response fields) changes — keep them synchronized with the version bump
described in `docs/data-contract.md`'s changelog, and re-run
`uv run python -m pytest tests/api/test_event_read_golden.py` to confirm the live route still agrees.
