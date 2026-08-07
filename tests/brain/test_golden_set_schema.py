"""Schema validation for `planning/retrieval-golden-set.yaml` (OR.K2 task 2).

Guards the golden set's structural contract so a future edit can't silently
break the eval harness (OR.K2 task 3, which loads this file): every case has
the required fields, the case count stays within the 60-case hard cap, at
least 3 cases are deliberate negatives (broad NL questions with no in-corpus
answer, asserting `expect_abstain: true`), and at least 2 are exact-ID-hijack
cases (query text contains a token `app/brain/retrieval.py::ID_PATTERN`
would match, per the block spec's hijack requirement). This is a pure
YAML-shape test — no DB/embedding calls, no network.
"""

import re
from pathlib import Path

import pytest
import yaml

_GOLDEN_SET_PATH = (
    Path(__file__).resolve().parent.parent.parent / "planning" / "retrieval-golden-set.yaml"
)

# Mirrors app/brain/retrieval.py::ID_PATTERN exactly (kept in sync deliberately,
# not imported, so this test stays a pure-YAML check with zero app/ coupling).
_ID_PATTERN = re.compile(r"\b[A-Z]{1,5}(?:[0-9]{1,4}|(?:\.[A-Z0-9]{1,5})+)\b")

_REQUIRED_FIELDS = {"id", "query", "expect_docs", "expect_abstain", "source", "category"}
_ALLOWED_FIELDS = _REQUIRED_FIELDS | {"scope", "notes", "source_query_id"}
# ~3s/case means 60 cases is a ~3-minute eval — still interactive — and ~60
# hand-verified cases is the realistic ceiling one person can keep accurate.
_MAX_CASES = 60
# OR.2.D converted id-or-k2-self and id-or-k1-query-log (both dead expect_docs
# paths, verified absent from disk 2026-08-07) into abstain cases. That raised
# the negative count from 6 to 8: archive-03-parallelnode, neg-01..03,
# hijack-01..02 (all pre-existing), plus the two newly renamed neg-04/neg-05.
_MIN_NEGATIVES = 8
_MIN_HIJACK_CASES = 2

# HQ brain root that `expect_docs` paths are relative to — matches how the
# corpus indexer resolves and indexes these paths. Derived from this test
# file's location (tests/brain/ -> core/orchestrator/ -> core/ -> HQ root),
# never hardcoded, so the guard below stays correct if the repo moves.
_HQ_ROOT = Path(__file__).resolve().parents[4]

_VALID_SOURCES = {"authored", "mined", "archived"}
_VALID_CATEGORIES = {"archive", "identifier", "negative", "hijack", "mined"}

# First `-`-delimited id segment -> the category it must agree with. Keyed on
# the segment, NOT a substring match — `archive-11-or-v-hijack` contains the
# literal token "hijack" but is an `archive` case (see file-header note in the
# golden set and CLAUDE.md ground truth #4 for this block).
_PREFIX_TO_CATEGORY = {
    "archive": "archive",
    "id": "identifier",
    "neg": "negative",
    "hijack": "hijack",
    "mined": "mined",
}


@pytest.fixture(name="golden_set")
def fixture_golden_set() -> dict:
    """Load and return the parsed golden-set YAML document."""
    with _GOLDEN_SET_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_golden_set_file_exists():
    assert _GOLDEN_SET_PATH.is_file(), f"missing golden set at {_GOLDEN_SET_PATH}"


def test_golden_set_has_cases_list(golden_set):
    assert isinstance(golden_set, dict), "golden set must be a YAML mapping with a 'cases' key"
    assert "cases" in golden_set, "golden set must define a top-level 'cases' key"
    assert isinstance(golden_set["cases"], list), "'cases' must be a list"
    assert golden_set["cases"], "'cases' must not be empty"


def test_case_count_within_hard_cap(golden_set):
    cases = golden_set["cases"]
    assert len(cases) <= _MAX_CASES, (
        f"golden set has {len(cases)} cases, exceeding the hard cap of {_MAX_CASES} "
        "(this block's Acceptance Criteria — see the cap comment above)"
    )


def test_every_case_has_required_fields(golden_set):
    for case in golden_set["cases"]:
        assert isinstance(case, dict), f"each case must be a mapping, got: {case!r}"
        missing = _REQUIRED_FIELDS - case.keys()
        assert not missing, f"case {case.get('id', case)!r} is missing fields: {missing}"
        unknown = case.keys() - _ALLOWED_FIELDS
        assert not unknown, f"case {case['id']!r} has unrecognized fields: {unknown}"


