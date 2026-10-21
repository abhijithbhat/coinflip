import sys
from pathlib import Path

benchmark_dir = Path(__file__).resolve().parent
if str(benchmark_dir) not in sys.path:
    sys.path.insert(0, str(benchmark_dir))
