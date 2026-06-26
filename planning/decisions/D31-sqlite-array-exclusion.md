---
type: Decision
title: D31 — Exclude ARRAY and Vector models from SQLite test fixtures
description: SQLAlchemy models with PostgreSQL-only column types (ARRAY, Vector) must be excluded from the SQLite in-memory test database and tested only against real PostgreSQL.
doc_id: D31-sqlite-array-exclusion
layer: [engine]
project: python-orchestration
status: active
keywords: [SQLite, ARRAY, Vector, pgvector, SQLAlchemy, test fixtures]
related: [app-architecture-overview]
---

# D31 — Exclude ARRAY and Vector models from SQLite test fixtures

**Decided:** Any SQLAlchemy model that uses `ARRAY` or `Vector` columns must be explicitly
excluded from the SQLite in-memory test fixture (the `Base.metadata.create_all` call in
`conftest.py`) and tested only via integration tests that target a live PostgreSQL instance.

**Why:** SQLite does not support `ARRAY` or pgvector's `Vector` type. Allowing these models
to be registered with the SQLite test fixture causes import-time or setup-time failures that
break the entire test suite, not just the affected model's tests. The pattern was first
established for `LearningArtifact` (pgvector) and confirmed for `BrainDocument` (both
`ARRAY` and `Vector`). The exclusion is the correct isolation boundary — SQLite is fine for
pure-Python logic tests; PostgreSQL-specific types need PostgreSQL.

**How:** Pass `tables=` to `Base.metadata.create_all()` in the SQLite fixture, listing only
models that are SQLite-compatible. Add a comment naming the excluded models and the reason.

**Rejected:**
- *Try to emulate ARRAY/Vector in SQLite* — fragile, not representative of production
  behavior, and defeats the point of testing the real schema.
- *Skip the SQLite fixture entirely* — tests that don't need PostgreSQL (pure logic, schema
  shape, etc.) should stay fast and offline-capable; throwing away the SQLite fixture is
  unnecessary.
- *Leave excluded models in the fixture and suppress errors* — silent suppression hides real
  breakage.
