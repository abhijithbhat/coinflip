# Coinflip Benchmark Report

**Generated**: 2026-10-18 15:30 UTC  
**Runs per condition**: 50  
**Total execution time**: 171s  
**Backend**: `local_isolated`  
**Confidence intervals**: 95% Wilson score

## Summary: Perturbation Spike Detection

| # | Suite | Category | Trigger | Baseline Fail% | Trigger Fail% | Spike? |
|---|-------|----------|---------|----------------|---------------|--------|
| 1 | Hero Worker Race (CPU Thread Race) | Concurrency / Thread Race | `cpu_heavy_load` | 0.0% | 100.0% | YES |
| 2 | Test Order Pollution (Shared Cache) | Order-Dependent (IDoFT: OD) | `shuffle_order` | 0.0% | 46.0% | YES |
| 3 | Unpinned Seed Sampling (Hash + Random) | Non-Deterministic (IDoFT: ND) | `seed_change` | 0.0% | 48.0% | YES |
| 4 | Token Expiry Clock (Mixed Clock Sources) | Time-Dependent (clock-sensitive) | `clock_shift` | 0.0% | 100.0% | YES |
| 5 | Async Queue Race (Producer-Consumer) | Async Wait / Concurrency | `cpu_heavy_load` | 0.0% | 100.0% | YES |

> **Overall Verdict**: ALL SPIKES CONFIRMED

---

## Detailed Results by Suite

### 1. Hero Worker Race (CPU Thread Race)

- **Category**: Concurrency / Thread Race
- **Trigger perturbation**: `cpu_heavy_load`
- **Suite time**: 31.8s

| Condition | Runs | Failures | Fail% | 95% CI | Note |
|-----------|------|----------|-------|--------|------|
| `baseline` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
| `shuffle_order` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
| `seed_change` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
| `clock_shift` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
| `cpu_half_cores` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
| `cpu_heavy_load` <-- | 50 | 50 | 100.0% | [92.9%, 100.0%] | **TRIGGER** |

**Trigger dot-matrix** (`cpu_heavy_load`):
```
XXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXX
```
`. = pass, X = fail`

### 2. Test Order Pollution (Shared Cache)

- **Category**: Order-Dependent (IDoFT: OD)
- **Trigger perturbation**: `shuffle_order`
- **Suite time**: 36.5s

| Condition | Runs | Failures | Fail% | 95% CI | Note |
|-----------|------|----------|-------|--------|------|
| `baseline` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
| `shuffle_order` <-- | 50 | 23 | 46.0% | [33.0%, 59.6%] | **TRIGGER** |
| `seed_change` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
| `clock_shift` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
| `cpu_half_cores` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
| `cpu_heavy_load` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |

**Trigger dot-matrix** (`shuffle_order`):
```
.X.X.......XXXX...X.X.X..
XXXXXXXX.X.X...XX....X..X
```
`. = pass, X = fail`

### 3. Unpinned Seed Sampling (Hash + Random)

- **Category**: Non-Deterministic (IDoFT: ND)
- **Trigger perturbation**: `seed_change`
- **Suite time**: 28.9s

| Condition | Runs | Failures | Fail% | 95% CI | Note |
|-----------|------|----------|-------|--------|------|
| `baseline` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
| `shuffle_order` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
| `seed_change` <-- | 50 | 24 | 48.0% | [34.8%, 61.5%] | **TRIGGER** |
| `clock_shift` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
| `cpu_half_cores` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
| `cpu_heavy_load` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |

**Trigger dot-matrix** (`seed_change`):
```
.XXXX..X..X..X..X.XX.XX.X
X.XX.XX..X.XX..X.......XX
```
`. = pass, X = fail`

### 4. Token Expiry Clock (Mixed Clock Sources)

- **Category**: Time-Dependent (clock-sensitive)
- **Trigger perturbation**: `clock_shift`
- **Suite time**: 41.0s

| Condition | Runs | Failures | Fail% | 95% CI | Note |
|-----------|------|----------|-------|--------|------|
| `baseline` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
| `shuffle_order` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
| `seed_change` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
| `clock_shift` <-- | 50 | 50 | 100.0% | [92.9%, 100.0%] | **TRIGGER** |
| `cpu_half_cores` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
| `cpu_heavy_load` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |

**Trigger dot-matrix** (`clock_shift`):
```
XXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXX
```
`. = pass, X = fail`

### 5. Async Queue Race (Producer-Consumer)

- **Category**: Async Wait / Concurrency
- **Trigger perturbation**: `cpu_heavy_load`
- **Suite time**: 32.8s

| Condition | Runs | Failures | Fail% | 95% CI | Note |
|-----------|------|----------|-------|--------|------|
| `baseline` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
| `shuffle_order` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
| `seed_change` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
| `clock_shift` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
| `cpu_half_cores` | 50 | 0 | 0.0% | [0.0%, 7.1%] |  |
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
