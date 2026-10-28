# Coinflip: Devpost Hackathon Submission Template

> **Hackathon**: Nebius & NVIDIA Nemotron AI Hackathon 2026  
> **Target Tracks**: Best Use of NVIDIA Nemotron Models on Nebius | Autonomous Coding Agents | Best Platform Feedback ($100 Prize)  
> **Authors**: Raghavendra (Product Operations Lead), Abhijith M Bhat (Lead Systems Architect), Tejas (AI Agent & Biostatistics Lead), Dhul Kifl (Benchmark Corpus Engineer)  
> **GitHub Repository**: [https://github.com/abhijithbhat/coinflip](https://github.com/abhijithbhat/coinflip)  
> **Video Demo**: [YouTube Link - 2m45s Architectural Walkthrough](https://youtu.be/coinflip-demo-2026)

---

## 1. Project Title & Tagline

- **Project Title**: **Coinflip: Statistical Flaky-Test Investigator & Flake Amplifier**
- **Tagline**: *"A single green test run is not proof — it is an uncalibrated coin toss. We turn 0% baseline flakes into 90–100% deterministic reproducers using NVIDIA Nemotron on Nebius."*

---

## 2. Devpost Elevator Pitch

Autonomous AI coding agents (Devin, Cursor, Copilot Workspace) rely on a fatally flawed heuristic: *if pytest exits 0 once, ship the PR*. But for concurrency races, unpinned seeds, and cache pollution, a test with a 90% failure probability under CI load still has a 10% chance of passing on a single quiet run. AI agents routinely ship "naive quick fixes" (enlarging `time.sleep()`, widening assertion bounds, or inserting `@pytest.mark.flaky`) that pass once on the agent's machine and immediately break production CI.

**Coinflip transforms test verification from an uncalibrated coin toss into rigorous biostatistical proof.** Using **NVIDIA Nemotron models on Nebius Token Factory** and **Nebius Sandboxes (`contree-sdk`)**, Coinflip:
1. Measures true baseline pass distributions using **95% Wilson Score Confidence Intervals**.
2. Deploys **Successive Halving Thompson Sampling** across 18 causal perturbation arms to amplify dormant flakes from **0% baseline to 90–100% deterministic reproduction**.
3. Directs **NVIDIA Nemotron-3-Super-120B** to synthesize true architectural root-cause fixes (replacing sleeps with `threading.Event`, monotonic clocks, and isolated PRNGs).
4. Enforces an **AST Static Anti-Cheat Gatekeeper** that blocks 14 test-weakening cheats before execution.
5. Verifies patches under **Dual-Condition Certification** (quiet + amplified stress) using **Wald's Sequential Probability Ratio Test (SPRT)** and the **Rule of Three ($p \le 3/N = 0.30\%$)**.
6. Signs every result with a **SHA-256 binary Merkle audit tree and server HMAC**.

---

## 3. Inspiration: Why We Built Coinflip

Every software engineer and AI agent researcher has experienced the frustration of flaky tests:
- You run `pytest` locally: **PASS (green)**.
- You push to GitHub: **FAIL (red)** in CI runner #4 under high parallel load.
- You ask an AI coding assistant to fix it: the assistant edits `time.sleep(0.025)` to `time.sleep(0.050)`, runs pytest once, sees green, and declares *"The bug has been completely resolved!"*
- Two hours later, the build breaks again.

We realized this is not an LLM hallucination problem — it is an **evaluation methodology crisis**. Flaky tests are **Bernoulli random variables ($X \sim \text{Bernoulli}(p)$)**. A single run gives exactly $N=1$ sample, with an astronomical 95% confidence interval of $[0.0\%, 97.5\%]$. You cannot evaluate non-deterministic systems with single-sample checks.

We built Coinflip to bring the mathematical rigor of clinical trial biostatistics (Fisher's exact test, Holm-Bonferroni corrections, Wilson score intervals, and Wald sequential probability ratio tests) into the automated software engineering loop.

---

## 4. What Coinflip Does (The 5-Stage Engine)

```
[Target Code & Test]
        │
        ▼
Stage 1: Baseline Quantification (N=25-30 runs -> Wilson 95% CI)
        │
        ▼
Stage 2 & 2A: Flake Amplifier (Thompson Sampling Bandit over 18 Arms)
        ├── NVIDIA Nemotron-3_5-Lightning on Nebius (AST Prior Ranking)
        └── 40-Run Out-of-Sample Confirmation (Winner's Curse Prevention)
        │
        ▼
Stage 3: Root-Cause Synthesis & Anti-Cheat
        ├── NVIDIA Nemotron-3-Super-120B on Nebius (Synchronized Patch Synthesis)
        └── AST Static Anti-Cheat Gatekeeper (14 Cheating Patterns Blocked)
        │
        ▼
Stage 4: Dual-Condition Certification (Wald's SPRT Gating Engine)
        ├── Condition A: Baseline Quiet (SPRT H0: p <= 0.01 vs H1: p >= 0.08)
        └── Condition B: Amplified Stress (SPRT H0: p <= 0.01 vs H1: p >= 0.08)
        │
        ▼
Stage 5: Cryptographic Attestation (SHA-256 Merkle Tree + Server HMAC)
        └── Certified GitHub PR Telemetry Badge & JSON Certificate
```

- **Stage 1 (Baseline Measurement)**: Runs 25–30 trials on quiet worker environments, proving that the test appears green ($p \in [0.0\%, 11.3\%]$) under quiet conditions.
- **Stage 2 & 2A (Causal Flake Amplifier)**: Uses `nvidia/Nemotron-3_5-Lightning` to inspect AST syntax trees and prioritize perturbation arms (Order Shuffling, Adversarial PRNG Seeds, Wall-Clock Skews, GIL Contention, Half-Cores, and Socket Jitter). A multi-armed bandit dynamically allocates runs, selecting the winning arm ($c^*$) and validating it with a 40-run out-of-sample confirmation batch.
- **Stage 3 (Root-Cause Synthesis)**: Feeds the causal timeline into `nvidia/nemotron-3-super-120b-a12b` via Nebius Token Factory. The model writes production-grade synchronization code.
- **Pre-Flight AST Gatekeeper**: Analyzes the Python AST of the patch before execution, rejecting any patch that deletes assertions, widens thresholds, or injects `@pytest.mark.flaky`.
- **Stage 4 (Dual-Condition Certification)**: Evaluates the patch under both quiet baseline AND the amplified stress condition using Wald's SPRT. If the patch contains a naive sleep bump, it fails within 2 runs under stress, terminating execution in $< 1.2$ seconds. If it passes all runs, the Rule of Three guarantees $p_{\text{upper}} \le 3/N = 0.30\%$.
- **Stage 5 (Cryptographic Proof)**: Hashes every run into a binary SHA-256 Merkle audit tree and generates an HMAC-signed PR badge for GitHub.

---

## 5. How We Built It & Technologies Used

- **AI Inference**: **NVIDIA Nemotron on Nebius Token Factory** (`https://api.tokenfactory.nebius.com/v1/`):
  - `nvidia/Nemotron-3_5-Lightning` for ultra-fast (< 300ms) AST hypothesis ranking.
  - `nvidia/nemotron-3-super-120b-a12b` for deep architectural root-cause patch synthesis.
- **Sandboxed Execution**: **Nebius Sandboxes (`contree-sdk==0.3.6`)** for isolated microVM container execution with zero cross-run state pollution.
- **Backend Core**: Python 3.12 / 3.14, FastAPI, async SSE streaming, multiprocessing worker pools with dynamic memory/CPU/clock perturbation hooks.
- **Statistical Mathematics**: Exact Wilson Score intervals, hypergeometric Fisher's Exact test via `math.lgamma`, Holm-Bonferroni FWER step-down corrections, Haldane relative risk ($RR \ge 1.8$), and Wald's SPRT ($A = -2.944, B = +2.944$).
- **Frontend Dashboard**: TanStack React Start, Tailwind CSS, Lucide icons, Recharts Bernoulli coin-toss visualizers, live Server-Sent Events (SSE) telemetry.
- **Deployment**: Production multi-stage Docker container (Node 22 build + Python 3.12 runtime) targeting Render, Google Cloud Run, and Hugging Face Spaces.

---

## 6. Real Benchmark Results & Empirical Proof

We evaluated Coinflip against **20 real-world flaky test archetypes** across 6 root-cause families in a paired 100-run empirical evaluation:

| Metric | Plain Reruns | Shaker Fixed Stress | Coinflip Flake Amplifier |
| :--- | :---: | :---: | :---: |
| **Overall Flake Reproduction Rate** | 20.0% (4/20) | 20.0% (4/20) | **90.0% (18/20)** |
| **Median Runs to First Failure** | 1.5 runs | 1.0 runs | **1.0 run** |
| **Median Amplification over Baseline** | 1.00x | 1.00x | **65.0x** |
| **Median Amplification over Shaker** | — | 1.00x | **65.0x** |
| **Compute Budget Allocation** | 100 identical runs | 100 fixed stress runs | 60 adaptive search + 40 confirmed |

### Key Takeaway:
Fixed stress (like academic tool Shaker) only applies CPU/memory load, completely failing to reproduce **Order-Dependent (0%)**, **Unpinned Seed (0%)**, and **Clock-Skew (0%)** flakes. Coinflip achieves **100% reproduction across all three categories**, delivering a **65.0x median amplification factor**.

---

## 7. Challenges Overcame

1. **Sub-5-Second Live Execution**: Executing 50+ real pytest subprocesses across 6 perturbation conditions took over 35 seconds initially. We optimized subprocess spawning, added 4ms burner caps, and implemented real-time SSE streaming, slashing total live run latency to **< 4.7 seconds**.
2. **Preventing AI Cheating**: Early LLM prompts frequently passed tests by deleting `assert` statements or adding `@pytest.mark.flaky(reruns=5)`. We built an AST static analyzer enforcing 14 mathematical invariants that rejects cheated code instantly.
3. **Winner's Curse in Bandit Optimization**: Choosing the best perturbation arm often introduces selection bias. We solved this by enforcing an independent 40-run out-of-sample confirmation batch with fresh seed salts before declaring amplification success.

---

## 8. What's Next for Coinflip

- **GitHub Actions Marketplace**: Release `uses: abhijithbhat/coinflip-gate@v1` to automatically gate pull requests across public open-source repositories.
- **Language Support Expansion**: Extend perturbation harnesses to Go (`-race`) and Rust (`tokio` async task scheduling).
- **IDE Native Extension**: Publish our Model Context Protocol (MCP) tool to Cursor, Claude Desktop, and VS Code for one-click root-cause verification inside the editor.

---

## 9. Team Members & Contributions

- **Abhijith M Bhat** (Lead Systems & Sandbox Engine Architect): Built the perturbation harness, Merkle attestation tree, HMAC verification, and Wald SPRT engine.
- **Tejas** (AI Agent, Biostatistics & Frontend Lead): Integrated Nebius Token Factory with Nemotron models, authored exact statistical engines, and designed the TanStack dashboard.
- **Dhul Kifl** (Benchmark Corpus Engineer): Curated 20 real-world flaky test archetypes and validated the AST anti-cheat gatekeeper.
- **Raghavendra** (Product Operations, Platform Feedback, Devpost & Video Producer): Authored the comprehensive Nebius platform feedback report, managed project operations, and scripted the demonstration video.
