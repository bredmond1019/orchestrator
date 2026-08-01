"""Grep-verified guard: `app/brain/` imports `app/workflows/` nowhere (OR.K2).

Before this block, `app/brain/retrieval.py::hybrid_search` had a
function-local `from workflows.document_qa_workflow_nodes.retrieve_chunks_node
import RetrieveChunksNode` — an inverted dependency (a "brain" read-core
module reaching into a "workflow" node). OR.K2 task 1 promoted the shared
retrieval pipeline into `app/brain/retrieval_engine.py` so `app/brain/` no
longer needs to import anything from `app/workflows/`, in any form (top-level
or function-local).

This is a static source-text guard, not an import-time guard: `import ast`
parsing every `.py` file under `app/brain/` catches a reintroduced
function-local import even though it would never execute during collection.
"""

import ast
from pathlib import Path

_BRAIN_DIR = Path(__file__).resolve().parent.parent.parent / "app" / "brain"


def _imports_workflows(tree: ast.Module) -> list[str]:
    """Return every imported module name under `tree` that starts with
    "workflows" (covers `import workflows...` and `from workflows... import
    ...`, top-level or nested inside a function body — `ast.walk` visits
    every node regardless of nesting depth)."""
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            hits.extend(alias.name for alias in node.names if alias.name.startswith("workflows"))
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("workflows"):
                hits.append(node.module)
    return hits


def test_brain_package_imports_workflows_nowhere():
    offenders: dict[str, list[str]] = {}
    for path in sorted(_BRAIN_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        hits = _imports_workflows(tree)
        if hits:
            offenders[str(path.relative_to(_BRAIN_DIR.parent.parent))] = hits

    assert offenders == {}, f"app/brain/ must never import app/workflows/: {offenders}"
