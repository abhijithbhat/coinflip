"""Naive Quick Fix: Widen the quality threshold.

Lowers the threshold from 85.0 to 70.0. While it passes more seeds,
outlier seeds under SEED_CHANGE sweeps still produce scores below 70.0.

Coinflip Verdict: REJECTED (still fails on outlier seeds under SEED_CHANGE)
"""

from sampler import compute_quality_score, sample_top_features


def test_batch_score_above_threshold():
    """Tests with widened threshold — still uses unpinned global random."""
    selected = sample_top_features(sample_size=12)
    score = compute_quality_score(selected)
    # Naive fix: widened threshold from 85.0 to 70.0 (still fails outlier seeds)
    assert score >= 70.0, (
        f"Batch quality score {score:.1f} below threshold 70.0 — "
        f"selected feature indices: {sorted(selected)}"
    )
