---
type: Decision
title: D32 — Lazy imports inside main() for standalone CLI scripts
description: Scripts under scripts/ import heavy dependencies (EmbeddingService, db_session, models) inside main() rather than at module level, so --dry-run and help flags work without a live DB or API key.
doc_id: D32-lazy-import-cli-scripts
layer: [engine]
project: orchestrator
status: active
keywords: [lazy imports, CLI scripts, EmbeddingService, dry-run, module-level imports]
related: [scripts, brain-rag]
---

# D32 — Lazy imports inside main() for standalone CLI scripts

**Decided:** Standalone CLI scripts in `scripts/` must defer all heavy or environment-dependent
imports (ORM sessions, service classes, API-key-consuming clients) to inside `main()` — not at
module level. The module-level body is limited to stdlib imports and `argparse` setup.

**Why:** Module-level imports of `EmbeddingService`, `db_session`, or `BrainDocument` trigger
SQLAlchemy engine construction, environment-variable reads, and (for embedding services) API
client initialization at `import` time. This means `--dry-run`, `--help`, and any import-only
usage (CI checks, documentation generation) require a live database connection and valid API keys
— even when the flag explicitly opts out of any network activity. First established for
`scripts/index_brain.py`: the dry-run path (`--dry-run`) must print the file list without
touching the DB or Voyage AI. The lazy-import pattern keeps scripts usable offline and makes the
`--dry-run` contract honest.

**How:** Move all non-stdlib imports below the `argparse.parse_args()` call inside `main()`.
Import only when the flag that needs them is active, or at the top of `main()` if all paths
need them but the module-level import isn't needed.

**Rejected:**
- *Module-level imports (status quo for non-script modules)* — correct for app modules where
  the environment is always initialized, but wrong for operator-facing scripts that must work
  in partial environments.
- *Separate `--no-init` flag to skip initialization* — more complex API for the same outcome;
  `--dry-run` already signals "no side effects."
- *Wrapper shell script that sets env vars before invoking* — shifts the burden to the caller
  and doesn't help when the script is imported or inspected by tooling.
