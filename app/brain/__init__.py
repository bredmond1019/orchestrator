"""app/brain — the Brain (Synapse) knowledge-layer service package.

Houses the shared, deployment-agnostic slices that back the brain corpus:
chunking (``app/brain/chunking.py``) and, from OR.Q onward, the ingest
service (``app/brain/ingest.py``). Extracted per CLAUDE.md rule 10
(extract on the second consumer) once both ``scripts/index_brain.py`` and
the ``POST /ingest/*`` API route needed the same chunk→embed→write path.
"""
