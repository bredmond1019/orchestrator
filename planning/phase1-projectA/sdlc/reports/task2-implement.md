# Implementation Report — phase1-projectA-task2

**Date:** 2026-06-20
**Plan:** planning/phase1-projectA/tasks.md
**Scope:** Task 2 — `LearningArtifact` model + migration

## What Was Built or Changed
- Added the `LearningArtifact` SQLAlchemy model (`app/database/learning_artifact.py`) on the shared `Base` from `database/session.py`, with columns `id` (UUID pk), `source_url`, `source_type`, `title`, `category`, `tl_dr`, `summary` (JSON), `embedding` (pgvector `Vector(1024)`), `fetch_status`, `make_blog` (Boolean), `created_at`. Exposes `EMBEDDING_DIM = 1024`.
- Imported the model in `app/alembic/env.py` (next to `from database.event import *`) so metadata/autogenerate sees it.
- Hand-authored Alembic migration `app/alembic/versions/a1b2c3d4e5f6_create_learning_artifacts_table.py` creating `learning_artifacts`, with `down_revision = '12a5c7643ab9'` (the pgvector revision) and the `Vector(1024)` embedding column.
- Added the `pgvector>=0.3.0` dependency (`pgvector==0.4.2`) to `pyproject.toml` / `uv.lock` — required for `pgvector.sqlalchemy.Vector`, which was not previously installed.
- Added a `.gitignore` negation (`!app/alembic/versions/*_create_learning_artifacts_table.py`) following the existing foundational-migration pattern so this migration is version-controlled.
- Added `tests/database/test_learning_artifact.py` — 14 tests covering model import, table name, column presence/types, primary key, the 1024-dim embedding column, and a full `GenericRepository` create/get round-trip against an in-memory SQLite DB (mirroring `tests/database/test_repository.py`).

## Files Created or Modified
| File | Action |
|---|---|
| app/database/learning_artifact.py | created |
| app/alembic/versions/a1b2c3d4e5f6_create_learning_artifacts_table.py | created |
| app/alembic/env.py | modified (one import line) |
| tests/database/test_learning_artifact.py | created |
| pyproject.toml | modified (added pgvector dep) |
| uv.lock | modified (lock pgvector) |
| .gitignore | modified (un-ignore this migration) |

## Validation Output
**Commands run:**
```
cd app && uv run python -c 'import main'
cd app && uv run python -c 'import worker.config'
cd app && uv run python -c 'import database.session'
cd app && uv run python -c 'import database.repository'
cd app && uv run alembic upgrade head        (env limitation — see note)
uv run python -m ruff check app/
uv run python -m pylint app/
uv run python -m pytest --collect-only -q      (258 tests collected)
uv run python -m pytest                        (258 passed)
```
**Result:** PASSED

Note: `alembic upgrade head` could not be physically applied — no Postgres server is
available in this sandbox (connection refused on localhost:5432; no docker/pg_ctl). The
migration was instead validated offline with `alembic upgrade head --sql`, which emits the
correct chained SQL (`CREATE EXTENSION ... vector` → `CREATE TABLE learning_artifacts (... embedding VECTOR(1024) ...)`)
under the Postgres dialect, confirming the revision chain and the Vector column compile. The
real `alembic upgrade head` runs against a live DB in the Test stage / deployment.

## Decisions and Trade-offs
- Added `pgvector` as a project dependency: the spec mandates `pgvector.sqlalchemy.Vector` but the package was absent from `pyproject.toml`. Without it the model cannot be imported.
- Used `uuid.uuid4` as the model-level pk default (standard random UUID) rather than `event.py`'s `uuid1`; the Task 1 schema also uses `uuid4`.
- Tests run against in-memory SQLite (per the repo's existing DB test pattern). pgvector's `Vector` column compiles to a permissive column type on SQLite, so list embeddings round-trip; the 1024-dim/Postgres behavior is asserted via the SQLAlchemy column type's `.dim` and the offline migration SQL.
- Tracked the migration via a `.gitignore` negation matching the existing `*_enable_pgvector_extension.py` convention, rather than a one-off `git add -f`, so it stays version-controlled across future operations.

## Follow-up Work
- None for Task 2. Downstream Task 5 (`StorageNode`) persists `LearningArtifact` rows with embeddings written at write time; this model/migration is its prerequisite.

## git diff --stat
```
 .gitignore                                         |   1 +
 app/alembic/env.py                                 |   1 +
 ...a1b2c3d4e5f6_create_learning_artifacts_table.py |  40 ++++++
 app/database/learning_artifact.py                  |  74 +++++++++++
 pyproject.toml                                     |   1 +
 tests/database/test_learning_artifact.py           | 135 +++++++++++++++++++++
 uv.lock                                            |  19 ++-
 7 files changed, 267 insertions(+), 4 deletions(-)
```
