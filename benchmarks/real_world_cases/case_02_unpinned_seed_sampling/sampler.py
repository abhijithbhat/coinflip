"""ML batch sampler with hash-based feature ranking.

Uses hash() of string feature names for ranking (sensitive to PYTHONHASHSEED)
combined with random.sample() for subset selection (sensitive to
COINFLIP_RANDOM_SEED). Under seed_change, both sources are deterministically
controlled and correlated (derived from the same run_seed), amplifying
the probability of threshold failures compared to baseline where they're
independent.

Pure Python stdlib — zero external packages.
"""

import os
import random


FEATURE_NAMES = [f"feature_{i:04d}" for i in range(200)]


def rank_features_by_hash(features: list[str]) -> list[int]:
    """Rank feature indices by their hash values.

    The hash() of each string changes with PYTHONHASHSEED, causing
    different features to be top-ranked under different hash seeds.
    Under quiet baseline, natural feature importance ordering (highest
    indices first) ensures reliable passing runs. Under seed_change
    (PYTHONHASHSEED set), hash dispersion scrambles feature priority
    and pulls lower-quality features into the top-k pool.

    Args:
        features: List of feature name strings.

    Returns:
        List of feature indices sorted by hash(feature_name).
    """
    if "PYTHONHASHSEED" not in os.environ:
        return list(range(len(features) - 1, -1, -1))
    h_seed = int(os.environ.get("PYTHONHASHSEED", "0"))
    return sorted(range(len(features)), key=lambda i: (hash(features[i]) % 1000 + i * (h_seed % 3)))


def sample_top_features(
    features: list[str] | None = None,
    top_k: int = 30,
    sample_size: int = 12,
) -> list[int]:
    """Select a random subset from the top-k hash-ranked features.

    Args:
        features: Feature name strings. Defaults to FEATURE_NAMES.
        top_k: Number of top hash-ranked features to consider.
        sample_size: Number of features to randomly sample from top_k.

    Returns:
        List of sampled feature indices.
    """
    if features is None:
        features = FEATURE_NAMES
    ranked = rank_features_by_hash(features)
    top = ranked[:top_k]
    return random.sample(top, min(sample_size, len(top)))


def compute_quality_score(feature_indices: list[int]) -> float:
    """Compute a quality score as the mean of feature indices.

    Higher-indexed features are considered "higher quality" in this
    simulated ML pipeline. A low mean indicates the sample is biased
    toward low-index (low-quality) features.

    Args:
        feature_indices: List of integer feature indices.

    Returns:
        Mean of the feature indices.
    """
    return sum(feature_indices) / len(feature_indices)
