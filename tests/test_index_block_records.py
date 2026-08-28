"""Unit tests for parse_block_record() and the block-records crawler lane in
scripts/index_brain.py.

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
- `_collect_files` includes each manifest repo's `planning/blocks/*.json`,
  excludes underscore-prefixed records, and a malformed record is collected
  as an error rather than aborting the run (task 3)
"""

import copy
import json
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure scripts/ is importable (mirrors tests/test_index_brain.py).
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from index_brain import (  # noqa: E402
    BrainConfig,
    DocumentParseError,
    _block_records_files,
    _collect_files,
    chunk_by_section,
    main,
    parse_block_record,
)

BLOCKS_DIR = Path(__file__).resolve().parent.parent / "planning" / "blocks"
OR_R_PATH = BLOCKS_DIR / "OR.R.json"
EVAL_REPORT_PATH = BLOCKS_DIR / "OR.ticket.publishable-eval-report.json"

# Minimal brain.toml written into tmp_path for the main()-driven test below —
# mirrors tests/test_index_brain.py's _TEST_BRAIN_TOML.
_TEST_BRAIN_TOML = """\
[vocab]
layer = ["brain", "engine", "factory", "console", "surface", "infra", "business", "content", "meta"]
status = ["active", "draft", "deprecated", "superseded", "archived"]

[crawl]
skip_dirs = ["target", "node_modules", ".git", ".claude", ".agent", "planning/archive", "venv", ".venv"]

[[repos]]
slug = "brain"
tier = "_root"
repo_path = "."
status_file = "planning/status.md"
cache_doc = "README.md"
heading = "Company Brain"
"""

_MINIMAL_BLOCK_RECORD = {
    "id": "TB.1",
    "repo": "brain",
    "title": "Test block",
    "description": "A minimal block record for a crawler test.",
    "what": "Does a thing.",
}


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


# ---------------------------------------------------------------------------
# crawler lane — _block_records_files / _collect_files (task 3)
# ---------------------------------------------------------------------------


def _config_for(tmp_path: Path, *repos: dict) -> BrainConfig:
    return BrainConfig(
        valid_layers=frozenset({"brain"}),
        valid_projects=frozenset(r["slug"] for r in repos),
        valid_statuses=frozenset({"active"}),
        skip_dirs=(),
        repos=tuple(repos),
    )


class TestBlockRecordsCollection:
    """`_block_records_files` / `_collect_files` collect real committed records
    and every manifest repo's `planning/blocks/*.json`."""

    def test_collect_files_includes_known_committed_record(self):
        # Real repo root (this repo), real committed record — no tmp_path fixture,
        # per the "test against real records" rule this ticket's tests follow.
        repo_root = Path(__file__).resolve().parent.parent
        config = _config_for(
            repo_root, {"slug": "orchestrator", "repo_path": ".", "tier": "_root"}
        )
        rels = {
            p.relative_to(repo_root).as_posix() for p, _, _ in _collect_files(repo_root, config)
        }
        assert "planning/blocks/OR.R.json" in rels

    def test_block_records_files_includes_root_and_sub_repo(self, tmp_path):
        root_blocks = tmp_path / "planning" / "blocks"
        root_blocks.mkdir(parents=True)
        (root_blocks / "HQ.1.json").write_text(
            json.dumps(_MINIMAL_BLOCK_RECORD), encoding="utf-8"
        )

        leaf_blocks = tmp_path / "leaf" / "planning" / "blocks"
        leaf_blocks.mkdir(parents=True)
        leaf_record = {**_MINIMAL_BLOCK_RECORD, "id": "LF.1", "repo": "leaf"}
        (leaf_blocks / "LF.1.json").write_text(json.dumps(leaf_record), encoding="utf-8")

        config = _config_for(
            tmp_path,
            {"slug": "brain", "repo_path": ".", "tier": "_root"},
            {"slug": "leaf", "repo_path": "leaf", "tier": "_root"},
        )
        rels = {
            p.relative_to(tmp_path).as_posix()
            for p, _, _ in _block_records_files(tmp_path, config, set())
        }
        assert "planning/blocks/HQ.1.json" in rels
        assert "leaf/planning/blocks/LF.1.json" in rels

    def test_underscore_prefixed_record_is_excluded(self, tmp_path):
        blocks_dir = tmp_path / "planning" / "blocks"
        blocks_dir.mkdir(parents=True)
        (blocks_dir / "_draft.json").write_text(
            json.dumps(_MINIMAL_BLOCK_RECORD), encoding="utf-8"
        )
        (blocks_dir / "REAL.json").write_text(
            json.dumps(_MINIMAL_BLOCK_RECORD), encoding="utf-8"
        )

        config = _config_for(tmp_path, {"slug": "brain", "repo_path": ".", "tier": "_root"})
        rels = {
            p.relative_to(tmp_path).as_posix()
            for p, _, _ in _block_records_files(tmp_path, config, set())
        }
        assert "planning/blocks/REAL.json" in rels
        assert "planning/blocks/_draft.json" not in rels

    def test_malformed_block_record_is_collected_as_error_and_run_continues(
        self, tmp_path, caplog
    ):
        """A malformed block record must flow into the same error-collection
        path a broken markdown frontmatter file uses (main(), not collection
        time — _block_records_files doesn't parse JSON, so this exercises the
        read-step branch added in task 3)."""
        (tmp_path / "brain.toml").write_text(_TEST_BRAIN_TOML, encoding="utf-8")

        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "career.md").write_text("## Section\nGood content.", encoding="utf-8")

        blocks_dir = tmp_path / "planning" / "blocks"
        blocks_dir.mkdir(parents=True)
        (blocks_dir / "BROKEN.json").write_text("{not valid json", encoding="utf-8")

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.filter_by.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None
        mock_query.delete.return_value = 0
        mock_session.query.return_value = mock_query
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        def fake_db_session():
            yield mock_session

        mock_embed = MagicMock()
        mock_embed.embed_batch.return_value = [[0.1] * 1024]

        with (
            patch("database.session.db_session", fake_db_session),
            patch("services.embedding_service.EmbeddingService", return_value=mock_embed),
            caplog.at_level(logging.WARNING, logger="index_brain"),
        ):
            result = main(["--brain-path", str(tmp_path)])

        # The run did not abort — the good markdown doc still embedded.
        assert mock_embed.embed_batch.called
        # The malformed record is named in the logged summary, and the run
        # reports the failure via a non-zero exit rather than raising.
        assert "BROKEN.json" in caplog.text
        assert result == 1
