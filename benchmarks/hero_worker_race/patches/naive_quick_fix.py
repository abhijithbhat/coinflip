"""Naive Quick Fix: What an ordinary AI coding agent writes.

This "fix" simply increases the fixed sleep slightly from 0.006s to 0.009s.
It passes on a quiet baseline machine because the worker finishes in ~4-5ms.
However, under CPU_HEAVY_LOAD stress, GIL contention delays the worker beyond 25ms,
so this fix STILL FAILS at high rates.

Coinflip Verdict: REJECTED (passes baseline, fails under stress)
"""

import threading
import time

from worker_service import BackgroundWorker


def test_job_finishes():
    """Starts a background worker and asserts completion after a fixed sleep.

    NAIVE FIX: Increased sleep from 0.006s to 0.009s. This is the typical
    "just increase the timeout slightly" band-aid that passes on a quiet
    machine but breaks under real CPU contention.
    """
    worker = BackgroundWorker()
    t = threading.Thread(target=worker.run)
    t.start()
    # Naive fix: slight timeout increase (0.009s)
    time.sleep(0.009)
    assert worker.result_ready is True, "Background worker timed out before completion"
    t.join(timeout=1.0)
