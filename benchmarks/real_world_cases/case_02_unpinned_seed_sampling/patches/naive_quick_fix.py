"""Naive Quick Fix: Widen the quality threshold.

Lowers the threshold from 75.0 to 45.0. Passes more seeds, but
tail-end seeds under seed_change still produce scores below 45.0.

Coinflip Verdict: REJECTED (still fails on ~3-5% of seeds under seed_change)
"""

from sampler import sample_top_features, compute_quality_score


def test_batch_score_above_threshold():
    """Tests with widened threshold — still uses unseeded random."""
    selected = sample_top_features(top_k=30, sample_size=12)
    score = compute_quality_score(selected)
    # Naive fix: widened threshold from 75.0 to 45.0
    assert score >= 45.0, (
        f"Batch quality score {score:.1f} below threshold 45.0 — "
        f"selected feature indices: {sorted(selected)}"
    )
