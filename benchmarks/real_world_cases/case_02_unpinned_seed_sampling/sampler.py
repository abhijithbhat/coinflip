"""ML batch sampler with reservoir sampling.

Uses random.sample() for subset selection across a feature pool.
Without a pinned local Random instance, unpinned sampling draws from
global module-level random state. Under seed sweeps (SEED_CHANGE),
stochastic variance in sampled indices causes quality scores to intermittently
breach tight assertion thresholds.

Pure Python stdlib — zero external packages.
"""

from __future__ import annotations

import random
from typing import Any

FEATURE_NAMES = [f"feature_{i:04d}" for i in range(200)]


def rank_features_by_hash(features: list[str]) -> list[int]:
    """Rank feature indices deterministically.

    Args:
        features: List of feature name strings.

    Returns:
        List of feature indices.
    """
    return list(range(len(features) - 1, -1, -1))


def sample_top_features(
    features: list[str] | None = None,
    top_k: int = 200,
    sample_size: int = 12,
    rng: Any = None,
) -> list[int]:
    """Select a random subset from feature indices.

    BUG: When rng is None, uses Python global module-level random.
    Under SEED_CHANGE seed sweeps, unpinned draws cause ~15-25% of runs
    to fall below tight quality thresholds.

    Args:
        features: Feature name strings.
        top_k: Number of features to consider.
        sample_size: Number of features to randomly sample.
        rng: Optional pinned random.Random instance.

    Returns:
        List of sampled feature indices.
    """
    pool_size = len(features) if features is not None else 200
    pool = list(range(min(top_k, pool_size)))
    draw_size = min(sample_size, len(pool))

    r = rng if rng is not None else random
    return r.sample(pool, draw_size)


def compute_quality_score(feature_indices: list[int]) -> float:
    """Compute a quality score as the mean of feature indices.

    Higher-indexed features represent higher quality in this pipeline.

    Args:
        feature_indices: List of integer feature indices.

    Returns:
        Mean of the feature indices.
    """
    if not feature_indices:
        return 0.0
    return sum(feature_indices) / len(feature_indices)
