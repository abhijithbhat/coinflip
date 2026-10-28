# Coinflip Video Demonstration Script

> **Title**: Coinflip — Statistical Flaky-Test Investigator & Amplifier  
> **Duration**: 2 minutes 45 seconds (0:00 – 2:45)  
> **Target Platforms**: YouTube (1080p60 / 4K) & Devpost Project Page  
> **Narrator / Producer**: Raghavendra (Product Operations Lead)  
> **Technical Oversight**: Abhijith M Bhat & Tejas  
> **Key Required Mentions**: *"Nebius Token Factory"*, *"Nebius Sandboxes"*, *"NVIDIA Nemotron"*

---

## Storyboard Overview & Timing Map

| Scene | Timestamp | Duration | Scene Title & Core Focus |
| :---: | :---: | :---: | :--- |
| **1** | `0:00 – 0:30` | 30s | **The Flaky Test Delusion**: Why single green runs deceive AI coding agents. |
| **2** | `0:30 – 1:00` | 30s | **Stage 1 & Stage 2A**: Thompson Sampling Flake Amplification powered by Nemotron-3_5-Lightning. |
| **3** | `1:00 – 1:35` | 35s | **Stage 3**: Nemotron-3-Super-120B Root-Cause Patch Synthesis & AST Anti-Cheat Gatekeeper. |
| **4** | `1:35 – 2:15` | 40s | **Stage 4**: Dual-Condition Certification & Wald's SPRT Early-Stop Sequential Analysis. |
| **5** | `2:15 – 2:45` | 30s | **Stage 5 & Conclusion**: Cryptographic Merkle Tree Attestation & GitHub PR Verification Badge. |

---

## Detailed Word-for-Word Production Script

### Scene 1: The Flaky Test Delusion (0:00 – 0:30)

**[VISUAL CUES]**
- `0:00 – 0:08`: Screen recording of an AI coding agent (Cursor/Devin) generating a patch. Camera zooms in on code where `time.sleep(0.025)` is arbitrarily changed to `time.sleep(0.050)`.
- `0:08 – 0:16`: Terminal opens. Agent runs `pytest test_worker.py`. A single green line appears: `1 passed in 0.04s`. Agent outputs: *"Test passed successfully! Opening pull request."*
- `0:16 – 0:30`: Cut to GitHub Actions CI dashboard. Runner #4 displays a bright red failure: `AssertionError: worker thread timed out!`. Animated split screen shows a coin flipping in slow motion landing on tails.

**[SPOKEN VOICEOVER]**
> *"In modern software engineering, autonomous AI coding agents rely on a dangerously flawed heuristic: run pytest once, see exit code zero, and ship the pull request.*  
>  
> *But flaky tests are not boolean states — they are Bernoulli random variables. A test with a ninety percent failure rate under production load still has a ten percent chance of passing on any single quiet run. AI agents routinely ship naive sleep bumps that pass once on their laptop, and immediately break production CI.*  
>  
> *A single green run is not proof. It is an uncalibrated coin toss. Meet Coinflip."*

---

### Scene 2: Stage 1 & Stage 2A Flake Amplifier (0:30 – 1:00)

**[VISUAL CUES]**
- `0:30 – 0:38`: Cut to the Coinflip Web Dashboard (`https://coinflip-2bcw.onrender.com`). Clean, dark porcelain-signal interface. Case selector dropdown highlights **"Hero Worker CPU Race"**.
- `0:38 – 0:45`: Baseline dot matrix displays 30 green circles. Telemetry card shows: `Failures: 0/30 (0.0%), Wilson 95% CI: [0.0%, 11.3%]`.
- `0:45 – 1:00`: Cursor clicks **"Run Live"**. Real-time SSE streaming indicator pulses. An AST hypothesis card expands showing `nvidia/Nemotron-3_5-Lightning` on **Nebius Token Factory** evaluating AST tokens and ranking `cpu_heavy_load` #1. The bandit executes across 18 perturbation arms. Below, the dot matrix transforms into bright crimson red: 27 fails out of 30 runs (`Fail Rate: 90.0%`).

**[SPOKEN VOICEOVER]**
> *"Coinflip transforms flaky test investigation into clinical-trial biostatistics.*  
>  
> *In Stage One, Coinflip runs the test across quiet worker pools. The baseline passes thirty out of thirty times. A naive agent would assume the code is flawless.*  
>  
> *In Stage Two-A, our Flake Amplifier takes over. Calling **NVIDIA Nemotron-3_5-Lightning** via **Nebius Token Factory**, Coinflip analyzes Python AST syntax trees to predict causal failure hypotheses in under three hundred milliseconds. Then, our Successive Halving Thompson Sampling bandit stresses the code across eighteen perturbation regimes. Under CPU thread contention, the failure rate spikes from zero percent to ninety percent. We have forced a dormant ghost into a deterministic reproducer."*

---

### Scene 3: Root-Cause Patch Synthesis & Anti-Cheat Gatekeeper (1:00 – 1:35)

