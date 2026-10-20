# Coinflip Benchmark Report

**Generated**: 2026-10-20 03:38 UTC  
**Runs per condition**: 50  
**Total execution time**: 92s  
**Backend**: `local_isolated`  
**Confidence intervals**: 95% Wilson score

## Summary: Perturbation Spike Detection

| # | Suite | Category | Trigger | Baseline Fail% | Trigger Fail% | Spike? |
|---|-------|----------|---------|----------------|---------------|--------|
| 1 | Hero Worker Race (CPU Thread Race) | Concurrency / Thread Race | `cpu_heavy_load` | 10.0% | 98.0% | YES |
| 2 | Test Order Pollution (Shared Cache) | Order-Dependent (IDoFT: OD) | `shuffle_order` | 18.0% | 78.0% | YES |
| 3 | Unpinned Seed Sampling (Hash + Random) | Non-Deterministic (IDoFT: ND) | `seed_change` | 18.0% | 70.0% | YES |
| 4 | Token Expiry Clock (Mixed Clock Sources) | Time-Dependent (clock-sensitive) | `clock_shift` | 12.0% | 100.0% | YES |
| 5 | Async Queue Race (Producer-Consumer) | Async Wait / Concurrency | `cpu_heavy_load` | 10.0% | 100.0% | YES |

> **Overall Verdict**: ALL SPIKES CONFIRMED

---

## Detailed Results by Suite

### 1. Hero Worker Race (CPU Thread Race)

- **Category**: Concurrency / Thread Race
- **Trigger perturbation**: `cpu_heavy_load`
- **Suite time**: 17.5s

| Condition | Runs | Failures | Fail% | 95% CI | Note |
|-----------|------|----------|-------|--------|------|
| `baseline` | 50 | 5 | 10.0% | [4.3%, 21.4%] |  |
| `shuffle_order` | 50 | 5 | 10.0% | [4.3%, 21.4%] |  |
| `seed_change` | 50 | 5 | 10.0% | [4.3%, 21.4%] |  |
| `clock_shift` | 50 | 8 | 16.0% | [8.3%, 28.5%] |  |
| `cpu_half_cores` | 50 | 5 | 10.0% | [4.3%, 21.4%] |  |
| `cpu_heavy_load` <-- | 50 | 49 | 98.0% | [89.5%, 99.7%] | **TRIGGER** |

**Trigger dot-matrix** (`cpu_heavy_load`):
```
XXXXXXXXX.XXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXX
```
`. = pass, X = fail`

### 2. Test Order Pollution (Shared Cache)

- **Category**: Order-Dependent (IDoFT: OD)
- **Trigger perturbation**: `shuffle_order`
- **Suite time**: 17.8s

| Condition | Runs | Failures | Fail% | 95% CI | Note |
|-----------|------|----------|-------|--------|------|
| `baseline` | 50 | 9 | 18.0% | [9.8%, 30.8%] |  |
| `shuffle_order` <-- | 50 | 39 | 78.0% | [64.8%, 87.2%] | **TRIGGER** |
| `seed_change` | 50 | 5 | 10.0% | [4.3%, 21.4%] |  |
| `clock_shift` | 50 | 9 | 18.0% | [9.8%, 30.8%] |  |
| `cpu_half_cores` | 50 | 5 | 10.0% | [4.3%, 21.4%] |  |
| `cpu_heavy_load` | 50 | 3 | 6.0% | [2.1%, 16.2%] |  |

**Trigger dot-matrix** (`shuffle_order`):
```
.X.XXX.XXX.XXXXXX.X.X.XX.
XXXXXXXX.XXXXXXXXXXX.X.XX
```
`. = pass, X = fail`

### 3. Unpinned Seed Sampling (Hash + Random)

- **Category**: Non-Deterministic (IDoFT: ND)
- **Trigger perturbation**: `seed_change`
- **Suite time**: 17.0s

| Condition | Runs | Failures | Fail% | 95% CI | Note |
|-----------|------|----------|-------|--------|------|
| `baseline` | 50 | 9 | 18.0% | [9.8%, 30.8%] |  |
| `shuffle_order` | 50 | 5 | 10.0% | [4.3%, 21.4%] |  |
| `seed_change` <-- | 50 | 35 | 70.0% | [56.2%, 80.9%] | **TRIGGER** |
| `clock_shift` | 50 | 7 | 14.0% | [7.0%, 26.2%] |  |
| `cpu_half_cores` | 50 | 4 | 8.0% | [3.1%, 18.8%] |  |
| `cpu_heavy_load` | 50 | 7 | 14.0% | [7.0%, 26.2%] |  |

**Trigger dot-matrix** (`seed_change`):
```
X.XX.XX.XXX.XX.XX.XXX.XX.
XX.XXX.XX.XX.XXX.XX.XX.XX
```
`. = pass, X = fail`

