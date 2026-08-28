"""Unit tests for app/brain/code_chunking.py.

Pins the chunk boundaries and the whole-file fallback for the `code`
corpus (OR.P). These are the tests that matter most in the block: an
off-by-one line number makes every citation subtly wrong, and no other
test in this suite catches it — retrieval tests only check that a chunk
is *returned*, not that its line range is correct.

Fixture sources live under `tests/brain/fixtures/code/`:
  - `sample.py` — Python, a module-level constant + import, a top-level
    function, and a class with two methods.
  - `sample.rs` — Rust, the same shape (const, function, struct + impl
    with two methods).
  - `sample.txt` — no installed tree-sitter grammar for `.txt`; exercises
    the whole-file fallback.
  - `broken.py` — syntactically invalid Python; exercises the
    parse-failure fallback (same code path as the no-grammar fallback,
    but reached via a tree-sitter parse error instead of a missing
    grammar).

Every emitted tuple is asserted with `==` against a literal written out
in the test, per the block's testing_strategy: not a count, not a
subset — an added or shifted chunk must fail.
"""

from pathlib import Path

from brain.code_chunking import chunk_source

FIXTURES = Path(__file__).parent / "fixtures" / "code"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _tuples(chunks):
    return [(c.symbol_name, c.symbol_kind, c.start_line, c.end_line) for c in chunks]


class TestPythonBoundaries:
    def test_full_emitted_tuple_set(self):
        text = _read("sample.py")
        chunks = chunk_source(text, file_path="sample.py")
        assert _tuples(chunks) == [
            ("helper", "function", 8, 9),
            ("Widget", "class", 12, 19),
            ("Widget.__init__", "method", 15, 16),
            ("Widget.render", "method", 18, 19),
            (None, "module", 1, 5),
        ]

    def test_method_is_its_own_chunk_named_class_dot_method(self):
        text = _read("sample.py")
        chunks = chunk_source(text, file_path="sample.py")
        by_name = {c.symbol_name: c for c in chunks}

        init_chunk = by_name["Widget.__init__"]
        render_chunk = by_name["Widget.render"]
        class_chunk = by_name["Widget"]

        assert init_chunk.symbol_kind == "method"
        assert render_chunk.symbol_kind == "method"

        # The class chunk's range contains both method chunks' ranges.
        assert class_chunk.start_line <= init_chunk.start_line
        assert init_chunk.end_line <= class_chunk.end_line
        assert class_chunk.start_line <= render_chunk.start_line
        assert render_chunk.end_line <= class_chunk.end_line

    def test_module_chunk_covers_imports_and_constants(self):
        text = _read("sample.py")
        chunks = chunk_source(text, file_path="sample.py")
        module_chunk = next(c for c in chunks if c.symbol_kind == "module")

        assert module_chunk.symbol_name is None
        assert module_chunk.start_line == 1
        assert module_chunk.end_line == 5
        assert "import os" in module_chunk.content
        assert 'VERSION = "1.0"' in module_chunk.content

    def test_module_chunk_omitted_when_leftover_is_whitespace_only(self):
        text = "def only_fn():\n    return 1\n"
        chunks = chunk_source(text, file_path="only_fn.py")
        assert all(c.symbol_kind != "module" for c in chunks)

    def test_citation_section_format_for_symbol_chunk(self):
        text = _read("sample.py")
        chunks = chunk_source(text, file_path="sample.py")
        helper_chunk = next(c for c in chunks if c.symbol_name == "helper")
        assert helper_chunk.section == "helper (function, L8-9)"


class TestRustBoundaries:
    def test_full_emitted_tuple_set(self):
        text = _read("sample.rs")
        chunks = chunk_source(text, file_path="sample.rs")
        assert _tuples(chunks) == [
            ("helper", "function", 5, 7),
            ("Widget", "class", 9, 11),
            ("Widget.new", "method", 14, 16),
            ("Widget.render", "method", 18, 20),
            (None, "module", 1, 3),
        ]

    def test_impl_method_named_type_dot_method(self):
        text = _read("sample.rs")
        chunks = chunk_source(text, file_path="sample.rs")
        by_name = {c.symbol_name: c for c in chunks}

        assert by_name["Widget.new"].symbol_kind == "method"
        assert by_name["Widget.render"].symbol_kind == "method"
        assert by_name["Widget"].symbol_kind == "class"

    def test_module_chunk_covers_const_and_doc_comment(self):
        text = _read("sample.rs")
        chunks = chunk_source(text, file_path="sample.rs")
        module_chunk = next(c for c in chunks if c.symbol_kind == "module")

        assert module_chunk.start_line == 1
        assert module_chunk.end_line == 3
        assert 'const VERSION: &str = "1.0";' in module_chunk.content


class TestWholeFileFallback:
    def test_no_grammar_extension_yields_single_file_chunk(self):
        text = _read("sample.txt")
        chunks = chunk_source(text, file_path="sample.txt")

        assert len(chunks) == 1
        chunk = chunks[0]
        assert chunk.symbol_name is None
        assert chunk.symbol_kind == "file"
        assert chunk.start_line == 1
        assert chunk.end_line == _line_count(text)
        assert chunk.content == text

    def test_no_grammar_citation_section_format(self):
        text = _read("sample.txt")
        chunks = chunk_source(text, file_path="tests/brain/fixtures/code/sample.txt")
        assert chunks[0].section == f"sample.txt (file, L1-{_line_count(text)})"

    def test_parse_failure_falls_back_to_whole_file_without_raising(self):
        text = _read("broken.py")
        # Must not raise despite the syntactically invalid Python source.
        chunks = chunk_source(text, file_path="broken.py")

        assert len(chunks) == 1
        chunk = chunks[0]
        assert chunk.symbol_name is None
        assert chunk.symbol_kind == "file"
        assert chunk.start_line == 1
        assert chunk.end_line == _line_count(text)

    def test_parse_failure_citation_section_format(self):
        text = _read("broken.py")
        chunks = chunk_source(text, file_path="broken.py")
        assert chunks[0].section == f"broken.py (file, L1-{_line_count(text)})"

    def test_empty_file_yields_single_chunk_with_end_line_one(self):
        chunks = chunk_source("", file_path="empty.txt")
        assert len(chunks) == 1
        assert chunks[0].start_line == 1
        assert chunks[0].end_line == 1


def _line_count(text: str) -> int:
    """Mirror code_chunking._line_count's contract for test expectations."""
    if text == "":
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)
