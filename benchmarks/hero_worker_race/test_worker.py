"""Flaky test: Background worker race condition.

This test exhibits the classic "fixed sleep guess" anti-pattern. Under quiet
baseline conditions, the worker finishes in ~15-20ms so the 25ms sleep
creates a razor-thin race (~0-10% failure). Under CPU_HEAVY_LOAD stress, thread
scheduling delays push the worker well beyond 25ms, causing >70% failure rate.

This test file matches the exact pattern from sandbox_engine/verify_phase4.py
(BASE_FLAKY_CODE) — Abhijith's validated reference implementation.

Expected behavior across Coinflip's 7 perturbation conditions:
  - baseline:        Low failure rate (~0-10%)
  - shuffle_order:   Similar to baseline (order doesn't affect this race)
  - seed_change:     Similar to baseline (seeds don't affect this race)
  - clock_shift:     Similar to baseline (clock skew doesn't affect time.sleep)
  - network_cut:     Similar to baseline (no network in this test)
  - cpu_half_cores:  Moderate increase (~15-40%)
  - cpu_heavy_load:  SHARP SPIKE (>70%) — THIS IS THE TRIGGERING CONDITION
"""

import threading
import time

from worker_service import BackgroundWorker


def test_job_finishes():
    """Starts a background worker and asserts completion after a fixed sleep.

    BUG: Uses time.sleep(0.025) as a "good enough" wait. This is a race
    condition — the worker thread may not have finished its 8 SHA-256
    iterations (each with 1ms delay) before the assertion fires.

    Under quiet conditions this mostly passes because the OS scheduler
    gives the worker thread enough time. Under cpu_heavy_load, background
    CPU burner threads compete for the GIL and OS scheduling slots,
    causing the worker to take 50-200ms+ instead of ~15-20ms.
    """
    worker = BackgroundWorker()
    t = threading.Thread(target=worker.run)
    t.start()
    # Flawed pattern: fixed arbitrary sleep (races worker under load)
    time.sleep(0.025)
    assert worker.is_completed is True, "Background worker timed out before completion"
    t.join(timeout=1.0)

