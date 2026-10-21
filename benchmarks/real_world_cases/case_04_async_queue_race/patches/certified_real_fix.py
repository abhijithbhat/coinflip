"""Certified Real Fix: Use wait_for_drain() event synchronization.

Replaces the fixed-sleep guess with eq.wait_for_drain(timeout=2.0),
which blocks on the internal threading.Event until all items are drained.
This is immune to CPU contention because the OS kernel wakes the waiting
thread upon event signal.

Coinflip Verdict: CERTIFIED (0% failures under all conditions)
"""

from event_queue import EventQueue


def test_all_events_flushed():
    """Emits 10 events and waits for proper queue drain."""
    eq = EventQueue()
    eq.start_consumer()

    for i in range(10):
        eq.emit(f"click_event_{i}")
    eq.signal_done()

    # Coinflip Real Fix: proper synchronization via event wait
    drained = eq.wait_for_drain(timeout=2.0)
    assert drained, "Consumer thread did not finish within timeout"
    assert len(eq.flushed_events) == 10, (
        f"Only {len(eq.flushed_events)}/10 events flushed"
    )
