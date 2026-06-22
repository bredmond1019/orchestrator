---
type: Tasks
title: Brain RAG — BrainDocument Model + Brain Corpus Indexer
description: Implement Layer 1 of the brain's sovereign context layer. New BrainDocument SQLAlchemy model + Alembic migration + index_brain.py ingestion script in python-orchestration-system. Reuses existing EmbeddingService, ChunkingService, and GenericRepository.
status: Not started
model: sonnet
target_repo: python-orchestration-system
---

# Brain RAG — Layer 1 Implementation

## Context

The brain repo is flat markdown. The python-orchestration-system already has Voyage AI + pgvector + ChunkingService + GenericRepository built and live (used by Project A). This workstream adds a new `BrainDocument` model and a standalone `index_brain.py` script that crawls brain docs, chunks them by section, embeds via Voyage AI, and stores in pgvector — making the brain semantically queryable.

This is Layer 1 of a three-layer architecture. Read `agentic-portfolio/planning/the-diagnostic/workstreams/brain-rag/index.md` for the full picture before starting.

**Layers 2 and 3 are NOT part of this workstream:**
- Layer 2 (retrieval via `RetrieveChunksNode`) — ships with Project D
- Layer 3 (MCP server / `/brain/search` endpoint) — ships with Project F

**This workstream only builds the write path** — crawl, chunk, embed, store. Reading/querying comes later.

---

## Prerequisites

- Working `python-orchestration-system` environment: PostgreSQL running, pgvector extension applied, `VOYAGE_API_KEY` set
- Familiar with the existing `LearningArtifact` model (`app/database/learning_artifact.py`) — `BrainDocument` follows the same pattern
- Read `agentic-portfolio/planning/the-diagnostic/workstreams/brain-rag/index.md` — schema, corpus scope, and architecture context

---

## Task 1 — `BrainDocument` SQLAlchemy model + Alembic migration

### New file: `app/database/brain_document.py`

Model based on the schema in `agentic-portfolio/planning/the-diagnostic/workstreams/brain-rag/index.md`:

```python
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from app.database.base import Base


class BrainDocument(Base):
    __tablename__ = "brain_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_path = Column(String(512), nullable=False)   # relative path from brain repo root
    doc_type = Column(String(50), nullable=False)     # decision|project|career|brand|business|content|diagnostic|memory
    section = Column(String(256))                     # H2/H3 header the chunk falls under
    content = Column(Text, nullable=False)            # the chunk text
    embedding = Column(Vector(1024))                  # Voyage AI voyage-2
    indexed_at = Column(DateTime, default=datetime.now)
    # Extended for diagnostic doc_type:
    client_slug = Column(String(128), nullable=True)          # e.g. "acme-sp-2026-07"
    workflow_patterns = Column(ARRAY(String), nullable=True)  # ["WhatsApp order tracking", ...]
```

### Export update: `app/database/__init__.py`
Add `BrainDocument` to the exports alongside `LearningArtifact`.

### New Alembic migration
Generate: `alembic revision --autogenerate -m "create_brain_documents_table"`
Review the generated migration — confirm it creates the `brain_documents` table with all columns including the `vector(1024)` column and the nullable `client_slug`/`workflow_patterns` columns.

### Tests
- Unit test: instantiate a `BrainDocument` with all required fields; verify it serializes correctly
- Verify migration applies cleanly: `alembic upgrade head` — no errors

---

## Task 2 — `scripts/index_brain.py`

New standalone script. This is NOT a workflow node — it runs from the CLI, not from Celery.

### Args

```
--brain-path PATH    Path to the brain repo root (default: ../agentic-portfolio)
--rebuild            Drop all existing brain_documents rows and re-index from scratch
--dry-run            Print what would be indexed without writing to DB
```

### Corpus definition

Hard-code the corpus scope (from `agentic-portfolio/planning/the-diagnostic/workstreams/brain-rag/index.md`):

```python
CORPUS = [
    ("docs/decisions", "decision"),
    ("docs/projects", "project"),
    ("docs/career.md", "career"),
    ("docs/brand.md", "brand"),
    ("docs/business", "business"),
    ("docs/content", "content"),
    ("docs/linkedin.md", "content"),
    ("docs/profile-and-pitch.md", "career"),
    ("planning/the-diagnostic", "diagnostic"),
    ("memory", "memory"),
    ("MEMORY.md", "memory"),
]
```

### Logic (in order)

1. **Parse args** — resolve `--brain-path` to an absolute path; validate it exists and looks like the brain repo (check for `docs/` and `MEMORY.md`).

2. **If `--rebuild`:** delete all rows from `brain_documents` where `client_slug IS NULL` (preserve diagnostic run entries).

