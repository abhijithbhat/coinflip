"""Certified Real Fix: What Coinflip certifies as a true root-cause fix.

This fix replaces the flawed fixed-sleep guess with proper event-based
synchronization using worker.wait_for_completion(timeout=2.0), which
internally calls self._done_event.wait(). This is immune to CPU load
because the OS kernel wakes the waiting thread immediately when the
event is signaled.

Coinflip Verdict: CERTIFIED (0% failures on BOTH baseline AND cpu_heavy_load)
"""

import threading

from worker_service import BackgroundWorker


def test_job_finishes():
    """Starts a background worker and waits for completion via event signal.

    REAL FIX: Uses worker.wait_for_completion(timeout=2.0) which calls
    self._done_event.wait() — the correct synchronization primitive.
    """
    worker = BackgroundWorker()
    t = threading.Thread(target=worker.run)
    t.start()
    # Coinflip Real Fix: Proper event synchronization
    completed = worker.wait_for_completion(timeout=2.0)
    assert completed, "Worker timed out waiting for event signal"
    t.join(timeout=1.0)
