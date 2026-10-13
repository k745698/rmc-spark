"""Statistics for comparing systems (independent runs -> Mann-Whitney U, Cliff's delta, bootstrap CI)."""
from __future__ import annotations

import random


def bootstrap_ci(xs: list, stat=lambda v: sum(v) / len(v), n_boot: int = 5000, alpha: float = 0.05,
                 seed: int = 7) -> tuple:
    xs = [x for x in xs if x is not None]
    if not xs:
        return (None, None, None)
    rng = random.Random(seed)
    boots = sorted(stat([rng.choice(xs) for _ in xs]) for _ in range(n_boot))
    lo = boots[int(alpha / 2 * n_boot)]
    hi = boots[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return (stat(xs), lo, hi)


def cliffs_delta(a: list, b: list) -> float:
    """P(a > b) - P(a < b). |d| < 0.147 negligible, < 0.33 small, < 0.474 medium, else large."""
    a = [x for x in a if x is not None]
    b = [x for x in b if x is not None]
    if not a or not b:
        return float("nan")
    gt = sum(1 for x in a for y in b if x > y)
    lt = sum(1 for x in a for y in b if x < y)
    return (gt - lt) / (len(a) * len(b))


def magnitude(d: float) -> str:
    d = abs(d)
    return "negligible" if d < 0.147 else "small" if d < 0.33 else "medium" if d < 0.474 else "large"


def mann_whitney(a: list, b: list) -> float | None:
    """Two-sided p-value (scipy). None when a sample is too small."""
    a = [x for x in a if x is not None]
    b = [x for x in b if x is not None]
    if len(a) < 2 or len(b) < 2:
        return None
    from scipy.stats import mannwhitneyu
    return float(mannwhitneyu(a, b, alternative="two-sided").pvalue)
