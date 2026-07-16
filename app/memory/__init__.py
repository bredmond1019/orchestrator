"""Memory module — the Brain's entity/memory layer (block OR.S).

A standalone, importable package (no coupling to any one workflow) providing
the reusable building blocks the two memory workflows
(``workflows/memory_ingest_workflow.py``, ``workflows/memory_consolidation_workflow.py``)
compose:

- ``decay``: pure confidence-decay functions.
- ``episode_write_service.EpisodeWriteService``: fast, ingest-time episode +
  peer-accumulation writes.
- ``upsert_memory_node.UpsertMemoryNode``: fact upserts with never-overwrite
  contradiction handling.
- ``memory_loader_node.MemoryLoaderNode``: session-start top-k loading,
  cosine and NL-query modes.

See ``docs/memory.md`` for the full architecture reference.
"""

from memory.decay import effective_confidence, weeks_between
from memory.episode_write_service import EpisodeWriteService
from memory.memory_loader_node import MemoryLoaderNode
from memory.upsert_memory_node import CONTRADICTION_PENALTY, UpsertMemoryNode

__all__ = [
    "effective_confidence",
    "weeks_between",
    "EpisodeWriteService",
    "UpsertMemoryNode",
    "CONTRADICTION_PENALTY",
    "MemoryLoaderNode",
]
