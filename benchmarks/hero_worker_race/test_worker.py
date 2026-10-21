"""Flaky test: Background worker race condition.

This test exhibits the classic "fixed sleep guess" anti-pattern. Under quiet
baseline conditions, the worker finishes in ~4-5ms so the 0.006s sleep
creates a razor-thin race (~5-12% natural failure when OS jitter occurs). Under
CPU_HEAVY_LOAD stress, thread scheduling and GIL contention delay the worker
well past 6ms, causing >85% failure rate.
"""

import threading
import time

from worker_service import BackgroundWorker


def test_job_finishes():
    """Starts a background worker and asserts completion after a fixed sleep.

    BUG: Uses time.sleep(0.006) as a "good enough" wait. This is a race
    condition — the worker thread may not have finished its payload processing
    loop before the assertion fires.
    """
    worker = BackgroundWorker()
    t = threading.Thread(target=worker.run)
    t.start()
    # Flawed pattern: fixed arbitrary sleep (0.006s)
    time.sleep(0.006)
    assert worker.result_ready is True, "Background worker timed out before completion"
    t.join(timeout=1.0)
