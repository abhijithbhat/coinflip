"""Certified Real Fix: What Coinflip certifies as a true root-cause fix.

This fix replaces the flawed fixed-sleep guess with proper event-based
synchronization using worker.wait_for_completion(timeout=5.0), which
internally calls threading.Event.wait(). This is immune to CPU load
because the OS kernel wakes the waiting thread immediately when the
event is signaled, regardless of how many CPU burner threads are running.

Coinflip Verdict: CERTIFIED (0% failures on BOTH baseline AND cpu_heavy_load)
"""

import threading

from worker_service import BackgroundWorker


def test_job_finishes():
    """Starts a background worker and waits for completion via event signal.

    REAL FIX: Uses worker.wait_for_completion(timeout=5.0) which calls
    threading.Event.wait() — the correct synchronization primitive.
    The OS kernel handles the wake-up, so this is immune to CPU contention.
    """
    worker = BackgroundWorker()
    t = threading.Thread(target=worker.run)
    t.start()
    # Coinflip Real Fix: Proper event synchronization
    completed = worker.wait_for_completion(timeout=5.0)
    assert completed, "Worker timed out waiting for event signal"
    t.join(timeout=1.0)
