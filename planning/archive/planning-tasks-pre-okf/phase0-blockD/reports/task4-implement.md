# Implementation Report — phase0-blockD-task4

**Date:** 2026-06-10
**Plan:** planning/tasks/phase0-blockD/tasks.md
**Scope:** Task 4 — TranscriptService

## What Was Built or Changed
- Created `app/services/transcript_service.py` — `TranscriptService` class with:
  - `_extract_video_id(url)` — regex-based YouTube video ID extraction (watch, youtu.be, embed, shorts forms); raises `ValueError` on unparseable URLs.
  - `fetch_transcript(url)` — fetches transcript via `youtube_transcript_api` and returns clean joined text; wraps fetch failures in a descriptive `RuntimeError`; raises `RuntimeError` on empty transcript (no silent empty-string returns, per spec).
  - `fetch_and_chunk(url, chunk_size=500, overlap=50)` — fetches then delegates to `ChunkingService.chunk_text` (Task 7) for overlapping token chunks.
- Exported `TranscriptService` from `app/services/__init__.py` (`__all__` updated).
- Created `tests/services/test_transcript_service.py` — 9 tests covering video-ID extraction (multiple URL forms + invalid), transcript joining, bad-URL `ValueError`, unavailable-transcript `RuntimeError`, empty-transcript `RuntimeError`, and chunk delegation with correct args.

## Files Created or Modified
| File | Action |
|---|---|
| app/services/transcript_service.py | created |
| tests/services/test_transcript_service.py | created |
| app/services/__init__.py | modified |

## Validation Output
**Commands run:**
```
uv run pytest tests/services/test_transcript_service.py -q
uv run pytest -q
uv run ruff check app/
uv run pylint app/services/transcript_service.py
cd app && uv run python -c "from services.transcript_service import TranscriptService"
```
**Results:**
```
tests/services/test_transcript_service.py: 9 passed
full suite: 210 passed, 7 warnings
ruff check app/: All checks passed!
pylint app/services/transcript_service.py: 10.00/10
import TranscriptService: ok
```
Status: PASSED

## Decisions and Trade-offs
- The breakdown's Step 4 sample code used the legacy `YouTubeTranscriptApi.get_transcript(video_id)` static API returning `list[dict]`. The installed library is v1.x, which exposes the **instance** method `YouTubeTranscriptApi().fetch(video_id)` returning a `FetchedTranscript` of snippet objects with a `.text` attribute (not dicts). Using the breakdown code verbatim would import fine but break at runtime. I implemented against the actually-installed API and updated the tests to mock `YouTubeTranscriptApi.fetch` and use snippet objects. tasks.md (authoritative for scope) only requires "extract video ID, fetch transcript, chunk delegation, error on bad URL," all of which are satisfied.
- Per spec, `fetch_transcript` never returns a silent empty string: fetch exceptions are re-raised as `RuntimeError` (chained with `from e`) and empty results raise `RuntimeError`.

## Follow-up Work
- `fetch_and_chunk` instantiates a fresh `ChunkingService()` per call (matches breakdown). If a shared/injected instance is preferred later, that is a trivial change. No deferred functionality.

## git diff --stat
```
 app/services/__init__.py | 2 ++
 1 file changed, 2 insertions(+)
```
(new files `app/services/transcript_service.py` and `tests/services/test_transcript_service.py` are untracked and not shown by `git diff --stat`)
