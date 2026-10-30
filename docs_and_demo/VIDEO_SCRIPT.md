# Coinflip Video Demonstration Script

> **Title**: Coinflip — Statistical Flaky-Test Investigator & Flake Amplifier  
> **Target Duration**: ~2 minutes 15 seconds (Safely under 3 minutes)  
> **Word Count**: 287 words (Calibrated for ~130 WPM TTS pacing)  
> **Format**: Screen Recording + ElevenLabs AI Voiceover  
> **Platforms**: YouTube (1080p60) & Devpost Hackathon Submission  
> **Live Demo URL**: https://coinflip-nvidia.onrender.com/  
> **Key Required Mentions**: *"Nebius Token Factory"*, *"Nebius Sandboxes"*, *"NVIDIA Nemotron"*

---

## ⏱️ Scene Timing & Word Count Calibration

| Scene | Target Timestamp | Target Duration | Word Count | Focus |
| :---: | :---: | :---: | :---: | :--- |
| **1** | `0:00 – 0:24` | 24s | 54 words | The Flaky Test Delusion & Bernoulli Flake Concept |
| **2** | `0:24 – 0:52` | 28s | 64 words | Stage 1 Quiet Baseline & Stage 2A Flake Amplifier |
| **3** | `0:52 – 1:17` | 25s | 57 words | AST Anti-Cheat Gatekeeper & Nemotron-3-Super-120B |
| **4** | `1:17 – 1:45` | 28s | 64 words | Dual-Condition Certification & Wald's SPRT Early-Stop |
| **5** | `1:45 – 2:10` | 25s | 48 words | Cryptographic Merkle/HMAC Attestation & Conclusion |
| **Total** | `0:00 – 2:10` | **2m 10s** | **287 words** | **Guaranteed under 2m 30s** |

---

## 🎙️ ElevenLabs Pacing & Voice Settings

1. **Voice Settings in ElevenLabs**:
   - Voice: **"Adam"** or **"Brian"**
   - **Speed Slider**: If your ElevenLabs interface has the Speed slider, set it to **`1.05x`** or **`1.10x`** for an energetic tech-keynote cadence.
   - **Stability**: `50%`
   - **Clarity + Similarity**: `75%`
2. **Copying Tips**:
   - Copy only the clean text inside the quote block for each scene.
   - All acronyms and numbers are written phonetically (e.g., "A-S-T", "H-MACK", "zero point three percent").

---

## 🎬 Compact Scene-by-Scene Script

### Scene 1: The Flaky Test Delusion (0:00 – 0:24 · 24s · 54 words)
**[Visual Actions]**
- `0:00 – 0:10`: Show code editor where an AI agent replaces `time.sleep(0.025)` with `time.sleep(0.050)`.
- `0:10 – 0:17`: Terminal shows green `pytest` passing (`1 passed in 0.04s`).
- `0:17 – 0:24`: Show CI terminal failure: `AssertionError: worker thread timed out!`.

**[ElevenLabs Voiceover Text]**
> Autonomous AI coding agents rely on a dangerous heuristic: run pytest once, see green, and ship the pull request. But flaky tests are not boolean: they are Bernoulli random variables. A naive sleep fix passes once on a quiet laptop, then breaks production CI. A single green run is an uncalibrated coin toss. Meet Coinflip.

---

### Scene 2: The Dot Matrix & Flake Amplifier (0:24 – 0:52 · 28s · 64 words)
**[Visual Actions]**
- `0:24 – 0:34`: Open live site `https://coinflip-nvidia.onrender.com/`. Hover over **The Coin-Toss Dot Matrix**. Show Quiet Baseline (`7.0% 21/300 FAILED`) vs Heavy CPU Contention (`92.5% 37/40 FAILED`).
- `0:34 – 0:52`: Scroll to **Stage 2A Flake Amplifier**. Highlight `nvidia/Nemotron-3_5-Lightning` on **Nebius Token Factory** and the 13.6x amplification factor.

**[ElevenLabs Voiceover Text]**
> Coinflip brings biostatistics to test investigation. In Stage One, our quiet baseline fails only seven percent of the time, easily fooling naive agents. In Stage Two-A, our Flake Amplifier queries NVIDIA Nemotron-3.5-Lightning on Nebius Token Factory to predict causal failure hypotheses. Our bandit stresses the code, spiking failures to over ninety percent under CPU contention. We turn dormant flakes into deterministic reproducers.

---

### Scene 3: AST Anti-Cheat Gatekeeper & Nemotron Patch (0:52 – 1:17 · 25s · 57 words)
**[Visual Actions]**
- `0:52 – 1:04`: Scroll to **Stage 4 Comparison Arena**. Show **Attempt 1: Naive Quick Fix** rejected by the **AST Anti-Cheat Gatekeeper**.
- `1:04 – 1:17`: Show **Attempt 2: Coinflip Certified Fix** with badge **LIVE NEMOTRON PATCH**, powered by **`nvidia/nemotron-3-super-120b-a12b`** on **Nebius Token Factory**, running in **Nebius Sandboxes**.

**[ElevenLabs Voiceover Text]**
> Before repairing the test, our A-S-T Anti-Cheat Gatekeeper blocks fourteen cheating tricks, like deleting assertions or adding flaky decorators. To fix the real root cause, Coinflip queries NVIDIA Nemotron-3-Super-120B on Nebius Token Factory. Nemotron identifies the underlying thread race and synthesizes a deterministic threading event barrier, verified cleanly inside isolated Nebius Sandboxes.

---

### Scene 4: Dual-Condition Certification & Wald's SPRT (1:17 – 1:45 · 28s · 64 words)
**[Visual Actions]**
- `1:17 – 1:30`: In Comparison Arena, contrast Attempt 1 (fails under stress) vs Attempt 2 (0/1,000 quiet and 0/1,000 stress).
- `1:30 – 1:45`: Hover over Attempt 1's badge **SPRT EARLY-STOP (SAVED 82 RUNS)**, then point to the **Streak Curve** upper bound `< 0.30%`.

**[ElevenLabs Voiceover Text]**
> Stage Four delivers Dual-Condition Certification. A valid fix must pass both quiet and amplified stress conditions. Notice the naive fix: it passes on a quiet machine, but fails under stress. Wald's Sequential Probability Ratio Test rejects it in eighteen runs, saving eighty percent of compute. Meanwhile, Nemotron's fix passes one thousand stress runs, certifying an upper bound under zero point three percent.

---

### Scene 5: Cryptographic Attestation & Conclusion (1:45 – 2:10 · 25s · 48 words)
**[Visual Actions]**
- `1:45 – 1:55`: In **Stage 5**, click **"Verify Cryptographic Signature"**. Show the green confirmation check.
- `1:55 – 2:05`: Click top-right **"Run Live Mini-Batch (~5-7s)"** to show sub-3-second live execution.
- `2:05 – 2:10`: Show final screen with Coinflip header, live Render URL, and GitHub repository.

**[ElevenLabs Voiceover Text]**
> Finally, Stage Five seals every artifact into a SHA-256 Merkle tree with an H-MACK signature. With one click, engineers can cryptographically verify the certificate. Powered by NVIDIA Nemotron on Nebius Token Factory and Nebius Sandboxes, Coinflip ends uncalibrated coin tosses. Don't guess. Measure, perturb, and verify.