def test_case_ids_are_unique(golden_set):
    ids = [case["id"] for case in golden_set["cases"]]
    duplicates = {case_id for case_id in ids if ids.count(case_id) > 1}
    assert not duplicates, f"duplicate case ids: {duplicates}"


def test_case_field_types(golden_set):
    for case in golden_set["cases"]:
        assert isinstance(case["id"], str) and case["id"], f"case id must be a non-empty str: {case}"
        assert isinstance(case["query"], str) and case["query"], (
            f"case {case['id']!r} query must be a non-empty str"
        )
        assert isinstance(case["expect_docs"], list), (
            f"case {case['id']!r} expect_docs must be a list"
        )
        for doc in case["expect_docs"]:
            assert isinstance(doc, str) and doc, (
                f"case {case['id']!r} expect_docs entries must be non-empty strings"
            )
        assert isinstance(case["expect_abstain"], bool), (
            f"case {case['id']!r} expect_abstain must be a bool"
        )
        assert case["source"] in _VALID_SOURCES, (
            f"case {case['id']!r} source {case['source']!r} must be one of {_VALID_SOURCES}"
        )
        assert case["category"] in _VALID_CATEGORIES, (
            f"case {case['id']!r} category {case['category']!r} must be one of "
            f"{_VALID_CATEGORIES}"
        )
        if "source_query_id" in case and case["source_query_id"] is not None:
            assert isinstance(case["source_query_id"], int), (
                f"case {case['id']!r} source_query_id must be an int or null"
            )
        if "scope" in case and case["scope"] is not None:
            assert isinstance(case["scope"], str) and case["scope"], (
                f"case {case['id']!r} scope must be a non-empty str or null"
            )
        if "notes" in case:
            assert isinstance(case["notes"], str), f"case {case['id']!r} notes must be a str"


def test_negative_cases_are_present_and_well_formed(golden_set):
    """Deliberate negatives: expect_abstain=true AND expect_docs=[] (no in-corpus
    answer exists, so the correct behavior is abstention, not a low-relevance hit)."""
    negatives = [
        case
        for case in golden_set["cases"]
        if case["expect_abstain"] is True and not case["expect_docs"]
    ]
    assert len(negatives) >= _MIN_NEGATIVES, (
        f"expected >= {_MIN_NEGATIVES} negative cases (expect_abstain=true, "
        f"expect_docs=[]), found {len(negatives)}"
    )


def test_exact_id_hijack_cases_are_present(golden_set):
    """>= 2 cases whose query contains an ID_PATTERN-matching token — the
    exact-ID-hijack fixture this block's Acceptance Criteria requires."""
    hijack_candidates = [
        case for case in golden_set["cases"] if _ID_PATTERN.search(case["query"])
    ]
    assert len(hijack_candidates) >= _MIN_HIJACK_CASES, (
        f"expected >= {_MIN_HIJACK_CASES} cases containing an ID_PATTERN-matching "
        f"token, found {len(hijack_candidates)}: "
        f"{[c['id'] for c in hijack_candidates]}"
    )


def test_explicitly_tagged_hijack_cases_match_id_pattern(golden_set):
    """Every case whose id is tagged 'hijack' must actually contain a token
    ID_PATTERN matches — guards against a hijack case being edited into a
    query that no longer exercises the pattern it exists to test."""
    tagged = [case for case in golden_set["cases"] if "hijack" in case["id"]]
    assert tagged, "expected at least one case id tagged 'hijack'"
    for case in tagged:
        assert _ID_PATTERN.search(case["query"]), (
            f"hijack-tagged case {case['id']!r} query {case['query']!r} does not "
            "match ID_PATTERN — it no longer exercises the hijack it's named for"
        )


def test_archive_cases_preserve_original_query_text(golden_set):
    """The 13 queries re-derived from
    planning/archive/test-runs/or-b-brain-retrieval-test-run1.md must appear
    verbatim (query text only re-derived expectations, per this block's spec)."""
    archived_queries = {
        "What are my hourly rates for contracting engagements?",
        "What blog posts have I published so far?",
        "How does ParallelNode handle thread safety and merging?",
        "What is my Toptal application prep strategy?",
        "Tell me about the Distrito job application",
        "What should I work on next in the orchestrator repo?",
        "How does the structural graph expansion in brain RAG retrieval work?",
        "What is the FileVault decision about the Mac Mini?",
        "What is amistad and what stage is it in?",
        "How do I set up local development for this repo?",
        "OR.V graph resolver cleanup",
        "What content ideas are queued for publishing?",
        "What is decision D20 about?",
    }
    present_queries = {case["query"] for case in golden_set["cases"]}
    missing = archived_queries - present_queries
    assert not missing, f"archived queries missing verbatim from the golden set: {missing}"


