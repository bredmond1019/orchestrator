"""Unit tests for parse_block_record() in scripts/index_brain.py.

Tests run against REAL committed block records under `planning/blocks/`
(`OR.R.json` and `OR.ticket.publishable-eval-report.json`), never hand-built
fixtures — a fixture drifts from the authored record shape and stops testing
anything (see this ticket's testing_strategy).

Covers:
- doc_id derivation (block:<repo>:<block-id>)
- meta shape: type/title/description/project/keywords, and the deliberate
  absence of `related` (mev emit-graph does not crawl JSON; an unresolvable
  edge red-gates the corpus)
- body rendering: one `##` section per populated prose field, multi-chunk
  splitting via chunk_by_section, both acceptance-criteria forms (plain
  string and the D64 object form)
- the negative that protects the corpus: machine-only fields never leak
  into the rendered body
- an absent optional field renders without raising
- malformed JSON raises DocumentParseError
"""

import copy
import json
import sys
from pathlib import Path

import pytest

# Ensure scripts/ is importable (mirrors tests/test_index_brain.py).
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from index_brain import (  # noqa: E402
    DocumentParseError,
    chunk_by_section,
    parse_block_record,
)

BLOCKS_DIR = Path(__file__).resolve().parent.parent / "planning" / "blocks"
OR_R_PATH = BLOCKS_DIR / "OR.R.json"
EVAL_REPORT_PATH = BLOCKS_DIR / "OR.ticket.publishable-eval-report.json"


def _load_text(path: Path) -> str:
    assert path.is_file(), f"expected real committed block record at {path}"
    return path.read_text(encoding="utf-8")


def _load_record(path: Path) -> dict:
    return json.loads(_load_text(path))


# ---------------------------------------------------------------------------
# doc_id
# ---------------------------------------------------------------------------


def test_doc_id_is_repo_qualified_block_id():
    text = _load_text(OR_R_PATH)
    meta, _body = parse_block_record(text, file_path=OR_R_PATH)
    assert meta["doc_id"] == "block:orchestrator:OR.R"


# ---------------------------------------------------------------------------
# meta shape
# ---------------------------------------------------------------------------


def test_meta_carries_expected_okf_fields():
    record = _load_record(OR_R_PATH)
    text = _load_text(OR_R_PATH)
    meta, _body = parse_block_record(text, file_path=OR_R_PATH)

    assert meta["type"] == "Block"
    assert meta["title"] == record["title"]
    assert meta["description"] == record["description"]
    assert meta["project"] == "orchestrator"
    assert isinstance(meta["keywords"], list)
    assert 3 <= len(meta["keywords"]) <= 7


def test_meta_has_no_related_key():
    # mev emit-graph does not crawl JSON, so a `related` value here would be
    # a dangling edge the corpus cannot resolve and would red-gate the run.
    text = _load_text(OR_R_PATH)
    meta, _body = parse_block_record(text, file_path=OR_R_PATH)
    assert "related" not in meta


# ---------------------------------------------------------------------------
# body rendering
# ---------------------------------------------------------------------------


def test_body_has_a_heading_per_populated_field_and_chunks_multiple():
    record = _load_record(OR_R_PATH)
    text = _load_text(OR_R_PATH)
    _meta, body = parse_block_record(text, file_path=OR_R_PATH)

    field_to_heading = {
        "what": "## What",
        "why": "## Why",
        "out_of_scope": "## Out of scope",
        "acceptance_criteria": "## Acceptance criteria",
        "testing_strategy": "## Testing strategy",
        "notes": "## Notes",
    }
    for field, heading in field_to_heading.items():
        if record.get(field):
            assert heading in body, f"expected {heading!r} in body for populated field {field!r}"

    chunks = chunk_by_section(body)
    assert len(chunks) > 1


def test_object_form_acceptance_criterion_renders_criterion_text():
    for path in (OR_R_PATH, EVAL_REPORT_PATH):
        record = _load_record(path)
        object_entries = [
            entry for entry in record.get("acceptance_criteria", []) if isinstance(entry, dict)
        ]
        assert object_entries, f"expected a D64 object-form criterion in {path}"

        text = _load_text(path)
        _meta, body = parse_block_record(text, file_path=path)
        for entry in object_entries:
            assert entry["criterion"] in body


# ---------------------------------------------------------------------------
# the negative that protects the corpus
# ---------------------------------------------------------------------------


def test_machine_only_fields_do_not_leak_into_body():
    record = _load_record(OR_R_PATH)
    text = _load_text(OR_R_PATH)
    _meta, body = parse_block_record(text, file_path=OR_R_PATH)

    distinctive_rationale_phrase = "pushes only through HQ's git_push.sh"
    assert distinctive_rationale_phrase in record["workflow_rationale"]
    assert distinctive_rationale_phrase not in body

    assert record["spec_dir"] not in body


# ---------------------------------------------------------------------------
# absent optional field
# ---------------------------------------------------------------------------


def test_absent_optional_field_renders_without_that_heading_and_does_not_raise():
    record = copy.deepcopy(_load_record(OR_R_PATH))
    assert "notes" in record
    del record["notes"]

    text = json.dumps(record)
    _meta, body = parse_block_record(text, file_path=OR_R_PATH)

    assert "## Notes" not in body


# ---------------------------------------------------------------------------
# malformed input
# ---------------------------------------------------------------------------


def test_malformed_json_raises_document_parse_error():
    with pytest.raises(DocumentParseError):
        parse_block_record("{not valid json", file_path=Path("planning/blocks/BAD.json"))
