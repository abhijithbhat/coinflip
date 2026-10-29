"""Background worker service simulating a CPU-bound report/job processor.

This module models a realistic background task that runs CPU-bound payload
processing in a separate thread and signals completion via a threading.Event.

Pure Python stdlib — zero external packages required.
"""

from __future__ import annotations

import hashlib
import threading
import time


class BackgroundWorker:
    """Simulates a background report/job processor that performs CPU-bound work.

    The worker runs payload processing iterations with a tiny delay in a background thread.
    Under quiet baseline conditions, the worker finishes in ~4-6ms. Under heavy CPU load
    (CPU_HEAVY_LOAD with low GIL switch interval and burner threads), thread scheduling
    and GIL contention delay completion past 6ms, causing race conditions with
    fixed-sleep-based test assertions.

    Attributes:
        result_ready: Boolean flag set to True when payload processing finishes.
        is_completed: Boolean flag set to True for backwards compatibility.
        result_hash: The final SHA-256 digest from processing.
    """

    def __init__(self) -> None:
        self.result_ready: bool = False
        self.is_completed: bool = False
        self._done_event = threading.Event()
        self.done_event = self._done_event  # Alias for compatibility
        self.result_hash: bytes = b""

    def run(self) -> None:
        """Executes CPU-bound payload processing loop.

        Performs realistic multi-step Python payload processing iterations
        followed by a tiny delay before signaling completion.
        Under quiet baseline, completes in ~4-6ms. Under heavy CPU load / GIL
        contention, completion is slowed to >25ms.
        """
        h = b""
        for i in range(2):
            payload = f"job_metric_{i}_{i * 31}".encode()
            h = hashlib.sha256(payload).digest()
        self.result_hash = h
        time.sleep(0.002)

        self.result_ready = True
        self.is_completed = True
        self._done_event.set()

    def wait_for_completion(self, timeout: float = 2.0) -> bool:
        """Blocks until the worker signals completion or the timeout expires.

        This is the correct synchronization primitive that should be used
        instead of a fixed time.sleep() guess. It uses threading.Event.wait()
        which is immune to CPU load fluctuations.

        Args:
            timeout: Maximum seconds to wait for the done_event signal.

        Returns:
            True if the worker completed within the timeout, False otherwise.
        """
        return self._done_event.wait(timeout=timeout)
