"""ingest_repo_log.py — Dogfood ingest of this repo's log.md into the memory tier.

Parses ``log.md``'s dated ``##``/``###`` entries into one
``Peer(peer_id="orchestrator", peer_type=PeerType.PRODUCT,
workspace_id="orchestrator")`` plus one ``AgentEpisode`` per entry, written
through the existing ``EpisodeWriteService`` (reused verbatim — no hand-rolled
inserts). This gives block OR.M's ``RetrieveChunksNode._memory_expand`` real
data to be proven against instead of an empty tier.

Ingest only. Consolidation over these episodes and any write-back to
``planning/knowledge.md``/``planning/memory.md`` are explicitly out of scope
(design decision 5, block OR.M) — see ``planning/or-m-memory-into-brain-rag/tasks.md``.

**``--dry-run`` is the deliverable's gate, not a convenience flag.** ``log.md``
is a *process* log ("ran /close-out, gates green, 1320 tests passed").
Distilled into facts and injected into answers, that risks being noise — it
teaches the tier about SDLC runs, not the product, and the durable content
already lives in ``knowledge.md``/``decisions/``, already indexed into
``brain_documents`` by ``scripts/index_brain.py``. Run ``--dry-run`` and read
the output before trusting the write path.

Usage:
    python scripts/ingest_repo_log.py --dry-run
    python scripts/ingest_repo_log.py --limit 5
    python scripts/ingest_repo_log.py --rebuild
    python scripts/ingest_repo_log.py --log-path /path/to/log.md --dry-run

Args:
    --dry-run       Parse and print entries without writing to DB or calling
                    the embedding API.
    --limit N       Ingest only the first N parsed entries.
    --rebuild       Delete existing ``orchestrator`` peer episodes before
                    re-ingesting from scratch.
    --log-path PATH Path to the log file to ingest (default: this repo's
                    root ``log.md``).
"""

import argparse
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# The single Peer this script's episodes accumulate under. This script never
# writes anything under a different workspace/peer.
_WORKSPACE_ID = "orchestrator"
_PEER_ID = "orchestrator"

_DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent / "log.md"

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
# "## [run: 2026-07-16]" or "## [2026-07-16]" — a pure session-grouping
# header (bracketed, with or without the "run:" label), not itself an entry.
_H2_RUN_MARKER_RE = re.compile(r"^\[(?:run:\s*)?(\d{4}-\d{2}-\d{2})\]$")
# "## 2026-06-23" — a bare date grouping header, not itself an entry.
_H2_BARE_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})$")
# "## 2026-06-22 (task 8 — validation pass ...)" — the date + title IS the entry.
_H2_TITLED_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s*\((.+)\)$")
# "### 2026-07-03 (Shipped OR.O ...)" — an H3 entry carrying its own embedded
# date, which can differ from (and must override) the enclosing H2 grouping
# header's date — the log has entries filed under a later session's grouping
# header that document work actually done on an earlier date.
_H3_OWN_DATE_RE = _H2_TITLED_RE


def _strip_trailing_rule(body: str) -> str:
    """Strip a trailing markdown horizontal-rule line (``---``) from ``body``."""
    return re.sub(r"\n?-{3,}\s*$", "", body).strip()


def parse_log_entries(content: str) -> list[dict]:
    """Parse ``log.md``'s dated ``##``/``###`` headings into flat entries.

    Two heading shapes carry an entry's date:

    - ``## [run: DATE]`` / ``## DATE`` — a session-grouping header with no
      title of its own; it sets the "current date" context for any ``###``
      sub-entries that follow, and is not itself an entry.
    - ``## DATE (title)`` — the date + title together ARE one entry (older
      log convention, no nested ``###`` headings).
    - ``### title`` — always an entry, dated by the nearest preceding ``##``
      grouping header.

    Returns a list of ``{"date": "YYYY-MM-DD", "title": str, "body": str}``
    dicts in file order. Headings whose date cannot be determined (e.g. a
    stray ``###`` before any ``##`` grouping header) are skipped rather than
    guessed at.
    """
    lines = content.splitlines()
    heading_positions = [
        i for i, line in enumerate(lines) if line.startswith("## ") or line.startswith("### ")
    ]

    entries: list[dict] = []
    current_date: str | None = None

    for idx, pos in enumerate(heading_positions):
        line = lines[pos]
        is_h2 = line.startswith("## ")
        text = line[3:].strip() if is_h2 else line[4:].strip()
        end = heading_positions[idx + 1] if idx + 1 < len(heading_positions) else len(lines)
        body = _strip_trailing_rule("\n".join(lines[pos + 1 : end]))

        if is_h2:
            titled_match = _H2_TITLED_RE.match(text)
            if titled_match:
                current_date = titled_match.group(1)
                entries.append({"date": current_date, "title": titled_match.group(2), "body": body})
                continue

            grouping_match = _H2_RUN_MARKER_RE.match(text) or _H2_BARE_DATE_RE.match(text)
            if grouping_match:
                current_date = grouping_match.group(1)
                continue

            # Unrecognized ## shape: best-effort — extract any date present,
            # otherwise fall back to the current context date, and treat the
            # whole heading text as the title.
            date_search = _DATE_RE.search(text)
            if date_search:
                current_date = date_search.group()
            if current_date is None:
                continue
            entries.append({"date": current_date, "title": text, "body": body})
        else:
            # An H3 may carry its own embedded date (e.g. filed under a later
            # session's H2 grouping header but documenting earlier-dated
            # work) — that embedded date wins over the grouping context.
            own_date_match = _H3_OWN_DATE_RE.match(text)
            if own_date_match:
                date, title = own_date_match.group(1), own_date_match.group(2)
            elif current_date is not None:
                date, title = current_date, text
            else:
                continue
            entries.append({"date": date, "title": title, "body": body})

    return entries


