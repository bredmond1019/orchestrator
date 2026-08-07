"""app/brain/eval/stats.py — Wilson score intervals and seeded bootstrap
percentile intervals, pure stdlib (`math` and `random` only).

`app/brain/eval/` is a pure-stdlib package — see
`tests/brain/test_eval.py::test_eval_package_imports_workflows_nowhere`, which
statically greps this package's imports. No numpy, no scipy.

Two estimators live here:

- `wilson_interval` — for 0/1 proportion metrics (`recall_at_5`, `recall_at_10`,
  `abstain_correctness`). The normal approximation exceeds 1.0 near p̂=1.0 and
  collapses to zero width exactly at p̂=1.0 — the precise failure that would
  let a `recall@10 = 1.0000` reading pass as certainty. Wilson does not have
  that failure mode: at 15/15 it still reports `[0.7961, 1.0]`.
- `bootstrap_mean_interval` — for metrics with a bounded, lumpy distribution
  (`mrr`'s discrete ladder with mass at 0; `groundedness` /
  `groundedness_on_hits`, continuous but bounded on [0, 1]) where a symmetric
  ±1.96·SD/√n interval is not defensible. Percentile method, seeded with a
  local `random.Random(seed)` instance — never the module-level `random` —
  so two calls with the same seed are byte-identical regardless of what any
  other caller in the process has done to global random state.
- `exact_sign_test` — the EXACT two-sided binomial sign test on discordant
  paired counts (`b` flipped worse, `c` flipped better), used by
  `runner.compare_to_baseline`'s paired per-case comparison. Not the normal
  approximation: the 5-vs-6 boundary (p=0.0625 vs p=0.03125) is the whole
  regression gate, and an approximation would blur exactly that boundary.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

DEFAULT_Z = 1.96
DEFAULT_RESAMPLES = 10000
DEFAULT_SEED = 0
DEFAULT_ALPHA = 0.05


@dataclass(frozen=True)
class Interval:
    """A point estimate plus a 95% interval and the method that produced it.

    `lo`/`hi`/`point` are `None` only in the documented `n=0` sentinel case —
    every other path returns real floats, including the p̂=0 and p̂=1 edges.
    """

    point: float | None
    lo: float | None
    hi: float | None
    n: int
    method: str
    seed: int | None = None

    def to_dict(self) -> dict[str, float | int | str | None]:
        """Flat, JSON-safe representation for stamping into a run report."""
        return {
            "point": self.point,
            "lo": self.lo,
            "hi": self.hi,
            "n": self.n,
            "method": self.method,
            "seed": self.seed,
        }


def wilson_interval(successes: int, n: int, z: float = DEFAULT_Z) -> Interval:
    """Wilson score interval for a binomial proportion.

    `successes` out of `n` trials, two-sided confidence level implied by `z`
    (default 1.96 → 95%). Reproduces (to 4dp): 15/17 -> [0.6566, 0.9671],
    15/15 -> [0.7961, 1.0], 22/23 -> [0.7901, 0.9923].

    `n=0` returns a sentinel `Interval` with `point`/`lo`/`hi` all `None`
    rather than raising — there is nothing to estimate from zero trials.
    """
    if n == 0:
        return Interval(point=None, lo=None, hi=None, n=0, method="wilson")

    if successes < 0 or successes > n:
        raise ValueError(f"successes={successes} out of range for n={n}")

    p_hat = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p_hat + z2 / (2 * n)) / denom
    half_width = (z * math.sqrt((p_hat * (1 - p_hat) / n) + (z2 / (4 * n * n)))) / denom

    lo = max(0.0, center - half_width)
    hi = min(1.0, center + half_width)

    return Interval(point=p_hat, lo=lo, hi=hi, n=n, method="wilson")


def bootstrap_mean_interval(
    values: list[float],
    *,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
    alpha: float = DEFAULT_ALPHA,
) -> Interval:
    """Seeded percentile bootstrap interval for the mean of `values`.

    Uses a local `random.Random(seed)` instance so results are deterministic
    across runs and unaffected by any other caller's use of the global
    `random` module. Two calls with the same `seed` produce identical bounds;
    different seeds may (but need not) differ.

    An empty `values` list returns the `n=0` sentinel rather than raising.
    """
    n = len(values)
    if n == 0:
        return Interval(point=None, lo=None, hi=None, n=0, method="bootstrap", seed=seed)

    point = sum(values) / n

    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(resamples):
        resample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(resample) / n)

    means.sort()
    lower_pct = alpha / 2
    upper_pct = 1 - alpha / 2
    lo_idx = min(round(lower_pct * (resamples - 1)), resamples - 1)
    hi_idx = min(round(upper_pct * (resamples - 1)), resamples - 1)
    lo = means[lo_idx]
    hi = means[hi_idx]

    return Interval(point=point, lo=lo, hi=hi, n=n, method="bootstrap", seed=seed)


def exact_sign_test(b: int, c: int) -> float:
    """Exact two-sided binomial sign test on `b` (flipped worse) vs. `c`
    (flipped better) discordant pairs; ties (concordant, unchanged pairs)
    are excluded before calling this — same convention the classic sign
    test uses.

    `n = b + c` discordant pairs, `k = min(b, c)`; under the null (each
    discordant pair is a fair coin flip) the two-sided p-value is
    `min(1.0, 2 * sum_{i=0}^{k} C(n, i) * 0.5**n)`. `n == 0` (no discordant
    pairs at all) returns `1.0` — nothing to test.

    Reproduces exactly (pinned as fixtures in `tests/brain/test_eval_stats.py`
    and the block's Acceptance Criteria table): (b=1,c=0)->1.00000,
    (3,0)->0.25000, (5,0)->0.06250, (6,0)->0.03125, (7,0)->0.01562,
    (5,1)->0.21875, (4,2)->0.68750, (0,0)->1.00000. The 5-vs-6 boundary
    (0.0625 vs 0.03125) is deliberately NOT approximated with a normal
    approximation — that boundary is the whole regression gate.
    """
    if b < 0 or c < 0:
        raise ValueError(f"b={b}, c={c} must both be non-negative")

    n = b + c
    if n == 0:
        return 1.0

    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) * (0.5**n)
    return min(1.0, 2 * tail)
