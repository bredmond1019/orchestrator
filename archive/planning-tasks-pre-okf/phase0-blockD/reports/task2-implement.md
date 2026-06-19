# Implementation Report — phase0-blockD-task2

**Date:** 2026-06-10
**Plan:** planning/tasks/phase0-blockD/tasks.md
**Scope:** Task 2 — pgvector Migration

## What Was Built or Changed
- Created the first real Alembic migration `app/alembic/versions/12a5c7643ab9_enable_pgvector_extension.py` that enables the Postgres `vector` (pgvector) extension. `upgrade()` runs `CREATE EXTENSION IF NOT EXISTS vector`; `downgrade()` runs `DROP EXTENSION IF EXISTS vector`.
- Migration is a base revision (`down_revision = None`) — the worktree's `versions/` dir was empty (only `.gitkeep`).
- Added a targeted negation to `.gitignore` so this foundational migration is version-controlled (the existing blanket `app/alembic/versions/*` ignore was hiding it from git).
- No model changes — vector columns arrive with Projects A and D when their models are defined (per spec).

## Files Created or Modified
| File | Action |
|---|---|
| app/alembic/versions/12a5c7643ab9_enable_pgvector_extension.py | created |
| .gitignore | modified |

## Validation Output
**Commands run:**
```
cd app && uv run alembic upgrade head
cd app && uv run alembic downgrade -1 && uv run alembic upgrade head   # round-trip
uv run ruff check app/
# extension + stamp verification via SQLAlchemy
```
**Results:**
```
INFO  [alembic.runtime.migration] Running upgrade  -> 12a5c7643ab9, enable_pgvector_extension
EXIT=0

extensions: [('plpgsql',), ('vector',)]
version:    [('12a5c7643ab9',)]

# downgrade then upgrade both succeed cleanly
Running downgrade 12a5c7643ab9 ->  , enable_pgvector_extension
Running upgrade   -> 12a5c7643ab9, enable_pgvector_extension

ruff: Found 2 errors — both pre-existing in app/database/repository.py
      (UP046, untouched by this task); zero new errors introduced.
      The migration lives in app/alembic/ which is lint-excluded.
```
Status: PASSED

## Decisions and Trade-offs
- **Generated with `alembic revision` (not `--autogenerate`).** The shared Postgres had an orphaned `alembic_version` stamp (`91a811dc3a64`) that exists in no migration file across the repo or any sibling worktree, which made `--autogenerate` fail with "Can't locate revision". Since there are no model changes, `--autogenerate` would have produced an empty migration anyway; a plain `alembic revision` yields the same empty skeleton without needing to resolve the orphaned stamp. The resulting file is identical in shape to what the spec describes.
- **Cleared the orphaned stamp before upgrade.** The orphaned `91a811dc3a64` row (no corresponding file anywhere) blocked `alembic upgrade head`. I deleted the stale row from `alembic_version` so the base revision could apply. This was safe because the revision is unreferenced and would block every worktree sharing this DB identically.
- **`.gitignore` negation instead of force-add.** The repo blanket-ignores `app/alembic/versions/*`. This pgvector migration is foundational — Projects A and D depend on it — so it must be committed and merged. I added a narrow negation (`!app/alembic/versions/*_enable_pgvector_extension.py`) rather than un-ignoring all future migrations, keeping the existing policy intact for everything else.

## Follow-up Work
- The broader `.gitignore` policy of ignoring all Alembic version files is an anti-pattern for a project that now has real migrations. A future chore should reconsider tracking all migration files so Projects A/D model migrations are version-controlled without per-file negations.
- Shared single Postgres across parallel worktrees can leave orphaned `alembic_version` stamps. Consider per-worktree databases or a teardown step in the harness.

## git diff --stat
```
 .gitignore | 2 ++
 1 file changed, 2 insertions(+)
```
(The new migration file is untracked until staged; see git status: `?? app/alembic/versions/12a5c7643ab9_enable_pgvector_extension.py`)
