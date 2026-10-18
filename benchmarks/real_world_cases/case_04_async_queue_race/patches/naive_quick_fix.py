"""Naive Quick Fix: Increase sleep to 0.200s.

Bumps the wait from 20ms to 200ms. Passes on a quiet machine because
10 events × ~1ms = ~10ms, well under 200ms. But under cpu_heavy_load,
the consumer's per-event time can balloon to 15-30ms each, making
10 events take 150-300ms — still exceeding 200ms frequently.

Coinflip Verdict: REJECTED (still fails >25% under cpu_heavy_load)
"""

import time

from event_queue import EventQueue


def test_all_events_flushed():
    """Emits 10 events and waits with inflated sleep."""
    eq = EventQueue()
    eq.start_consumer()

    for i in range(10):
        eq.emit(f"click_event_{i}")
    eq.signal_done()

    # Naive fix: increased sleep (still races under stress)
    time.sleep(0.200)

    assert len(eq.flushed_events) == 10, (
        f"Only {len(eq.flushed_events)}/10 events flushed"
    )