def _entry_summary(entry: dict) -> str:
    """Build the ``AgentEpisode.summary`` text for one parsed log entry."""
    if entry["body"]:
        return f"{entry['title']}\n\n{entry['body']}"
    return entry["title"]


def main(argv: list[str] | None = None) -> None:
    """Entry point for the repo-log dogfood ingest."""
    parser = argparse.ArgumentParser(
        description="Ingest this repo's log.md into the memory tier (Peer + AgentEpisode rows)."
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=None,
        help=f"Path to the log file to ingest (default: {_DEFAULT_LOG_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and print entries without writing to DB or calling the embedding API",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Ingest only the first N parsed entries",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete existing 'orchestrator' peer episodes before re-ingesting from scratch",
    )
    args = parser.parse_args(argv)

    log_path = args.log_path if args.log_path is not None else _DEFAULT_LOG_PATH
    if not log_path.is_file():
        raise SystemExit(f"Error: log file not found: {log_path}")

    content = log_path.read_text(encoding="utf-8")
    entries = parse_log_entries(content)
    if args.limit is not None:
        entries = entries[: args.limit]
        logger.info("--limit %d: processing first %d entr(y/ies) only", args.limit, len(entries))

    if args.dry_run:
        logger.info("Dry run — no DB writes, no API calls.")
        logger.info("Entries that would be ingested from %s:", log_path)
        for entry in entries:
            logger.info("  [%s] %s", entry["date"], entry["title"])
        logger.info("Total: %d entries", len(entries))
        return

    if not entries:
        logger.info("No entries parsed from %s — nothing to ingest.", log_path)
        return

    # D32: lazy imports — only pulled in for a real (non-dry-run) ingest, so
    # --dry-run never needs a DB connection or an embedding provider.
    app_dir = Path(__file__).resolve().parent.parent / "app"
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))

    from database.agent_episode import AgentEpisode  # pylint: disable=import-outside-toplevel
    from database.peer import PeerType  # pylint: disable=import-outside-toplevel
    from database.session import db_session  # pylint: disable=import-outside-toplevel
    from memory.episode_write_service import (  # pylint: disable=import-outside-toplevel
        EpisodeWriteService,
    )

    if args.rebuild:
        # peer_id is this script's own primary key ("orchestrator"), so scoping
        # the delete by it alone is sufficient — no join to Peer.workspace_id
        # needed.
        with next(db_session()) as session:  # type: ignore[arg-type]
            deleted = (
                session.query(AgentEpisode)
                .filter(AgentEpisode.peer_id == _PEER_ID)
                .delete(synchronize_session=False)
            )
            session.commit()
            logger.info("--rebuild: deleted %d existing episode(s)", deleted)

    service = EpisodeWriteService()
    written = 0
    for entry in entries:
        try:
            occurred_at = datetime.strptime(entry["date"], "%Y-%m-%d")
        except ValueError:
            occurred_at = None
        service.write(
            workspace_id=_WORKSPACE_ID,
            peer_id=_PEER_ID,
            peer_type=PeerType.PRODUCT,
            summary=_entry_summary(entry),
            outcome=None,
            tags=["log-entry"],
            occurred_at=occurred_at,
        )
        written += 1

    logger.info("Ingested %d episode(s) for peer '%s' (workspace '%s')", written, _PEER_ID, _WORKSPACE_ID)


if __name__ == "__main__":
    main()
