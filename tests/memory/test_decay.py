"""Tests for app/memory/decay.py — pure confidence decay functions.

No I/O, no DB, no mocking needed — `freezegun` advances wall-clock time so
`weeks_between` can be exercised against `datetime.now()`.
"""

from datetime import datetime, timedelta

from freezegun import freeze_time
from memory.decay import effective_confidence, weeks_between


class TestWeeksBetween:
    """weeks_between: whole-week floor of the elapsed time delta."""

    def test_zero_weeks_when_same_instant(self):
        now = datetime(2026, 7, 1)
        assert weeks_between(now, now) == 0.0

    def test_zero_weeks_for_less_than_a_week(self):
        then = datetime(2026, 7, 1)
        now = then + timedelta(days=6, hours=23)
        assert weeks_between(then, now) == 0.0

    def test_one_week_at_exactly_seven_days(self):
        then = datetime(2026, 7, 1)
        now = then + timedelta(days=7)
        assert weeks_between(then, now) == 1.0

    def test_floors_fractional_weeks(self):
        then = datetime(2026, 7, 1)
        now = then + timedelta(days=13, hours=23)  # just under 2 weeks
        assert weeks_between(then, now) == 1.0

    def test_negative_delta_returns_zero(self):
        then = datetime(2026, 7, 8)
        now = datetime(2026, 7, 1)
        assert weeks_between(then, now) == 0.0

    def test_with_freezegun_frozen_now(self):
        then = datetime(2026, 7, 1)
        with freeze_time(then + timedelta(weeks=4)):
            assert weeks_between(then, datetime.now()) == 4.0


class TestEffectiveConfidence:
    """effective_confidence: confidence * decay_factor ** weeks_elapsed."""

    def test_zero_weeks_is_identity(self):
        assert effective_confidence(0.9, 0.95, 0) == 0.9

    def test_reference_case_matches_spec_formula(self):
        confidence = 0.9
        decay_factor = 0.95
        for weeks in (1, 2, 3, 8, 26):
            assert effective_confidence(confidence, decay_factor, weeks) == (
                confidence * decay_factor**weeks
            )

    def test_decay_is_monotonically_non_increasing(self):
        confidence = 0.9
        decay_factor = 0.95
        values = [effective_confidence(confidence, decay_factor, w) for w in range(10)]
        assert values == sorted(values, reverse=True)

    def test_decay_factor_one_never_decays(self):
        assert effective_confidence(0.9, 1.0, 52) == 0.9

    def test_freezegun_end_to_end_weeks_then_decay(self):
        """The reference case wired end-to-end through weeks_between."""
        updated_at = datetime(2026, 1, 1)
        confidence = 0.9
        decay_factor = 0.95
        weeks = 6
        with freeze_time(updated_at + timedelta(weeks=weeks)):
            elapsed = weeks_between(updated_at, datetime.now())
            result = effective_confidence(confidence, decay_factor, elapsed)
        assert elapsed == weeks
        assert result == confidence * decay_factor**weeks
