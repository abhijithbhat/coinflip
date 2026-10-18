# conftest.py — Ensures the benchmark directory is on sys.path so that
# `from worker_service import BackgroundWorker` resolves correctly when
# pytest runs test_worker.py from an isolated temporary workspace.

import sys
from pathlib import Path

# Add the benchmark directory itself to sys.path
benchmark_dir = Path(__file__).resolve().parent
if str(benchmark_dir) not in sys.path:
    sys.path.insert(0, str(benchmark_dir))
