"""Eval Record Database Model Module

This module defines the SQLAlchemy models for persisting offline eval results
produced by the Block OR.U eval harness (``scripts/run_eval.py`` and
``app/evals/``). Two tables back the regression-history primitive:

- ``EvalRun``: one row per (slice, model) execution of an eval slice, carrying
  the aggregated pass-rate and case counts for that run.
- ``EvalResult``: one row per individual case scored within a run, linked back
  to its parent ``EvalRun`` via a foreign key.

Column types are kept SQLite-compilable (mirroring ``event.py`` /
``learning_artifact.py``'s JSON/String/DateTime style, not
``brain_document.py``'s Postgres-only ARRAY type) so the in-memory unit suite
(``tests/conftest.py``) can create and exercise these tables without Docker.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID

from database.session import Base


class EvalRun(Base):
    """SQLAlchemy model for one aggregated run of an eval slice against one model.

    A single invocation of ``run_slice`` (see ``app/evals/runner.py``) produces
    exactly one ``EvalRun`` row per model under test, aggregating the pass-rate
    across every case in the slice. Successive runs of the same
    ``slice_name``/``model_name`` form the regression history that the
    one-change gate (``app/evals/gate.py``) compares against.
    """

    __tablename__ = "eval_runs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique identifier for this eval run",
    )
    slice_name = Column(
        String(150),
        nullable=False,
        doc="Name of the eval slice that was executed (e.g. 'coding')",
    )
    domain = Column(
        String(150),
        nullable=False,
        doc="North-star domain string this slice belongs to (e.g. 'coding')",
    )
    model_name = Column(
        String(150),
        nullable=False,
        doc="Identifier of the model under test for this run",
    )
    pass_rate = Column(
        Float,
        nullable=False,
        doc="Fraction of cases that passed, in [0.0, 1.0]",
    )
    case_count = Column(
        Integer,
        nullable=False,
        doc="Total number of cases scored in this run",
    )
    passed_count = Column(
        Integer,
        nullable=False,
        doc="Number of cases that passed in this run",
    )
    total_cost = Column(
        Float,
        nullable=True,
        doc="Total cost incurred running this slice against this model, if tracked",
    )
    total_duration_seconds = Column(
        Float,
        nullable=True,
        doc="Total wall-clock duration of this run in seconds, if tracked",
    )
    meta = Column(
        JSON,
        nullable=True,
        doc="Free-form metadata about the run (e.g. routing/config context)",
    )
    created_at = Column(
        DateTime,
        default=datetime.now,
        doc="Timestamp when this run was recorded",
    )


class EvalResult(Base):
    """SQLAlchemy model for a single scored case within an ``EvalRun``.

    Each row records the outcome of applying one scorer to one case's output
    within a parent run, mirroring the ``ScoreResult`` shape produced by the
    scorer library (``app/evals/scorers.py``).
    """

    __tablename__ = "eval_results"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique identifier for this eval result row",
    )
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("eval_runs.id"),
        nullable=False,
        index=True,
        doc="The EvalRun this case result belongs to",
    )
    case_id = Column(
        String(256),
        nullable=False,
        doc="Identifier of the case within the eval slice",
    )
    scorer = Column(
        String(150),
        nullable=False,
        doc="Name of the scorer that produced this result (e.g. 'deterministic')",
    )
    passed = Column(
        Boolean,
        nullable=False,
        doc="Whether the case passed according to this scorer",
    )
    score = Column(
        Float,
        nullable=True,
        doc="Optional continuous score (e.g. partial credit), when applicable",
    )
    detail = Column(
        JSON,
        nullable=True,
        doc="Free-form detail about the scoring outcome (e.g. failure reasons)",
    )
    created_at = Column(
        DateTime,
        default=datetime.now,
        doc="Timestamp when this result was recorded",
    )
