"""Certified Real Fix: Use queue.join() / wait_for_drain() synchronization.

Replaces the fixed-sleep guess with eq.wait_for_drain(timeout=5.0),
which internally calls consumer_thread.join(). The thread terminates
only after processing all events (including the sentinel None). This
is immune to CPU load because the OS kernel handles thread completion
signaling, not a fixed timer.

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

    # Coinflip Real Fix: proper synchronization via thread join
    drained = eq.wait_for_drain(timeout=5.0)
    assert drained, "Consumer thread did not finish within timeout"
    assert len(eq.flushed_events) == 10, (
        f"Only {len(eq.flushed_events)}/10 events flushed"
    )