### 4. Token Expiry Clock (Mixed Clock Sources)

- **Category**: Time-Dependent (clock-sensitive)
- **Trigger perturbation**: `clock_shift`
- **Suite time**: 21.0s

| Condition | Runs | Failures | Fail% | 95% CI | Note |
|-----------|------|----------|-------|--------|------|
| `baseline` | 50 | 6 | 12.0% | [5.6%, 23.8%] |  |
| `shuffle_order` | 50 | 5 | 10.0% | [4.3%, 21.4%] |  |
| `seed_change` | 50 | 5 | 10.0% | [4.3%, 21.4%] |  |
| `clock_shift` <-- | 50 | 50 | 100.0% | [92.9%, 100.0%] | **TRIGGER** |
| `cpu_half_cores` | 50 | 3 | 6.0% | [2.1%, 16.2%] |  |
| `cpu_heavy_load` | 50 | 5 | 10.0% | [4.3%, 21.4%] |  |

**Trigger dot-matrix** (`clock_shift`):
```
XXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXX
```
`. = pass, X = fail`

### 5. Async Queue Race (Producer-Consumer)

- **Category**: Async Wait / Concurrency
- **Trigger perturbation**: `cpu_heavy_load`
- **Suite time**: 18.5s

| Condition | Runs | Failures | Fail% | 95% CI | Note |
|-----------|------|----------|-------|--------|------|
| `baseline` | 50 | 5 | 10.0% | [4.3%, 21.4%] |  |
| `shuffle_order` | 50 | 5 | 10.0% | [4.3%, 21.4%] |  |
| `seed_change` | 50 | 5 | 10.0% | [4.3%, 21.4%] |  |
| `clock_shift` | 50 | 2 | 4.0% | [1.1%, 13.5%] |  |
| `cpu_half_cores` | 50 | 3 | 6.0% | [2.1%, 16.2%] |  |
| `cpu_heavy_load` <-- | 50 | 50 | 100.0% | [92.9%, 100.0%] | **TRIGGER** |

**Trigger dot-matrix** (`cpu_heavy_load`):
```
XXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXX
```
`. = pass, X = fail`

---

## Patch Comparison: Naive AI Quick Fix vs. Coinflip Root-Cause Fix

| Suite | Root Cause | Naive AI Quick Fix (REJECTED) | Naive Fail% | Coinflip Root-Cause Fix (CERTIFIED) | Certified Fail% |
|---|---|---|---|---|---|
| **Hero Worker Race** | `time.sleep(0.025)` races against SHA-256 worker thread | Bump sleep to 0.050s -- still races under CPU load | `>70.0%` | `worker.wait_for_completion()` via `threading.Event` | `0.0%` |
| **Order Pollution** | Module-level `_rate_config_cache` persists across tests | Inline `cache.clear()` in one test -- doesn't protect new tests | `50.0%` | Autouse pytest fixture with `reset_config()` -- order-immune | `0.0%` |
| **Unpinned Seed** | `hash()` + module `random` correlated under `seed_change` | Widen threshold from 75 to 45 -- tail seeds still fail | `12.0%` | Local `Random(42)` + remove hash dependency -- deterministic | `0.0%` |
| **Token Expiry** | `time.time()` patched but `os.path.getmtime()` is not | Bump TTL to 4000s -- fragile to larger shifts | `100.0%` | `time.monotonic()` for age tracking -- shift-immune | `0.0%` |
| **Queue Race** | Fixed `sleep(0.020)` races against CPU-starved consumer | Bump sleep to 0.200s -- still races >25% under load | `>35.0%` | `wait_for_drain()` via `thread.join()` -- load-immune | `0.0%` |

---

## Methodology

- **Engine**: sandbox_engine perturbation contexts + Wilson CI math
- **Perturbations**: 6 conditions x N runs each (baseline, shuffle_order, seed_change, clock_shift, cpu_half_cores, cpu_heavy_load)
- **Confidence intervals**: 95% two-sided Wilson score intervals
- **Spike criterion**: Trigger failure rate > baseline + 5%, OR trigger failures > 0 when baseline = 0%
- **Isolation**: Each run executes in a fresh tempfile copy of the benchmark directory

## Perturbation Key

| Condition | What it does |
|-----------|-------------|
| `baseline` | Normal quiet execution (control group) |
| `shuffle_order` | Randomizes pytest test execution order |
| `seed_change` | Varies `PYTHONHASHSEED` and `random.seed()` across runs |
| `clock_shift` | Monkey-patches `time.time()` forward by +3600 seconds |
| `cpu_half_cores` | Restricts CPU affinity and thread counts |
| `cpu_heavy_load` | Spawns background CPU-burning processes |