def test_expect_docs_or_abstain_present_for_every_case(golden_set):
    """A case must either name at least one expected doc, or explicitly expect
    abstention — never neither (an unscored, meaningless case)."""
    for case in golden_set["cases"]:
        assert case["expect_docs"] or case["expect_abstain"], (
            f"case {case['id']!r} has neither expect_docs nor expect_abstain=true "
            "— it can never score a pass"
        )


def test_id_prefix_agrees_with_category(golden_set):
    """The id-prefix convention and the new `category` field must agree,
    keyed on the FIRST `-`-delimited segment of the id — not a substring
    match. `archive-11-or-v-hijack` contains the literal token "hijack" but
    is an `archive` case; this assertion must pass on it while the existing
    substring-based `test_explicitly_tagged_hijack_cases_match_id_pattern`
    (which uses `"hijack" in case["id"]`) keeps matching it unchanged."""
    for case in golden_set["cases"]:
        prefix = case["id"].split("-", 1)[0]
        assert prefix in _PREFIX_TO_CATEGORY, (
            f"case {case['id']!r} has an unrecognized id prefix {prefix!r} — "
            f"add it to _PREFIX_TO_CATEGORY or rename the case"
        )
        expected_category = _PREFIX_TO_CATEGORY[prefix]
        assert case["category"] == expected_category, (
            f"case {case['id']!r} has category {case['category']!r} but its id "
            f"prefix {prefix!r} implies category {expected_category!r}"
        )

    # Pin the exact case this rule exists to protect: an id containing the
    # literal substring "hijack" that is nonetheless an `archive` case.
    hijack_shaped_archive_case = next(
        c for c in golden_set["cases"] if c["id"] == "archive-11-or-v-hijack"
    )
    assert hijack_shaped_archive_case["category"] == "archive"


def test_negative_case_count_matches_expected(golden_set):
    """Pin the exact negative count so a future edit that silently adds or
    removes a negative case is caught rather than sliding past a `>=` floor."""
    negatives = [
        case
        for case in golden_set["cases"]
        if case["expect_abstain"] is True and not case["expect_docs"]
    ]
    assert len(negatives) == _MIN_NEGATIVES, (
        f"expected exactly {_MIN_NEGATIVES} negative cases (expect_abstain=true, "
        f"expect_docs=[]), found {len(negatives)}: {[c['id'] for c in negatives]}"
    )


def test_expect_docs_paths_exist_on_disk(golden_set):
    """No case may name an `expect_docs` path that is absent from disk.

    This is the permanent guard OR.2.D adds: `id-or-k2-self` and
    `id-or-k1-query-log` each named a path under an archived planning
    directory that no longer exists, so they permanently scored 0.0 in
    recall instead of being converted to abstain cases. This test would
    have caught both the day their directories were archived.

    Paths are resolved against the HQ brain root (`_HQ_ROOT`), matching how
    the corpus indexer resolves and indexes `expect_docs` entries (they are
    HQ-relative, e.g. `core/orchestrator/planning/status.md`).
    """
    missing = []
    for case in golden_set["cases"]:
        for doc_path in case["expect_docs"]:
            resolved = _HQ_ROOT / doc_path
            if not resolved.is_file():
                missing.append((case["id"], doc_path, str(resolved)))
    assert not missing, (
        "golden set names expect_docs paths absent from disk (resolved against "
        f"HQ root {_HQ_ROOT}):\n"
        + "\n".join(
            f"  case {case_id!r}: {doc_path!r} -> {resolved!r}"
            for case_id, doc_path, resolved in missing
        )
    )


def test_source_query_id_only_set_for_mined_cases(golden_set):
    """`source_query_id` is optional metadata that is only meaningful (and
    only ever set) when `source: mined` — reject it anywhere else."""
    for case in golden_set["cases"]:
        source_query_id = case.get("source_query_id")
        if source_query_id is not None:
            assert case["source"] == "mined", (
                f"case {case['id']!r} sets source_query_id but source is "
                f"{case['source']!r}, not 'mined'"
            )