3. **Walk corpus:** For each entry in `CORPUS`:
   - If it's a file: process that file
   - If it's a directory: walk with `pathlib.Path.rglob("*.md")`; skip files starting with `_`

4. **Per file — incremental check:** Query `brain_documents` for existing rows with this `file_path`. Get the max `indexed_at`. Compare to `file.stat().st_mtime`. If `indexed_at > mtime` (and not `--rebuild`): skip this file.

5. **Per file — chunk by section:**
   - Read the file content
   - Split on H2 (`## `) and H3 (`### `) headers using regex
   - Each chunk = header text (as `section`) + body text until the next header
   - If a chunk exceeds 500 tokens (use `ChunkingService` for token counting): split further with overlap
   - If the file has no headers: treat the entire file as one chunk with `section = ""`

6. **Batch embed:** Collect all chunk texts for this file → `EmbeddingService().embed_batch(texts)`. One API call per file.

7. **Upsert:** For each chunk: delete existing rows with matching `file_path` + `section`, then insert new `BrainDocument`. Use `GenericRepository` for DB operations.

8. **Progress logging:**
   ```
   Indexing docs/decisions/D1-solo-practice.md → 2 chunks (1 skipped, 1 new)
   Indexing docs/career.md → 4 chunks (all new)
   ...
   Done: 47 files, 183 chunks, 183 embeddings. Skipped: 12 files (unchanged).
   ```

### Error handling
- If a file fails to embed (VoyageAI error): log the error and continue — don't abort the whole run
- If DB write fails: log and continue
- At the end: print a summary of errors if any

### Tests

**Unit tests** (no DB, no API):
- `test_chunk_by_section`: given a markdown string with H2/H3 headers, verify chunking produces the right (section, content) pairs
- `test_doc_type_assignment`: given file paths from the corpus map, verify doc_type is assigned correctly
- `test_incremental_skip`: mock the DB query to return a recent `indexed_at`; verify the file is skipped

**Integration test** (requires DB + VoyageAI or a mock):
- Point the script at a fixture directory with 2–3 small markdown files
- Run with `--rebuild`
- Verify `brain_documents` table has the expected rows
- Run again without `--rebuild`; verify no new rows (incremental skip works)

---

## Task 3 — Document Layer 2 scope extension

Add a comment to the Project D context/planning area (wherever it will live — create `planning/phase1-projectD/notes.md` if it doesn't exist yet) noting the required scope extension:

```markdown
## Brain RAG integration (from brain-rag workstream)

RetrieveChunksNode must accept a `corpus` parameter:

    def retrieve_chunks(
        query: str,
        corpus: Literal["content", "brain"] = "content",
        k: int = 5,
        threshold: float = 0.0,
    ) -> list[ContentChunk]

When corpus="brain": query `brain_documents` table via cosine similarity on `embedding`.
When corpus="content": query `learning_artifacts` table (current behavior).

The `BrainDocument` model is in `app/database/brain_document.py` (ships with this workstream).
```

This note ensures whoever specs Project D wires in the corpus filter.

---

## Task 4 — Note in orchestrator's master-plan.md

Add a line under the shared services section in `planning/master-plan.md` referencing the brain indexer:

```markdown
- **Brain corpus indexer** (`scripts/index_brain.py`) — crawls the company brain repo,
  chunks by section, embeds via Voyage AI, stores in `brain_documents` table. Run manually
  to refresh: `python scripts/index_brain.py [--brain-path ../agentic-portfolio]`.
```

---

## Validation Commands

```bash
cd app && alembic upgrade head
uv run python -m pytest tests/ -k "brain" -v
uv run python -m pytest
uv run python -m ruff check app/
uv run python scripts/index_brain.py --brain-path ../agentic-portfolio --dry-run
```

All must pass. The `--dry-run` check must print a list of files that would be indexed (no DB writes, no errors).

## Verification

- [ ] `app/database/brain_document.py` exists with the schema above
- [ ] `BrainDocument` exported from `app/database/__init__.py`
- [ ] Alembic migration applies cleanly (`alembic upgrade head` — no errors)
- [ ] `scripts/index_brain.py` exists with `--brain-path`, `--rebuild`, `--dry-run` args
- [ ] Running `python scripts/index_brain.py --brain-path ../agentic-portfolio --dry-run` prints a list of files that would be indexed (no DB writes)
- [ ] Running with `--rebuild` populates `brain_documents` table; re-running without `--rebuild` skips unchanged files
- [ ] Unit tests pass for chunking, doc_type assignment, and incremental skip
- [ ] Integration test passes (fixture dir → DB rows)
- [ ] `planning/phase1-projectD/notes.md` (or equivalent) has the Layer 2 scope note
- [ ] `pytest` passes (all existing tests still green after adding the new model)
