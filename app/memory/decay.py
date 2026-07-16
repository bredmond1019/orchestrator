"""Confidence decay — pure functions, no I/O.

Implements the block OR.S decay rule: a ``SemanticMemory`` fact's *effective*
confidence at query time is its stored ``confidence`` aged down by
``decay_factor`` for every whole week elapsed since it was last written
(``updated_at``). The stored ``confidence`` column itself is never mutated by
a background job — decay is always computed on read, in
``UpsertMemoryNode`` (before comparing an incoming fact against what's
stored) and in ``MemoryLoaderNode`` (for ranking).

Reference case (D-pinned in the spec): ``confidence * 0.95 ** weeks_elapsed``.
"""

from datetime import datetime


def weeks_between(then: datetime, now: datetime) -> float:
    """Return the number of whole weeks elapsed between ``then`` and ``now``.

    Fractional weeks are truncated (floor) toward zero: a fact updated 6 days
    ago has decayed 0 weeks, not ~0.86. Negative deltas (``now`` before
    ``then``) return 0.0 rather than a negative exponent, since a fact can
    never decay for negative time.
    """
    delta_seconds = (now - then).total_seconds()
    if delta_seconds <= 0:
        return 0.0
    return float(delta_seconds // (7 * 24 * 60 * 60))


def effective_confidence(
    confidence: float, decay_factor: float, weeks_elapsed: float
) -> float:
    """Return ``confidence`` aged down by ``decay_factor`` per week elapsed.

    ``effective = confidence * decay_factor ** weeks_elapsed``.

    At ``weeks_elapsed == 0`` this is the identity (returns ``confidence``
    unchanged) since any base raised to the 0th power is 1. Decay is
    monotonically non-increasing for ``0 <= decay_factor <= 1`` and
    ``weeks_elapsed >= 0``, which is the only regime this function is used in.
    """
    return confidence * (decay_factor**weeks_elapsed)
