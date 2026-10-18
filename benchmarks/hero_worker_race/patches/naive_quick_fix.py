"""Naive Quick Fix: What an ordinary AI coding agent writes.

This "fix" simply increases the fixed sleep from 0.009s to 0.050s.
It passes 100% on a quiet baseline machine because the worker easily
finishes its 8 iterations in ~8-15ms. However, under cpu_heavy_load stress,
the worker can take 50-200ms+, so this fix STILL FAILS at >25% rate.

Coinflip Verdict: REJECTED (passes baseline, fails under stress)
"""

import threading
import time

from worker_service import BackgroundWorker


def test_job_finishes():
    """Starts a background worker and asserts completion after a fixed sleep.

    NAIVE FIX: Increased sleep from 0.009s to 0.050s. This is the typical
    "just increase the timeout" band-aid that passes on the developer's
    quiet laptop but breaks under real-world CPU contention.
    """
    worker = BackgroundWorker()
    t = threading.Thread(target=worker.run)
    t.start()
    # Naive fix: arbitrary timeout increase (0.050s)
    time.sleep(0.050)
    assert worker.is_completed is True, "Background worker timed out before completion"
    t.join(timeout=1.0)