**[VISUAL CUES]**
- `1:00 – 1:12`: Dashboard scrolls to Stage 3. A diff inspector displays a "Naive AI Quick Fix" trying to insert `@pytest.mark.flaky(reruns=5)` and delete assertions. A red warning banner flashes: **`[AST ANTI-CHEAT GATEKEEPER: REJECTED - Deleted Assertions & Flaky Decorator Detected]`**.
- `1:12 – 1:25`: Model reasoning trace box unfolds. The camera highlights **`nvidia/nemotron-3-super-120b-a12b`** running on **Nebius Token Factory**. The model analyzes the thread race timeline.
- `1:25 – 1:35`: A clean, certified patch appears: replacing the flawed sleep with a deterministic `threading.Event` synchronization lock and `worker.wait_for_completion()`. Nebius microVM sandbox status badge illuminates: **`[Nebius contree-sdk MicroVM: Clean Sandbox Environment Active]`**.

**[SPOKEN VOICEOVER]**
> *"Now Stage Three synthesizes the fix. But first, Coinflip enforces an AST Static Anti-Cheat Gatekeeper. AI agents frequently cheat by deleting assertions, widening tolerances, or adding flaky decorators. Our AST gatekeeper blocks fourteen separate cheating tricks before execution.*  
>  
> *To fix the root cause, Coinflip queries **NVIDIA Nemotron-3-Super-120B** on **Nebius Token Factory**. Leveraging its hundred-and-twenty billion parameter reasoning capacity, Nemotron identifies that the worker thread races against Python's global interpreter lock. Instead of a fragile sleep, Nemotron rewrites the concurrency primitive using a deterministic threading event barrier, executed inside disposable **Nebius Sandboxes** via the contree-sdk."*

---

### Scene 4: Dual-Condition Certification & Wald's SPRT (1:35 – 2:15)

**[VISUAL CUES]**
- `1:35 – 1:48`: Dashboard transitions to Stage 4: **Dual-Condition Certification**. Split comparison panel: Left side tests the Naive Fix under stress; Right side tests the Nemotron Certified Fix.
- `1:48 – 2:02`: Under stress, the Naive Fix fails on Run #2. Wald's SPRT ledger updates in real-time: log-likelihood ratio $\Lambda_m$ crosses $+2.94$, triggering an early-stop abort in **1.1 seconds**: **`[SPRT REJECTED: H1 Confirmed Defective]`**.
- `2:02 – 2:15`: On the right, the Nemotron Certified Fix completes 50 out of 50 runs cleanly. The interactive Streak Curve demonstrates the **Rule of Three ($p \le 3/N = 0.30\%$)**. Both Condition A and Condition B are verified green.

**[SPOKEN VOICEOVER]**
> *"Stage Four is where Coinflip delivers mathematical proof: Dual-Condition Certification.*  
>  
> *A patch must pass not only on quiet machines, but under the exact amplified stress condition that broke the original code.*  
>  
> *Watch what happens to the naive fix: under stress, it fails on run two. Wald's Sequential Probability Ratio Test detects the defect instantly and terminates the run in just over one second — saving ninety percent of CI compute.*  
>  
> *Meanwhile, Nemotron's certified fix completes fifty consecutive stress runs without a single failure. By the mathematical Rule of Three, the one-sided upper bound drops to zero-point-three percent."*

---

### Scene 5: Cryptographic Attestation & Conclusion (2:15 – 2:45)

**[VISUAL CUES]**
- `2:15 – 2:25`: Stage 5 card expands. An interactive binary SHA-256 Merkle tree animates from leaf nodes (run results) up to the root hash: `3042456f...`. An HMAC-SHA256 signature seal is applied.
- `2:25 – 2:35`: Camera cuts to a terminal window. The engineer types:  
  `python -m sandbox_engine.attestation --verify shared_contracts/recorded_traces/hero.json`.  
  Instant green output: **`[PASS] Merkle Root & HMAC Attestation Verified`**. Cursor copies the GitHub Markdown badge into a PR.
- `2:35 – 2:45`: Final title slide appears with the emerald Coinflip coin logo, live cloud demo (`coinflip-2bcw.onrender.com`), repository link (`github.com/abhijithbhat/coinflip`), and hackathon credits for Nebius, NVIDIA Nemotron, and the engineering team.

**[SPOKEN VOICEOVER]**
> *"Finally, Stage Five hashes every execution artifact into a binary SHA-256 Merkle audit tree, sealed with an HMAC signature. Any engineer, auditor, or CI bot can cryptographically verify that the test was genuinely stressed and genuinely fixed.*  
>  
> *Powered by **NVIDIA Nemotron** on **Nebius Token Factory** and **Nebius Sandboxes**, Coinflip ends the era of uncalibrated coin tosses in automated software engineering.*  
>  
> *Don't guess. Measure, perturb, and verify. Thank you."*

---

## Technical Recording & Production Guidelines

1. **Resolution & Audio**:
   - Screen capture at 1920x1080 (60 fps), UI zoomed to 110% in Chrome for crystal-clear dot-matrix visibility.
   - Professional USB condenser microphone with noise-suppression and subtle background ambient electronic synth track (lowered to -18dB during voiceover).
2. **Timing Adherence**:
   - Keep Scene 2 (live run) snappy: click "Run Live" right at 0:45 so the SSE stream completes smoothly before the 1:00 transition.
   - Ensure the spoken words *"Nebius Token Factory"*, *"NVIDIA Nemotron"*, and *"Nebius Sandboxes"* are enunciated with clear, deliberate cadence.

