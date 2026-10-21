"""Flaky test: Async event queue race condition.

This test emits 10 events to a producer-consumer queue, then checks
that all events were flushed after a fixed sleep. Under quiet conditions,
the consumer drains the queue in ~3-5ms. Under CPU_HEAVY_LOAD, the
consumer thread experiences GIL contention, delaying drain past 8ms and
causing >80% failures.
"""

import time

from event_queue import EventQueue


def test_all_events_flushed():
    """Emits 10 events and asserts all are flushed after a fixed sleep.

    BUG: Uses time.sleep(0.008) to wait for the consumer to process
    10 events. Under quiet conditions this usually succeeds, but under
    heavy CPU contention and GIL switching, 10 events take >35ms,
    causing the assertion to fail.
    """
    eq = EventQueue()
    eq.start_consumer()

    for i in range(10):
        eq.emit(f"click_event_{i}")
    eq.signal_done()

    # Flawed pattern: fixed arbitrary sleep (0.008s)
    time.sleep(0.008)

    assert len(eq.flushed_events) == 10, (
        f"Only {len(eq.flushed_events)}/10 events flushed — "
        f"consumer thread likely starved for CPU"
    )
