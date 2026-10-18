"""Flaky test: Async event queue race condition.

This test emits 10 events to a producer-consumer queue, then checks
that all events were flushed after a fixed sleep. Under quiet conditions
the consumer drains the queue fast enough. Under cpu_heavy_load, the
consumer thread is starved for CPU cycles, failing to drain in time.

Expected behavior across Coinflip's 7 perturbation conditions:
  - baseline:        ~5-15% failure (tight race, depends on OS scheduler)
  - shuffle_order:   ~5-15% failure (order doesn't affect this race)
  - seed_change:     ~5-15% failure (seeds don't affect this race)
  - clock_shift:     ~5-15% failure (clock doesn't affect thread scheduling)
  - network_cut:     ~5-15% failure (no network in this test)
  - cpu_half_cores:  Elevated (~20-40%)
  - cpu_heavy_load:  >70% failure — THIS IS THE TRIGGERING CONDITION
"""

import time

from event_queue import EventQueue


def test_all_events_flushed():
    """Emits 10 events and asserts all are flushed after a fixed sleep.

    BUG: Uses time.sleep(0.020) to wait for the consumer to process
    10 events. Each event takes ~1ms (SHA-256 + sleep), so 10 events
    take ~10-15ms on a quiet machine. The 20ms sleep is barely enough.

    Under cpu_heavy_load, the consumer's per-event time.sleep(0.001)
    gets rounded up to ~15ms on Windows (or delayed by GIL contention
    on Linux), making 10 events take 50-200ms+. The 20ms sleep is
    far too short.
    """
    eq = EventQueue()
    eq.start_consumer()

    for i in range(10):
        eq.emit(f"click_event_{i}")
    eq.signal_done()

    # Flawed pattern: fixed arbitrary sleep
    time.sleep(0.020)

    assert len(eq.flushed_events) == 10, (
        f"Only {len(eq.flushed_events)}/10 events flushed — "
        f"consumer thread likely starved for CPU"
    )
