"""Naive Quick Fix: Slightly increase sleep to 0.015s.

Bumps the wait from 8ms to 15ms. Passes on a quiet machine because
10 events take ~4ms. But under CPU_HEAVY_LOAD, consumer processing balloons
to >35ms, so this fix STILL FAILS at high rates.

Coinflip Verdict: REJECTED (still fails under CPU_HEAVY_LOAD)
"""

import time

from event_queue import EventQueue


def test_all_events_flushed():
    """Emits 10 events and waits with slightly increased sleep."""
    eq = EventQueue()
    eq.start_consumer()

    for i in range(10):
        eq.emit(f"click_event_{i}")
    eq.signal_done()

    # Naive fix: slightly increased sleep (0.015s, still races under load)
    time.sleep(0.015)

    assert len(eq.flushed_events) == 10, (
        f"Only {len(eq.flushed_events)}/10 events flushed"
    )
