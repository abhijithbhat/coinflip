"""Flaky test: Unpinned seed sampling with hash-dependent feature ranking.

This test uses hash() for feature ranking (PYTHONHASHSEED-sensitive) and
the module-level random for subset selection (COINFLIP_RANDOM_SEED-sensitive).
Under seed_change, both sources are deterministically correlated (same run_seed),
amplifying the chance of sampling low-quality features that fail the threshold.

Expected behavior across Coinflip's 7 perturbation conditions:
  - baseline:        Low failure (~2-5%, independent hash + random)
  - shuffle_order:   Low failure (~2-5%, shuffle doesn't affect hash/random)
  - seed_change:     ELEVATED failure (~8-15%) — THIS IS THE TRIGGERING CONDITION
  - clock_shift:     Low failure (~2-5%, clock doesn't affect hash/random)
  - network_cut:     Low failure (~2-5%, no network in this test)
  - cpu_half_cores:  Low failure (~2-5%, CPU doesn't affect hash/random)
  - cpu_heavy_load:  Low failure (~2-5%, CPU doesn't affect hash/random)
"""

from sampler import sample_top_features, compute_quality_score


def test_batch_score_above_threshold():
    """Tests that sampled features have adequate quality score.

    BUG: Uses the module-level random (which _pytest_hooks re-seeds under
    seed_change) and hash() (which changes with PYTHONHASHSEED under
    seed_change). The combination of correlated hash ranking + random
    selection means some seed values consistently produce low-quality
    samples that fail this threshold check.

    The threshold 75.0 is set so that ~8-15% of seed values under
    seed_change produce scores below it, while independent randomness
    (baseline) rarely does.
    """
    selected = sample_top_features(top_k=30, sample_size=12)
    score = compute_quality_score(selected)
    assert score >= 75.0, (
        f"Batch quality score {score:.1f} below threshold 75.0 — "
        f"selected feature indices: {sorted(selected)}"
    )
