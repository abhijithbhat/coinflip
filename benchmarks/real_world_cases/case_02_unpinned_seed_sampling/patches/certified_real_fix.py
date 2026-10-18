"""Certified Real Fix: Pin a local Random instance with a fixed seed.

Uses random.Random(42) instead of the module-level random. This makes
the sampling fully deterministic and immune to both PYTHONHASHSEED and
COINFLIP_RANDOM_SEED. The test also uses index-based ranking instead of
hash-based ranking to eliminate PYTHONHASHSEED sensitivity.

Coinflip Verdict: CERTIFIED (0% failures across all conditions)
"""

import random


def test_batch_score_above_threshold():
    """Tests with pinned local RNG — fully deterministic."""
    # Coinflip Real Fix: local RNG with fixed seed, no hash dependency
    rng = random.Random(42)
    feature_indices = list(range(200))
    selected = rng.sample(feature_indices, 12)
    score = sum(selected) / len(selected)
    assert score >= 75.0, (
        f"Batch quality score {score:.1f} below threshold 75.0 — "
        f"selected feature indices: {sorted(selected)}"
    )
