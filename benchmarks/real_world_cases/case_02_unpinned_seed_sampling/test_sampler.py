"""Flaky test: Unpinned seed sampling in ML feature selection.

This test uses the global module-level random for feature sampling.
Under SEED_CHANGE, each run receives a distinct deterministic seed
(10000 + run_id * 7919). Approximately 15%–25% of seed draws produce
feature subsets with average score below the 85.0 threshold, causing
reproducible flakiness.
"""

from sampler import compute_quality_score, sample_top_features


def test_batch_score_above_threshold():
    """Tests that sampled features meet the quality threshold.

    BUG: Uses module-level random state. When seeds change across CI runs
    or worker iterations, variance in random draws causes ~15-25% of runs
    to fall below 85.0.
    """
    selected = sample_top_features(sample_size=12)
    score = compute_quality_score(selected)
    assert score >= 85.0, (
        f"Batch quality score {score:.1f} below threshold 85.0 — "
        f"selected feature indices: {sorted(selected)}"
    )
