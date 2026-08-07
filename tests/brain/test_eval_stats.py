"""Tests for app/brain/eval/stats.py — Wilson score intervals and seeded
bootstrap percentile intervals.

Fixtures are hand-computed and pinned exactly (to 4dp for Wilson); this is
the module OR.2.B exists to make trustworthy, so no "close enough" assertions.
"""

from brain.eval.stats import Interval, bootstrap_mean_interval, wilson_interval


def _round4(x: float) -> float:
    return round(x, 4)


class TestWilsonInterval:
    def test_15_of_17(self):
        result = wilson_interval(15, 17)
        assert _round4(result.lo) == 0.6566
        assert _round4(result.hi) == 0.9671
        assert result.point == 15 / 17
        assert result.n == 17
        assert result.method == "wilson"

    def test_15_of_15(self):
        result = wilson_interval(15, 15)
        assert _round4(result.lo) == 0.7961
        assert _round4(result.hi) == 1.0

    def test_22_of_23(self):
        result = wilson_interval(22, 23)
        assert _round4(result.lo) == 0.7901
        assert _round4(result.hi) == 0.9923

    def test_p_hat_zero_is_non_degenerate(self):
        result = wilson_interval(0, 10)
        assert result.point == 0.0
        assert result.lo == 0.0
        assert result.hi > 0.0

    def test_p_hat_one_is_non_degenerate(self):
        result = wilson_interval(10, 10)
        assert result.point == 1.0
        assert result.hi == 1.0
        assert result.lo < 1.0

    def test_n_zero_does_not_raise(self):
        result = wilson_interval(0, 0)
        assert result.n == 0
        assert result.point is None
        assert result.lo is None
        assert result.hi is None
        assert result.method == "wilson"

    def test_successes_out_of_range_raises(self):
        import pytest  # pylint: disable=import-outside-toplevel

        with pytest.raises(ValueError):
            wilson_interval(11, 10)
        with pytest.raises(ValueError):
            wilson_interval(-1, 10)

    def test_returns_interval_dataclass_with_to_dict(self):
        result = wilson_interval(5, 10)
        assert isinstance(result, Interval)
        d = result.to_dict()
        assert d["n"] == 10
        assert d["method"] == "wilson"
        assert "point" in d and "lo" in d and "hi" in d


class TestBootstrapMeanInterval:
    def test_same_seed_is_byte_identical(self):
        values = [0.0, 1.0, 0.5, 0.33, 1.0, 0.0, 0.5]
        r1 = bootstrap_mean_interval(values, seed=7, resamples=500)
        r2 = bootstrap_mean_interval(values, seed=7, resamples=500)
        assert r1 == r2

    def test_different_seed_may_differ(self):
        values = [0.0, 1.0, 0.5, 0.33, 1.0, 0.0, 0.5]
        r1 = bootstrap_mean_interval(values, seed=1, resamples=500)
        r2 = bootstrap_mean_interval(values, seed=2, resamples=500)
        # Not asserting inequality strictly (could coincide), but bounds must
        # both be well-formed and the point estimate identical regardless of
        # seed (point is the plain sample mean, not resampled).
        assert r1.point == r2.point == sum(values) / len(values)

    def test_empty_values_does_not_raise(self):
        result = bootstrap_mean_interval([])
        assert result.n == 0
        assert result.point is None
        assert result.lo is None
        assert result.hi is None
        assert result.method == "bootstrap"

    def test_uses_local_random_not_module_global(self):
        """Perturbing the global `random` module state must not change the
        bootstrap result for a given seed."""
        import random as random_module  # pylint: disable=import-outside-toplevel

        values = [0.2, 0.4, 0.6, 0.8, 1.0]
        before = bootstrap_mean_interval(values, seed=3, resamples=300)

        random_module.seed(999)
        for _ in range(50):
            random_module.random()

        after = bootstrap_mean_interval(values, seed=3, resamples=300)
        assert before == after

    def test_point_estimate_is_plain_mean(self):
        values = [1.0, 0.0, 0.5]
        result = bootstrap_mean_interval(values, seed=0, resamples=200)
        assert result.point == sum(values) / len(values)

    def test_bounds_bracket_plausible_range(self):
        values = [0.0] * 5 + [1.0] * 5
        result = bootstrap_mean_interval(values, seed=0, resamples=2000)
        assert 0.0 <= result.lo <= result.point <= result.hi <= 1.0

    def test_metadata_stamped(self):
        result = bootstrap_mean_interval([0.1, 0.2, 0.3], seed=42, resamples=100)
        d = result.to_dict()
        assert d["method"] == "bootstrap"
        assert d["seed"] == 42
        assert d["n"] == 3
