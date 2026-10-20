"""Producer-consumer event queue with threaded consumer.

This module implements a simple event bus where producers enqueue events
and a consumer thread drains the queue, processing each event. The
consumer runs in a background thread and processes events at a rate
limited by per-event SHA-256 computation.

Under cpu_heavy_load, the consumer thread gets starved for CPU by
burner threads, causing it to drain the queue much slower than normal.

Pure Python stdlib — zero external packages.
"""

import hashlib
import os
import queue
import random
import threading
import time


class EventQueue:
    """Threaded event queue with background consumer.

    Events are added via emit() and processed by a background consumer
    thread that drains the internal queue and appends processed events
    to the flushed_events list.

    Attributes:
        flushed_events: List of successfully processed events.
    """

    def __init__(self) -> None:
        self._queue: queue.Queue[str | None] = queue.Queue()
        self.flushed_events: list[str] = []
        self._consumer_thread: threading.Thread | None = None

    def start_consumer(self) -> None:
        """Start the background consumer thread."""
        self._consumer_thread = threading.Thread(
            target=self._consume, daemon=True
        )
        self._consumer_thread.start()

    def emit(self, event: str) -> None:
        """Add an event to the queue for processing.

        Args:
            event: Event identifier string.
        """
        self._queue.put(event)

    def signal_done(self) -> None:
        """Signal the consumer that no more events will be produced."""
        self._queue.put(None)  # Sentinel value

    def wait_for_drain(self, timeout: float = 5.0) -> bool:
        """Wait for the consumer to finish processing all events.

        This is the correct synchronization primitive. It blocks until
        all items in the queue have been processed (task_done called
        for each) or the timeout expires.

        Args:
            timeout: Maximum seconds to wait.

        Returns:
            True if queue was fully drained, False if timed out.
        """
        if self._consumer_thread is None:
            return True
        self._consumer_thread.join(timeout=timeout)
        return not self._consumer_thread.is_alive()

    def _consume(self) -> None:
        """Background consumer loop: drain queue and process events."""
        is_cpu_stress = (
            os.environ.get("COINFLIP_CPU_LOAD") == "1"
            or os.environ.get("COINFLIP_PERTURBATION") in ("cpu_heavy_load", "cpu_half_cores")
        )
        is_ambient_tail = random.random() < 0.10 if not is_cpu_stress else False

        while True:
            event = self._queue.get()
            if event is None:
                self._queue.task_done()
                break
            # Simulate per-event processing work (SHA-256)
            _ = hashlib.sha256(event.encode()).digest()
            if is_cpu_stress:
                time.sleep(0.025)  # 10 events * 25ms = 250ms (fails both 20ms and 200ms fixed sleeps)
            elif is_ambient_tail:
                time.sleep(0.003)  # 10 events * 3ms = 30ms (fails 20ms unpatched sleep, passes 200ms naive fix)
            else:
                time.sleep(0.001)  # 10 events * 1ms = 10ms (passes both 20ms and 200ms)
            self.flushed_events.append(event)
            self._queue.task_done()
