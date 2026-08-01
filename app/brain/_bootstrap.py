"""app/brain/_bootstrap.py — the one `scripts/` sys.path shim, shared.

`app/brain/ops.py` and `app/brain/reconcile.py` both need `scripts/index_brain.py`
importable bare (as `import index_brain`) so they can reach `index_brain.main`,
`index_brain._DEFAULT_BRAIN_PATH`, and `index_brain.parse_document` without a
second embed/index implementation. Putting the `sys.path` mutation in one leaf
module (no imports of its own beyond stdlib) — rather than one of `ops`/
`reconcile` importing the other for this side effect, or duplicating the four
lines in both — keeps the bootstrap singular without introducing an import
cycle between the two (repair dispatch in `ops` calls back into `reconcile`).
"""

import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _APP_DIR.parent / "scripts"
for _p in (_APP_DIR, _SCRIPTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
