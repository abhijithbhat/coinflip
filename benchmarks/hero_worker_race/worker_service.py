"""Background worker service simulating a CPU-bound report/job processor.

This module models a realistic background task that runs SHA-256 hashing
iterations in a separate thread and signals completion via a threading.Event.

Pure Python stdlib — zero external packages required.

Cross-platform note: The per-iteration time.sleep(0.001) adds ~1ms on Linux
(where Nebius sandboxes run) but rounds to ~15ms on Windows due to timer
granularity. Baseline flakiness rates will differ across platforms, but the
cpu_heavy_load stress amplification works on all platforms.
"""

import hashlib
import threading
import time


class BackgroundWorker:
    """Simulates a background report/job processor that performs CPU-bound work.

    The worker runs SHA-256 hashing iterations with small per-iteration delays
    in a thread. Under normal quiet conditions (Linux), the work completes in
    ~8-15ms. Under heavy CPU load (COINFLIP_CPU_HEAVY_LOAD), thread scheduling
    delays push the worker well beyond that, causing race conditions with
    fixed-sleep-based test assertions.

    Attributes:
        is_completed: Boolean flag set to True when all work iterations finish.
        done_event: threading.Event signaled upon completion for proper synchronization.
        result_hash: The final SHA-256 digest (bytes) from the last iteration.
    """

    def __init__(self) -> None:
        self.is_completed: bool = False
        self.done_event = threading.Event()
        self.result_hash: bytes = b""

    def run(self) -> None:
        """Executes CPU-bound hashing work across 8 iterations.

        Each iteration computes a SHA-256 digest and introduces a small
        per-iteration delay (1ms) to simulate realistic I/O or compute
        pauses. Total runtime on quiet Linux: ~8-15ms.
        Upon finishing all iterations, sets is_completed = True and
        signals done_event.
        """
        for i in range(8):
            self.result_hash = hashlib.sha256(f"job_{i}".encode()).digest()
            time.sleep(0.001)
        self.is_completed = True
        self.done_event.set()

    def wait_for_completion(self, timeout: float = 5.0) -> bool:
        """Blocks until the worker signals completion or the timeout expires.

        This is the correct synchronization primitive that should be used
        instead of a fixed time.sleep() guess. It uses threading.Event.wait()
        which is immune to CPU load fluctuations.

        Args:
            timeout: Maximum seconds to wait for the done_event signal.

        Returns:
            True if the worker completed within the timeout, False otherwise.
        """
        return self.done_event.wait(timeout=timeout)
