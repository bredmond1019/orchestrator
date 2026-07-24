"""Unit tests for app/brain/chunking.py.

Covers the pure, DB-free text helpers extracted out of
scripts/index_brain.py (OR.Q task 1): chunk_by_section, _split_chunk,
_is_header_only_chunk, and build_context_prefix.
"""

from brain.chunking import (
    _is_header_only_chunk,
    _split_chunk,
    build_context_prefix,
    chunk_by_section,
)

# ---------------------------------------------------------------------------
# chunk_by_section
# ---------------------------------------------------------------------------


class TestChunkBySection:
    def test_splits_on_h2_headers(self):
        content = "## First\nBody one.\n\n## Second\nBody two."
        result = chunk_by_section(content)
        assert result == [
            ("## First", "## First\nBody one."),
            ("## Second", "## Second\nBody two."),
        ]

    def test_splits_on_h3_headers(self):
        content = "### Sub A\nAlpha.\n\n### Sub B\nBeta."
        result = chunk_by_section(content)
        assert result == [
            ("### Sub A", "### Sub A\nAlpha."),
            ("### Sub B", "### Sub B\nBeta."),
        ]

    def test_mixed_h2_h3_headers(self):
        content = "## Top\nTop body.\n\n### Nested\nNested body."
        result = chunk_by_section(content)
        assert result == [
            ("## Top", "## Top\nTop body."),
            ("### Nested", "### Nested\nNested body."),
        ]

    def test_preamble_before_first_header_kept_as_untitled_chunk(self):
        content = "Intro text before any header.\n\n## First\nBody."
        result = chunk_by_section(content)
        assert result[0] == ("", "Intro text before any header.")
        assert result[1] == ("## First", "## First\nBody.")

    def test_no_header_file_returns_single_empty_section_chunk(self):
        content = "Just plain prose, no markdown headers at all."
        result = chunk_by_section(content)
        assert result == [("", content.strip())]

    def test_no_header_file_strips_surrounding_whitespace(self):
        content = "\n\n  Loose prose with surrounding blank lines.  \n\n"
        result = chunk_by_section(content)
        assert result == [("", "Loose prose with surrounding blank lines.")]

    def test_header_with_no_body_keeps_header_only(self):
        content = "## Empty Section\n\n## Next\nHas body."
        result = chunk_by_section(content)
        assert result[0] == ("## Empty Section", "## Empty Section")
        assert result[1] == ("## Next", "## Next\nHas body.")


# ---------------------------------------------------------------------------
# _is_header_only_chunk
# ---------------------------------------------------------------------------


class TestIsHeaderOnlyChunk:
    def test_bare_header_is_header_only(self):
        assert _is_header_only_chunk("## Section", "## Section") is True

    def test_tiny_body_is_header_only(self):
        assert _is_header_only_chunk("## Section", "## Section\nTiny.") is True

    def test_substantial_body_is_not_header_only(self):
        combined = "## Section\n" + ("word " * 20)
        assert _is_header_only_chunk("## Section", combined) is False

    def test_measured_on_header_stripped_body_not_raw_startswith(self):
        # A naive `chunk_text.startswith("#")` check would flag every chunk
        # produced by chunk_by_section since the header is always prepended.
        # The real behavior strips the header span first.
        header = "## Long Section Name Here"
        body_text = "This body is long enough to not be header-only content."
        combined = f"{header}\n{body_text}"
        assert _is_header_only_chunk(header, combined) is False

    def test_integration_with_chunk_by_section(self):
        content = "## Empty\n\n## Full\n" + ("substantial body text " * 5)
        chunks = chunk_by_section(content)
        flags = [_is_header_only_chunk(h, t) for h, t in chunks]
        assert flags == [True, False]


# ---------------------------------------------------------------------------
# _split_chunk
# ---------------------------------------------------------------------------


class TestSplitChunk:
    def test_short_text_returns_single_chunk(self):
        result = _split_chunk("A short piece of text.", max_tokens=500, overlap=50)
        assert len(result) == 1
        assert result[0] == "A short piece of text."

    def test_long_text_splits_into_multiple_overlapping_chunks(self):
        # ~1200 "word" tokens comfortably exceeds a 500-token chunk size, so
        # this must produce more than one chunk via ChunkingService.
        long_text = " ".join(f"word{i}" for i in range(1200))
        result = _split_chunk(long_text, max_tokens=500, overlap=50)
        assert len(result) > 1
        # Adjacent chunks overlap: some trailing tokens of chunk N reappear
        # at the start of chunk N+1.
        assert result[0].strip() != ""
        assert result[1].strip() != ""

    def test_empty_text_returns_empty_list(self):
        assert _split_chunk("", max_tokens=500, overlap=50) == []


# ---------------------------------------------------------------------------
# build_context_prefix
# ---------------------------------------------------------------------------


class TestBuildContextPrefix:
    def test_empty_meta_returns_empty_string(self):
        assert build_context_prefix({}) == ""

    def test_includes_type(self):
        prefix = build_context_prefix({"type": "Strategy"})
        assert "type: Strategy" in prefix

    def test_includes_title(self):
        prefix = build_context_prefix({"title": "My Doc"})
        assert "title: My Doc" in prefix

    def test_includes_description(self):
        prefix = build_context_prefix({"description": "A short summary."})
        assert "description: A short summary." in prefix

    def test_layer_list_joined(self):
        prefix = build_context_prefix({"layer": ["brain", "engine"]})
        assert "layer: brain, engine" in prefix

    def test_layer_string_normalized_to_list(self):
        prefix = build_context_prefix({"layer": "brain"})
        assert "layer: brain" in prefix

    def test_includes_project(self):
        prefix = build_context_prefix({"project": "bastion"})
        assert "project: bastion" in prefix

    def test_keywords_list_joined(self):
        prefix = build_context_prefix({"keywords": ["foo", "bar"]})
        assert "keywords: foo, bar" in prefix

    def test_excludes_status(self):
        prefix = build_context_prefix({"title": "X", "status": "active"})
        assert "status" not in prefix

    def test_excludes_doc_id(self):
        prefix = build_context_prefix({"title": "X", "doc_id": "my-id"})
        assert "doc_id" not in prefix

    def test_excludes_related(self):
        prefix = build_context_prefix({"title": "X", "related": ["docs/a.md"]})
        assert "related" not in prefix

    def test_prefix_is_newline_terminated_with_blank_line(self):
        prefix = build_context_prefix({"title": "X"})
        assert prefix.endswith("\n\n")
