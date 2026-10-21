"""Producer-consumer event queue with threaded consumer.

This module implements an event queue where producers enqueue events
and a background consumer thread drains the queue, processing each event
with realistic CPU work (SHA-256 rounds).

Under quiet baseline conditions, 10 events drain in ~3-5ms.
Under CPU_HEAVY_LOAD, GIL contention and thread scheduling delay consumer
progress to >35ms, causing fixed-sleep test assertions to fail.

Pure Python stdlib — zero external packages.
"""

from __future__ import annotations

import hashlib
import queue
import threading


class EventQueue:
    """Threaded event queue with background consumer.

    Events are enqueued via emit() and processed by a background consumer
    thread that drains the queue and appends processed events to flushed_events.

    Attributes:
        flushed_events: List of successfully processed events.
        drained: Boolean indicating whether all queued events finished processing.
    """

    def __init__(self) -> None:
        self._queue: queue.Queue[str | None] = queue.Queue()
        self.flushed_events: list[str] = []
        self._consumer_thread: threading.Thread | None = None
        self._drain_event = threading.Event()
        self.drained: bool = False

    def start_consumer(self) -> None:
        """Starts the background consumer thread."""
        self._consumer_thread = threading.Thread(
            target=self._consume, daemon=True
        )
        self._consumer_thread.start()

    def emit(self, event: str) -> None:
        """Adds an event to the queue for processing."""
        self._queue.put(event)

    def signal_done(self) -> None:
        """Signals the consumer that no more events will be produced."""
        self._queue.put(None)  # Sentinel value

    def wait_for_drain(self, timeout: float = 2.0) -> bool:
        """Waits for the consumer to finish processing all events.

        This is the correct synchronization primitive. It blocks until
        all items in the queue have been drained or the timeout expires.

        Args:
            timeout: Maximum seconds to wait.

        Returns:
            True if queue was fully drained, False if timed out.
        """
        return self._drain_event.wait(timeout=timeout)

    def _consume(self) -> None:
        """Background consumer loop: drain queue and process events."""
        while True:
            event = self._queue.get()
            if event is None:
                self.drained = True
                self._drain_event.set()
                self._queue.task_done()
                break
            # Realistic per-event computation
            h = event.encode()
            for _ in range(250):
                h = hashlib.sha256(h).digest()
            self.flushed_events.append(event)
            self._queue.task_done()
