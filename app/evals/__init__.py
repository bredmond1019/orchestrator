"""Eval + success-metrics engine (Bastion Program Block OR.U).

This package hosts the offline eval harness: the scorer library, the
blind/randomized LLM-as-judge, the eval slice + runner primitives, the
per-domain slices, and the one-change self-improvement gate. It is invoked
offline via ``scripts/run_eval.py`` — nothing in ``app/core/`` or
``app/workflows/`` imports from here.

This module is a docstring-only marker owned by Task 2; later tasks add
submodules and import them directly (e.g. ``from evals.scorers import
ScoreResult``) without editing this file, keeping task file ownership
disjoint for parallel-merge safety.
"""
