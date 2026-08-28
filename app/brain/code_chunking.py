"""app/brain/code_chunking.py — pure, DB-free source-code chunking for the `code` corpus.

Follows `app/brain/chunking.py`'s conventions (pure functions, no DB, no
embedding): this module owns splitting raw source text into
function/class/method-boundary chunks, and nothing else. `scripts/index_code.py`
is the caller that turns the output into `CodeChunk` rows.

Grammar support is deliberately narrow: Python and Rust cover the fleet
(per OR.P's block record). Any other extension — and any file that fails to
parse even with an installed grammar — takes the whole-file fallback rather
than being dropped: an indexed-coarsely file is visible to search, a silently
skipped file is not.

Line numbers are 1-indexed and inclusive throughout this module. tree-sitter
reports 0-indexed, inclusive `row` positions on `Node.start_point`/
`end_point`; the `+ 1` conversion happens exactly once, in `_line_range`,
so no other function in this module (or a caller) re-derives it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Extension -> language name. Only languages with an installed tree-sitter
# grammar (see `_GRAMMARS`) actually get boundary-aware chunking; every other
# extension resolves to "unknown" and takes the whole-file fallback.
_EXTENSION_LANGUAGES: dict[str, str] = {
    ".py": "python",
    ".rs": "rust",
}

# Populated lazily by `_get_language`, so importing this module never
# requires the tree-sitter grammar packages to be importable unless a
# supported-language file is actually chunked. Keys are language names
# ("python", "rust"); values are `tree_sitter.Language` instances.
_LANGUAGE_CACHE: dict[str, object] = {}


@dataclass(frozen=True)
class CodeChunkSpec:
    """One chunk emitted by `chunk_source` — not yet a DB row.

    `scripts/index_code.py` turns each spec into a `CodeChunk` row by adding
    `repo`, `file_path`, embedding, and `indexed_at`. `content` is the raw
    source text of the chunk's line range; `section` is the pre-rendered
    citation string that rides the recall() result dict's existing `section`
    field (see OR.P's out_of_scope — the recall envelope may not gain a new
    key for line-number provenance).
    """

    symbol_name: str | None
    symbol_kind: str  # "function" | "method" | "class" | "module" | "file"
    start_line: int  # 1-indexed, inclusive
    end_line: int  # 1-indexed, inclusive
    content: str
    language: str
    section: str


def _detect_language(file_path: str) -> str:
    """Resolve a language name from a file's extension.

    Returns "unknown" for any extension with no installed grammar — this is
    the trigger for the whole-file fallback, not an error.
    """
    for ext, language in _EXTENSION_LANGUAGES.items():
        if file_path.endswith(ext):
            return language
    return "unknown"


def _get_language(language: str):
    """Return a cached `tree_sitter.Language` for a supported language name.

    Returns `None` when the language has no installed grammar (or isn't one
    of the two supported languages), so callers fall back rather than raise.
    """
    if language in _LANGUAGE_CACHE:
        return _LANGUAGE_CACHE[language]

    # pylint: disable=import-outside-toplevel
    from tree_sitter import Language

    grammar = None
    try:
        if language == "python":
            import tree_sitter_python as ts_grammar

            grammar = Language(ts_grammar.language())
        elif language == "rust":
            import tree_sitter_rust as ts_grammar

            grammar = Language(ts_grammar.language())
    except ImportError:
        grammar = None

    _LANGUAGE_CACHE[language] = grammar
    return grammar


def _render_section(
    symbol_name: str | None, symbol_kind: str, start_line: int, end_line: int
) -> str:
    """Render the citation string ridden by recall()'s existing `section` field.

    `<symbol_name> (<symbol_kind>, L<start>-<end>)` for a real symbol chunk;
    callers of the whole-file fallback pass the file's basename as
    `symbol_name` with `symbol_kind="file"`, which naturally renders as
    `<basename> (file, L1-N)`. Defined once so the indexer and any future
    caller cannot disagree about the format.
    """
    return f"{symbol_name} ({symbol_kind}, L{start_line}-{end_line})"


def _line_range(node) -> tuple[int, int]:
    """Convert a tree-sitter node's 0-indexed rows to 1-indexed inclusive lines.

    The single place this conversion happens — see the module docstring.
    """
    return node.start_point[0] + 1, node.end_point[0] + 1


def _line_count(text: str) -> int:
    """Count lines the way a 1-indexed inclusive line range expects.

    An empty string is zero lines; any non-empty string has at least one
    line even with no trailing newline.
    """
    if text == "":
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def _whole_file_chunk(text: str, file_path: str, language: str) -> list[CodeChunkSpec]:
    """The fallback: exactly one chunk spanning the whole file.

    Used for an "unknown" language (no installed grammar) and for a file
    that fails to parse even with a grammar installed — indexed coarsely
    beats dropped silently.
    """
    basename = file_path.rsplit("/", 1)[-1]
    end_line = max(_line_count(text), 1)
    section = _render_section(basename, "file", 1, end_line)
    return [
        CodeChunkSpec(
            symbol_name=None,
            symbol_kind="file",
            start_line=1,
            end_line=end_line,
            content=text,
            language=language,
            section=section,
        )
    ]


def _node_text(text_lines: list[str], start_line: int, end_line: int) -> str:
    """Slice the original source by a 1-indexed inclusive line range."""
    return "\n".join(text_lines[start_line - 1 : end_line])


def _extract_python_chunks(root, text_lines: list[str]) -> list[CodeChunkSpec]:
    """Walk a Python parse tree's top level: functions, classes, methods.

    A method inside a class is emitted as its own chunk named
    `ClassName.method_name`; the class chunk itself covers the whole class
    body, so the method's range is deliberately a subset of the class
    chunk's range. This overlap is intentional (see the module docstring
    upstream in the block record): a "how does X work" query benefits from
    seeing both the method and its surrounding type, and
    `retrieval_engine._apply_diversity_cap` already prevents one file's
    chunks from flooding a result set.
    """
    chunks: list[CodeChunkSpec] = []
    leftover_starts: list[int] = []
    leftover_ends: list[int] = []

    for child in root.children:
        if child.type == "function_definition":
            name_node = child.child_by_field_name("name")
            name = name_node.text.decode("utf-8") if name_node else None
            start, end = _line_range(child)
            chunks.append(
                CodeChunkSpec(
                    symbol_name=name,
                    symbol_kind="function",
                    start_line=start,
                    end_line=end,
                    content=_node_text(text_lines, start, end),
                    language="python",
                    section=_render_section(name, "function", start, end),
                )
            )
        elif child.type == "class_definition":
            name_node = child.child_by_field_name("name")
            class_name = name_node.text.decode("utf-8") if name_node else None
            start, end = _line_range(child)
            chunks.append(
                CodeChunkSpec(
                    symbol_name=class_name,
                    symbol_kind="class",
                    start_line=start,
                    end_line=end,
                    content=_node_text(text_lines, start, end),
                    language="python",
                    section=_render_section(class_name, "class", start, end),
                )
            )
            body = child.child_by_field_name("body")
            if body is not None:
                for member in body.children:
                    if member.type == "function_definition":
                        m_name_node = member.child_by_field_name("name")
                        m_name = m_name_node.text.decode("utf-8") if m_name_node else None
                        qualified = f"{class_name}.{m_name}" if class_name and m_name else m_name
                        m_start, m_end = _line_range(member)
                        chunks.append(
                            CodeChunkSpec(
                                symbol_name=qualified,
                                symbol_kind="method",
                                start_line=m_start,
                                end_line=m_end,
                                content=_node_text(text_lines, m_start, m_end),
                                language="python",
                                section=_render_section(qualified, "method", m_start, m_end),
                            )
                        )
        else:
            start, end = _line_range(child)
            leftover_starts.append(start)
            leftover_ends.append(end)

    module_chunk = _build_module_chunk(leftover_starts, leftover_ends, text_lines, "python")
    if module_chunk is not None:
        chunks.append(module_chunk)

    return chunks


def _extract_rust_chunks(root, text_lines: list[str]) -> list[CodeChunkSpec]:
    """Walk a Rust parse tree's top level: functions, structs/enums, and
    `impl` methods.

    Rust separates a type's definition (`struct`/`enum`) from its methods
    (`impl`) into two different top-level items, so — unlike Python, where a
    method is nested directly inside its class node — a Rust method chunk is
    named `<ImplTargetType>.<method_name>` from the `impl` block's target
    type, but its own line range never extends into the struct/enum
    definition's range. This is a deliberate simplification: the two are
    already separately retrievable chunks, and merging their ranges would
    require chunk content that doesn't correspond to a single tree-sitter
    node span.
    """
    chunks: list[CodeChunkSpec] = []
    leftover_starts: list[int] = []
    leftover_ends: list[int] = []

    for child in root.children:
        if child.type == "function_item":
            name_node = child.child_by_field_name("name")
            name = name_node.text.decode("utf-8") if name_node else None
            start, end = _line_range(child)
            chunks.append(
                CodeChunkSpec(
                    symbol_name=name,
                    symbol_kind="function",
                    start_line=start,
                    end_line=end,
                    content=_node_text(text_lines, start, end),
                    language="rust",
                    section=_render_section(name, "function", start, end),
                )
            )
        elif child.type in ("struct_item", "enum_item"):
            name_node = child.child_by_field_name("name")
            name = name_node.text.decode("utf-8") if name_node else None
            start, end = _line_range(child)
            chunks.append(
                CodeChunkSpec(
                    symbol_name=name,
                    symbol_kind="class",
                    start_line=start,
                    end_line=end,
                    content=_node_text(text_lines, start, end),
                    language="rust",
                    section=_render_section(name, "class", start, end),
                )
            )
        elif child.type == "impl_item":
            type_node = child.child_by_field_name("type")
            impl_type = type_node.text.decode("utf-8") if type_node else None
            body = child.child_by_field_name("body")
            if body is not None:
                for member in body.children:
                    if member.type == "function_item":
                        m_name_node = member.child_by_field_name("name")
                        m_name = m_name_node.text.decode("utf-8") if m_name_node else None
                        qualified = f"{impl_type}.{m_name}" if impl_type and m_name else m_name
                        m_start, m_end = _line_range(member)
                        chunks.append(
                            CodeChunkSpec(
                                symbol_name=qualified,
                                symbol_kind="method",
                                start_line=m_start,
                                end_line=m_end,
                                content=_node_text(text_lines, m_start, m_end),
                                language="rust",
                                section=_render_section(qualified, "method", m_start, m_end),
                            )
                        )
        else:
            start, end = _line_range(child)
            leftover_starts.append(start)
            leftover_ends.append(end)

    module_chunk = _build_module_chunk(leftover_starts, leftover_ends, text_lines, "rust")
    if module_chunk is not None:
        chunks.append(module_chunk)

    return chunks


def _build_module_chunk(
    starts: list[int], ends: list[int], text_lines: list[str], language: str
) -> CodeChunkSpec | None:
    """Merge every top-level non-definition node into one `module` chunk.

    Spans from the earliest to the latest leftover line (imports, constants,
    a Rust `mod` body's loose items typically sit contiguously at the top of
    a file, so this range usually IS just that preamble). Returns `None`
    when there is no leftover code, or when the leftover text is only
    whitespace — a whitespace-only module chunk is deliberately skipped
    rather than indexed as an empty citation.
    """
    if not starts:
        return None

    start_line = min(starts)
    end_line = max(ends)
    content = _node_text(text_lines, start_line, end_line)
    if content.strip() == "":
        return None

    return CodeChunkSpec(
        symbol_name=None,
        symbol_kind="module",
        start_line=start_line,
        end_line=end_line,
        content=content,
        language=language,
        section=_render_section("module", "module", start_line, end_line),
    )


_EXTRACTORS = {
    "python": _extract_python_chunks,
    "rust": _extract_rust_chunks,
}


def chunk_source(text: str, *, file_path: str, language: str | None = None) -> list[CodeChunkSpec]:
    """Split source text into function/class/method-boundary chunks.

    Detects the language from `file_path`'s extension when `language` is not
    given. A language with no installed tree-sitter grammar — and a file
    that fails to parse even with one installed (a syntax error, a
    truncated file) — falls back to exactly one whole-file chunk rather than
    raising or being skipped: see the module docstring.
    """
    resolved_language = language or _detect_language(file_path)

    if resolved_language not in _EXTRACTORS:
        return _whole_file_chunk(text, file_path, resolved_language)

    grammar = _get_language(resolved_language)
    if grammar is None:
        return _whole_file_chunk(text, file_path, resolved_language)

    try:
        # pylint: disable=import-outside-toplevel
        from tree_sitter import Parser

        parser = Parser(grammar)
        tree = parser.parse(text.encode("utf-8"))
        root = tree.root_node
        if root.has_error:
            # tree-sitter is error-tolerant by design: a syntax error or a
            # truncated file does not raise, it just yields ERROR nodes
            # scattered through an otherwise-parsed tree. Boundary chunks
            # extracted around those errors would be unreliable, so treat
            # any parse error as the same signal a raised exception would
            # be and take the whole-file fallback.
            raise ValueError(f"tree-sitter parse error in {file_path}")
        text_lines = text.split("\n")
        extractor = _EXTRACTORS[resolved_language]
        chunks = extractor(root, text_lines)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning(
            "code_chunking: failed to parse %s as %s; falling back to whole-file chunk",
            file_path,
            resolved_language,
        )
        return _whole_file_chunk(text, file_path, resolved_language)

    if not chunks:
        return _whole_file_chunk(text, file_path, resolved_language)

    return chunks
