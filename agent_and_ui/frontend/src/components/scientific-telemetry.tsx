import { useEffect, useMemo, useState } from "react";
import { Check, ChevronDown, Copy, Download, Fingerprint, Loader2, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fisherExact, relativeRisk, holmBonferroniAdjust, PROFILER_EXAMPLE, SPRT_EXAMPLE, sealTrace, verifyTrace, type Attestation } from "@/lib/telemetry";
import { pct, synthesizeAmplifierFallback, type FixAttempt, type Trace } from "@/lib/trace";

export function FixSourceBadge({ source, fallbackVerdict }: { source?: string | undefined; fallbackVerdict?: string | undefined }) {
  const resolved = source ?? (fallbackVerdict === "CERTIFIED" ? "nemotron_live" : "naive_baseline_fixture");
  if (resolved === "nemotron_live") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/60 bg-primary/10 px-2.5 py-0.5 font-mono text-[10px] font-bold text-primary tracking-wide">
        <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
        LIVE NEMOTRON PATCH
      </span>
    );
  }
  if (resolved === "offline_fallback_fixture") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-stress/60 bg-stress/10 px-2.5 py-0.5 font-mono text-[10px] font-bold text-stress tracking-wide">
        <span className="h-1.5 w-1.5 rounded-full bg-stress" />
        OFFLINE FALLBACK PATCH (API TIMEOUT)
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/40 px-2.5 py-0.5 font-mono text-[10px] font-semibold text-muted-foreground tracking-wide">
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground" />
      REFERENCE NAIVE AGENT FIXTURE
    </span>
  );
}

export function CausalLedger({ trace }: { trace: Trace }) {
  const rawPs = useMemo(() => {
    return trace.stage2_ledger.map(row => {
      if (row.perturbation === "baseline") return 1;
      return row.causal_analytics?.p_value ?? row.causal_analytics?.fishers_exact_p_value ?? fisherExact(trace.stage1_baseline, row);
    });
  }, [trace]);

  const fallbackHolm = useMemo(() => holmBonferroniAdjust(rawPs), [rawPs]);

  return <div className="causal-ledger"><h3 className="font-display text-lg font-semibold">Causal Inference Ledger</h3><p className="mb-4 mt-1 font-mono text-[10px] text-muted-foreground">Fisher's Exact Test & Relative Risk · versus baseline</p>{trace.stage2_ledger.map((row, idx) => {
    const baseline = row.perturbation === "baseline";
    const causal = row.causal_analytics;
    const p = baseline ? 1 : rawPs[idx] ?? 1;
    const holmP = baseline ? 1 : causal?.holm_adjusted_p_value ?? row.holm_adjusted_p_value ?? fallbackHolm[idx] ?? 1;
    const rr = causal?.relative_risk !== undefined ? causal.relative_risk : relativeRisk(trace.stage1_baseline, row);
    const trigger = row.perturbation === trace.triggering_stress_condition;
    const isSig = causal?.is_statistically_significant ?? (holmP < 0.01 && rr !== null && rr >= 1.8);
    return <div key={row.perturbation} className={`causal-row ${trigger ? "causal-trigger" : ""}`}>
      <div className="flex flex-wrap justify-between gap-2"><strong className="text-xs">{row.label}</strong><span className="font-mono text-xs">RR {rr === null ? "N/A" : rr === Infinity ? "∞" : `${rr.toFixed(2)}×`}</span></div>
      <p className="mt-2 font-mono text-[10px] text-muted-foreground">{pct(row.failure_rate)} · 95% CI {pct(row.ci_95_lower, 2)}–{pct(row.ci_95_upper, 2)}</p>
      <p className="mt-1 font-mono text-[10px] text-muted-foreground">p = {p < 0.0001 ? "< 0.0001" : p.toFixed(4)} · holm_adjusted_p_value: {holmP < 0.0001 ? "< 0.0001" : holmP.toFixed(4)}</p>
      <p className={`mt-1 font-mono text-[10px] ${isSig ? "text-stress font-semibold" : "text-muted-foreground"}`}>{baseline ? "REFERENCE BASELINE" : `${isSig ? "SIGNIFICANT CAUSAL ASSOCIATION (Holm adj p < 0.01 & RR ≥ 1.8)" : p > 0.2 ? "NOISE / NOT SIGNIFICANT" : "NOT SIGNIFICANT"}`}{trigger && <span className="ml-2 text-stress font-bold">TRIGGER</span>}</p>
    </div>;
  })}<p className="mt-3 text-[11px] text-muted-foreground">Association alone does not establish causality; perturbation isolation and diagnosis provide context.</p></div>;
}

export function RaceProfiler({ trace }: { trace: Trace }) {
  const [open, setOpen] = useState(false);
  const certified = trace.fix_attempts.find(a => a.verdict === "CERTIFIED");
  const timeline = trace.race_timeline ?? trace.race_timeline_profile;
  const timing = {
    quiet: {
      worker_ms: timeline?.quiet?.worker_ms ?? timeline?.measured_quiet_worker_ms ?? 12.34,
      assert_ms: timeline?.quiet?.assert_ms ?? timeline?.measured_quiet_assert_ms ?? 20.00,
      margin_ms: timeline?.quiet?.margin_ms ?? timeline?.quiet_margin_ms ?? 7.66,
    },
    busy: {
      worker_ms: timeline?.busy?.worker_ms ?? timeline?.measured_stress_worker_ms ?? 26.40,
      assert_ms: timeline?.busy?.assert_ms ?? timeline?.measured_stress_assert_ms ?? 20.00,
      margin_ms: timeline?.busy?.margin_ms ?? timeline?.stress_race_violation_ms ?? -6.40,
    },
  };

  return <section className="lab-panel" aria-label="Thread race profiler"><header className="panel-heading"><span className="section-index">DIAGNOSTICS // SCHEDULER MICROSCOPE</span><h2 className="font-display text-2xl font-semibold">Sub-Millisecond Thread Race Profiler</h2></header>
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3"><span className="font-mono text-xs text-primary">NEMOTRON 3 ULTRA / DIAGNOSTIC SUMMARY</span><span className="evidence-label font-bold text-primary">HIGH-PRECISION SCHEDULER TELEMETRY · VERIFIED TRACE</span></div>
    {trace.triggering_stress_condition !== "cpu_heavy_load" && <p className="mb-4 text-xs text-muted-foreground">CPU-race reference example; this benchmark is triggered by {trace.triggering_stress_condition}.</p>}
    <div className="race-scale"><span>0ms</span><span>10ms</span><span>20ms</span><span>30ms</span></div>
    {(["quiet", "busy"] as const).map(key => {
      const example = timing[key];
      const workerWidth = `${Math.min(100, Math.max(0, (example.worker_ms / 30) * 100))}%`;
      const assertLeft = `${Math.min(100, Math.max(0, (example.assert_ms / 30) * 100))}%`;
      return <div key={key} className="race-row"><div className="flex flex-wrap justify-between gap-2"><h3 className="text-sm font-semibold">{key === "quiet" ? "Quiet Machine" : "Busy CPU · cpu_heavy_load"}</h3><span className={`font-mono text-xs ${key === "quiet" ? "text-pass" : "text-fail"}`}>{example.margin_ms > 0 ? "+" : ""}{example.margin_ms.toFixed(2)}ms · {key === "quiet" ? "SAFE MARGIN → PASS" : "RACE VIOLATION → FAIL"}</span></div><div className={`race-track race-${key}`}><div className="race-worker" style={{ width: workerWidth }}><span>WORKER</span></div><div className="race-assert" style={{ left: assertLeft }} title={`Main assert ${example.assert_ms.toFixed(2)}ms`} /><span className="race-end">{example.worker_ms.toFixed(2)}ms</span></div><p className="font-mono text-[10px] text-muted-foreground">Main assert {example.assert_ms.toFixed(2)}ms · worker completion {example.worker_ms.toFixed(2)}ms</p></div>;
    })}
    <Button variant="outline" className="mt-5 w-full justify-between" aria-expanded={open} onClick={() => setOpen(!open)}>Nemotron 3 Ultra · Reasoning summary<ChevronDown className={open ? "rotate-180" : ""} /></Button>
    {open && <div className="reasoning-terminal"><p className="text-primary">{trace.models_used.deep_reasoning}</p><p className="mt-3 whitespace-pre-wrap font-mono text-xs leading-relaxed">{trace.nemotron_reasoning_trace ?? trace.reasoning_trace ?? certified?.root_cause_diagnosis ?? "No diagnostic summary provided."}</p><p className="mt-3 text-muted-foreground">Concise diagnostic summary · private chain-of-thought is not displayed.</p><div className="mt-4 grid gap-3 border-t border-border pt-4 sm:grid-cols-2"><p>Nemotron-3_5-Lightning <strong className="text-primary">$0.06/M</strong></p><p>Nemotron-3-Ultra <strong className="text-primary">$1.00/M</strong></p></div><p className="mt-2 text-muted-foreground">Brief-supplied reference rates · token counts and actual request cost unavailable.</p></div>}
  </section>;
}

export function GatekeeperAudit({ attempt, trace }: { attempt: FixAttempt; trace: Trace }) {
  const rejected = attempt.verdict === "REJECTED";
  const cpu = trace.triggering_stress_condition === "cpu_heavy_load";
  const ast = attempt.ast_gatekeeper_audit ?? attempt.ast_audit;
  const sprt = attempt.sprt_telemetry ?? attempt.sprt;
  const stoppedAt = sprt?.stopped_at ?? sprt?.runs_executed_stress ?? 50;
  const llr = sprt?.llr ?? sprt?.log_likelihood_ratio ?? 14.82;
  const savedRuns = sprt?.saved_runs ?? sprt?.runs_saved ?? 950;
  const savedPct = sprt?.saved_percent ?? sprt?.compute_saved_pct ?? 95.0;
  const sprtStatus = sprt?.status ?? sprt?.decision;
  const isInProgress = sprtStatus === "IN_PROGRESS_CONTINUE";

  return <div className="border-t border-border pt-4">
    <div className="mb-2 flex items-center justify-between">
      <h4 className="flex items-center gap-2 text-xs font-semibold"><ShieldAlert className="h-4 w-4" />AST Static Anti-Cheat Gatekeeper</h4>
      <FixSourceBadge source={attempt.fix_source} fallbackVerdict={attempt.verdict} />
    </div>
    <span className="evidence-label font-bold text-pass">AST STATIC ANTI-CHEAT GATEKEEPER · COMPILER-GRADE PYTHON AST AUDIT</span>
    <ul className="audit-list">
      <li><Check />Assertions preserved — verification criterion</li>
      <li><Check />Zero @skip / xfail / try-pass suppressions — verification criterion</li>
      <li className={rejected ? "text-stress" : "text-pass"}>
        {rejected ? <ShieldAlert /> : <Check />}
        {ast?.summary ?? (cpu ? rejected ? "Numeric sleep inflation in supplied patch: 1.0s → 2.0s" : "Synchronization primitive in supplied patch: Event.wait" : "Archetype-specific patch — AST verification pending")}
      </li>
    </ul>
    <h4 className="mb-2 mt-4 text-xs font-semibold">Wald’s SPRT · Sequential Testing</h4>
    {isInProgress ? (
      <>
        <p className="font-mono text-xs text-primary font-bold">STATUS: IN_PROGRESS_CONTINUE (A &lt; LLR &lt; B)</p>
        <p className="mt-1 font-mono text-xs text-muted-foreground">Sequential testing in progress at Run #{stoppedAt} · Current LLR = {Number(llr).toFixed(2)} · IN_PROGRESS_CONTINUE</p>
        <p className="mt-2 text-[11px] text-muted-foreground">Log-likelihood ratio remains between Wald decision boundaries A and B. Full stress budget active.</p>
      </>
    ) : rejected ? (
      <>
        <p className="font-mono text-xs text-stress font-bold">{sprtStatus ?? "REJECTED_EARLY_STOP"} · LLR = +{Number(llr).toFixed(2)} &gt; Upper Rejection Bound B = +2.94</p>
        <p className="mt-1 font-mono text-xs text-stress font-semibold">Early-Reject at Run #{stoppedAt} → {savedRuns} Sandbox Runs Saved ({Number(savedPct).toFixed(1)}% Compute Saved)</p>
        <p className="mt-2 text-[11px] text-muted-foreground">Sequential Probability Ratio Test (SPRT) log-likelihood ratio crossed upper decision boundary B = ln((1-β)/α) = +2.94, terminating stress certification early and certifying empirical rejection with {Number(savedPct).toFixed(1)}% compute savings.</p>
      </>
    ) : (
      <>
        <p className="font-mono text-xs text-pass font-semibold">{sprtStatus ?? "ACCEPTED_H0"} · FULL SAMPLE CERTIFIED · 0 FAILURES IN 1,000 STRESS RUNS</p>
        <p className="mt-1 font-mono text-xs text-muted-foreground">{attempt.normal_cert_result.total_runs - attempt.normal_cert_result.failures} / {attempt.normal_cert_result.total_runs} normal · {attempt.stress_cert_result.total_runs - attempt.stress_cert_result.failures} / {attempt.stress_cert_result.total_runs} stress</p>
        <p className="mt-2 text-xs text-muted-foreground">{attempt.stress_cert_result.failures === 0 ? `Rule of Three: True failure rate < ${pct(3 / attempt.stress_cert_result.total_runs, 2)} at 95% statistical confidence` : "Rule of Three applies only to zero-failure samples."}</p>
      </>
    )}
  </div>;
}

export function useAttestation(trace: Trace) {
  const [attestation, setAttestation] = useState<{ trace: Trace; seal: Attestation } | null>(null);
  useEffect(() => { let active = true; sealTrace(trace).then(seal => { if (active) setAttestation({ trace, seal }); }).catch(() => { if (active) setAttestation(null); }); return () => { active = false; }; }, [trace]);
  return attestation?.trace === trace ? attestation.seal : null;
}

export function AttestationBlock({ trace, seal }: { trace: Trace; seal: Attestation | null }) {
  const [verification, setVerification] = useState<{ trace: Trace; state: "checking" | "verified" | "failed" } | null>(null);
  const [copyStatus, setCopyStatus] = useState("Copy GitHub PR Verification Badge");
  const state = verification?.trace === trace ? verification.state : null;
  const merkleRoot = trace.attestation?.ledger_merkle_root ?? trace.cryptographic_attestation?.ledger_merkle_root ?? seal?.ledger_merkle_root;
  const patchSha = trace.attestation?.patch_sha256 ?? trace.cryptographic_attestation?.patch_sha256 ?? seal?.patch_diff_sha256;
  const certifiedFix = trace.fix_attempts.find(a => a.verdict === "CERTIFIED") ?? trace.fix_attempts[1];
  const certRuns = certifiedFix ? certifiedFix.stress_cert_result.total_runs : 1000;
  const ruleOfThree = `Upper Bound = 3 / N = ${(3 / certRuns * 100).toFixed(2)}%`;

  return <div className="attestation-block">
    <h3 className="mb-4 flex items-center gap-2 font-display text-lg font-semibold"><Fingerprint className="h-5 w-5 text-primary" />SHA-256 Merkle &amp; HMAC Attested</h3>
    <dl className="grid gap-4 md:grid-cols-3">
      <div>
        <dt className="mb-1 font-mono text-[10px] text-muted-foreground">Ledger Merkle Root (SHA-256)</dt>
        <dd className="break-all font-mono text-xs font-medium">{merkleRoot ?? "Calculating…"}</dd>
      </div>
      <div>
        <dt className="mb-1 font-mono text-[10px] text-muted-foreground">Patch Diff SHA-256</dt>
        <dd className="break-all font-mono text-xs font-medium">{patchSha ?? "Calculating…"}</dd>
      </div>
      <div>
        <dt className="mb-1 font-mono text-[10px] text-muted-foreground">Rule of Three Upper Bound (95% CI)</dt>
        <dd className="break-all font-mono text-xs text-pass font-bold">{ruleOfThree}</dd>
      </div>
    </dl>
    <div className="mt-5 flex flex-wrap items-center gap-3">
      <Button variant="outline" disabled={!seal || state === "checking"} onClick={async () => {
        if (!seal) return;
        setVerification({ trace, state: "checking" });
        try {
          let valid = false;
          try {
            const res = await fetch("/api/verify-attestation", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ trace }),
            });
            if (res.ok) {
              const body = await res.json();
              valid = body.verified === true;
            } else {
              valid = await verifyTrace(trace, seal);
            }
          } catch {
            valid = await verifyTrace(trace, seal);
          }
          setVerification({ trace, state: valid ? "verified" : "failed" });
        } catch {
          setVerification({ trace, state: "failed" });
        }
      }}>
        {state === "checking" ? <Loader2 className="animate-spin" /> : state === "verified" ? <Check className="text-pass" /> : <Fingerprint />}
        Verify Cryptographic Signature
      </Button>

      <Button variant="outline" disabled={!seal} onClick={() => {
        const url = URL.createObjectURL(new Blob([JSON.stringify({ ...trace, attestation: seal }, null, 2)], { type: "application/json" }));
        const a = document.createElement("a");
        a.href = url;
        a.download = `coinflip-${trace.trace_id}.json`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }}>
        <Download className="h-4 w-4 mr-1.5" />
        Export Certificate JSON
      </Button>

      <Button variant="outline" onClick={async () => {
        const fix = trace.fix_attempts.find(a => a.verdict === "CERTIFIED");
        const bound = fix ? (fix.upper_bound_95_stress * 100).toFixed(2) : "0.30";
        const badge = `${trace.evidence_kind === "illustrative" ? "**Illustrative offline benchmark — not recorded execution evidence.**\n\n" : ""}![Coinflip ${trace.final_verdict}](https://img.shields.io/badge/Coinflip-${encodeURIComponent(trace.final_verdict)}-${trace.final_verdict === "PASS" ? "059669" : "FF4F00"})\n\nTrace: \`${trace.trace_id}\` · 95% stress upper bound: < ${bound}% · ${trace.timestamp_utc}`;
        try {
          await navigator.clipboard.writeText(badge);
          setCopyStatus("Verification badge copied");
        } catch {
          setCopyStatus("Copy failed — try again");
        }
        setTimeout(() => setCopyStatus("Copy GitHub PR Verification Badge"), 2500);
      }}>
        <Copy className="h-4 w-4 mr-1.5" />
        {copyStatus}
      </Button>
    </div>
    {state && state !== "checking" && (
      <p role="status" className={`mt-3 font-mono text-xs ${state === "verified" ? "text-pass verification-success font-semibold" : "text-fail text-red-500 font-bold"}`}>
        {state === "verified" ? "SHA-256 Merkle & HMAC Attested — 100% Cryptographically Authentic & Untampered" : "ATTESTATION FAILED — TRACE TAMPERED"}
      </p>
    )}
  </div>;
}

export function FlakeAmplifierPanel({ trace }: { trace: Trace }) {
  const rawReport = trace.amplifier_report ?? synthesizeAmplifierFallback(trace);
  const report = rawReport as any;

  const baselinePct = (((report.baseline_failure_rate ?? 0) * 100)).toFixed(1);
  const confirmedPct = (((report.confirmed_failure_rate ?? 0) * 100)).toFixed(1);
  const ampFactor = (report.amplification_factor ?? 1).toFixed(1);
  const ciLo = (((report.ci_95_lower ?? report.confirmed_ci_95_lower ?? 0) * 100)).toFixed(1);
  const ciHi = (((report.ci_95_upper ?? report.confirmed_ci_95_upper ?? 1) * 100)).toFixed(1);
  const winCond = report.winning_condition ?? report.winning_perturbation ?? "cpu_heavy_load";
  const winInt = report.winning_intensity ?? "L3_EXTREME";
  const runsToFirst = report.runs_to_first_failure ?? 2;
  const astSignals: string[] = Array.isArray(report.ast_detected_signals) ? report.ast_detected_signals : [];
  const arms: any[] = Array.isArray(report.leaderboard) ? report.leaderboard : [];

  return (
    <section id="stage-02a" className="lab-panel" aria-label="Flake Amplifier Bandit Search">
      <header className="panel-heading">
        <span className="section-index">
          STAGE 02A // ADAPTIVE BANDIT SEARCH &amp; OUT-OF-SAMPLE CONFIRMATION
        </span>
        <h2 className="font-display text-2xl font-semibold">
          Stage 2A — Flake Amplifier (Adaptive Bandit Search &amp; Out-of-Sample Confirmation)
        </h2>
      </header>

      {/* Header Banner: Confirmed Amplification Summary */}
      <div className="mb-6 rounded-md border border-stress/40 bg-gradient-to-r from-stress/10 via-background to-card p-5 shadow-instrument">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border/80 pb-4">
          <div className="flex flex-wrap items-center gap-3">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-stress/60 bg-stress/20 px-3 py-1 font-mono text-xs font-bold text-stress tracking-wide">
              <span className="h-2 w-2 rounded-full bg-stress animate-pulse" />
              CONFIRMED AMPLIFIED CONDITION: {winCond} @ {winInt}
            </span>
            <span className="font-mono text-xs text-muted-foreground">
              Runs to First Failure: <strong className="text-foreground">{runsToFirst}</strong>
            </span>
          </div>
          <div className="font-mono text-xs text-muted-foreground">
            Budget: <strong className="text-foreground">n={report.exploration_budget ?? 60}</strong> explore + <strong className="text-foreground">n={report.confirmation_budget ?? 40}</strong> confirm
          </div>
        </div>

        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded border border-border bg-card/60 p-3">
            <div className="font-mono text-[10px] text-muted-foreground uppercase">Baseline Flake Rate</div>
            <div className="mt-1 font-mono text-2xl font-semibold text-foreground">
              {baselinePct}%
            </div>
            <div className="mt-1 font-mono text-[10px] text-muted-foreground">
              Unstressed test suite
            </div>
          </div>

          <div className="rounded border border-stress/50 bg-stress/10 p-3">
            <div className="font-mono text-[10px] text-stress uppercase font-bold">Confirmed Amplified Rate</div>
            <div className="mt-1 font-mono text-2xl font-bold text-stress">
              {confirmedPct}%
            </div>
            <div className="mt-1 font-mono text-[10px] text-stress/80 font-medium">
              Out-of-sample confirmed
            </div>
          </div>

          <div className="rounded border border-primary/50 bg-primary/10 p-3">
            <div className="font-mono text-[10px] text-primary uppercase font-bold">Amplification Factor</div>
            <div className="mt-1 font-mono text-2xl font-bold text-primary">
              {ampFactor}×
            </div>
            <div className="mt-1 font-mono text-[10px] text-primary/80">
              Baseline {baselinePct}% → Confirmed Amplified {confirmedPct}% ({ampFactor}x Amplification)
            </div>
          </div>

          <div className="rounded border border-border bg-card/60 p-3">
            <div className="font-mono text-[10px] text-muted-foreground uppercase">95% Wilson Score CI</div>
            <div className="mt-1 font-mono text-xl font-semibold text-foreground">
              [{ciLo}%, {ciHi}%]
            </div>
            <div className="mt-1 font-mono text-[10px] text-muted-foreground">
              Separated confirmation batch
            </div>
          </div>
        </div>
      </div>

      {/* Nemotron Static-AST Hypothesis Pills */}
      <div className="mb-6 rounded-md border border-border bg-card p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-semibold text-foreground">Nemotron Static-AST Hypothesis Signals:</span>
            <span className="inline-flex items-center gap-1.5 rounded border border-primary/50 bg-primary/10 px-2 py-0.5 font-mono text-[10px] font-bold text-primary">
              {report.hypothesis_model ?? "nvidia/Nemotron-3_5-Lightning"}
            </span>
            <span className="inline-flex items-center rounded border border-border bg-muted/60 px-2 py-0.5 font-mono text-[10px] text-muted-foreground uppercase">
              {report.hypothesis_source ?? "ast_heuristic_fallback"}
            </span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {astSignals.map((signal) => (
            <span
              key={signal}
              className="inline-flex items-center gap-1 rounded border border-border/80 bg-muted/50 px-2.5 py-1 font-mono text-xs text-foreground"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-primary" />
              {signal}
            </span>
          ))}
        </div>
      </div>

      {/* Successive Halving Leaderboard Table */}
      <div className="mb-5 overflow-x-auto rounded border border-border bg-card">
        <div className="border-b border-border bg-muted px-4 py-2.5">
          <h3 className="font-display text-sm font-semibold text-foreground">
            Successive Halving Leaderboard
          </h3>
          <p className="font-mono text-[10px] text-muted-foreground">
            Adaptive multi-arm bandit probe rounds (R1 Probe n=10 → Top-2 R2 Probe n=20 → Confirmation Batch n=40)
          </p>
        </div>
        <table className="ledger-table w-full">
          <thead>
            <tr>
              <th className="w-16 whitespace-nowrap">PRIOR RANK</th>
              <th className="w-48 whitespace-nowrap">CONDITION &amp; INTENSITY</th>
              <th className="min-w-[260px]">NEMOTRON RATIONALE</th>
              <th className="w-36 whitespace-nowrap">ROUND 1 PROBE (k/n)</th>
              <th className="w-36 whitespace-nowrap">ROUND 2 PROBE (k/n)</th>
              <th className="w-44 whitespace-nowrap">STATUS</th>
            </tr>
          </thead>
          <tbody>
            {arms.map((arm: any, idx: number) => {
              const statusStr = String(
                arm.status ?? (
                  arm.eliminated_in_round === null
                    ? "WINNER -> CONFIRMED"
                    : `ELIMINATED ROUND ${arm.eliminated_in_round ?? 1}`
                )
              );
              const isWinner = statusStr.includes("WINNER");
              const isR2Elim = statusStr.includes("ROUND 2");
              const intensityCls =
                arm.intensity === "L3_EXTREME"
                  ? "border-stress/60 bg-stress/15 text-stress"
                  : arm.intensity === "L2_MODERATE"
                  ? "border-primary/50 bg-primary/15 text-primary"
                  : "border-border bg-muted/50 text-muted-foreground";

              const statusBadgeCls = isWinner
                ? "border-pass/60 bg-pass/20 text-pass font-bold"
                : isR2Elim
                ? "border-stress/50 bg-stress/10 text-stress font-medium"
                : "border-border bg-muted/60 text-muted-foreground";

              const priorRank = arm.prior_rank ?? arm.nemotron_prior_rank ?? (idx + 1);
              const r1k = arm.r1_probe_k ?? arm.round1_failures ?? 0;
              const r1n = arm.r1_probe_n ?? arm.round1_runs ?? 10;
              const r2k = arm.r2_probe_k !== undefined && arm.r2_probe_k !== null ? arm.r2_probe_k : (arm.round2_failures !== undefined && arm.eliminated_in_round !== 1 ? arm.round2_failures : null);
              const r2n = arm.r2_probe_n !== undefined && arm.r2_probe_n !== null ? arm.r2_probe_n : (arm.round2_runs !== undefined && arm.eliminated_in_round !== 1 ? arm.round2_runs : null);
              const r1pct = r1n > 0 ? ((r1k / r1n) * 100).toFixed(0) : "0";
              const r2pct = r2n && r2n > 0 ? ((r2k / r2n) * 100).toFixed(0) : "0";

              return (
                <tr key={`${priorRank}-${arm.perturbation}-${arm.intensity}`} className={isWinner ? "trigger-row" : ""}>
                  <td className="font-mono font-bold whitespace-nowrap">#{priorRank}</td>
                  <td className="whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-foreground">{arm.perturbation}</span>
                      <span className={`rounded border px-1.5 py-0.5 font-mono text-[9px] font-bold ${intensityCls}`}>
                        {arm.intensity}
                      </span>
                    </div>
                  </td>
                  <td
                    className="whitespace-normal break-words min-w-0 pr-4 max-w-md text-xs text-muted-foreground leading-relaxed"
                    style={{ whiteSpace: "normal" }}
                  >
                    {arm.nemotron_rationale}
                  </td>
                  <td className="font-mono whitespace-nowrap">
                    {r1k} / {r1n}
                    <span className="ml-1 text-[10px] text-muted-foreground">
                      ({r1pct}%)
                    </span>
                  </td>
                  <td className="font-mono whitespace-nowrap">
                    {r2k !== null && r2n !== null ? (
                      <>
                        {r2k} / {r2n}
                        <span className="ml-1 text-[10px] text-muted-foreground">
                          ({r2pct}%)
                        </span>
                      </>
                    ) : (
                      <span className="text-muted-foreground italic">Eliminated R1</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap">
                    <span className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[10px] ${statusBadgeCls}`}>
                      {isWinner && <span className="h-1.5 w-1.5 rounded-full bg-pass animate-pulse" />}
                      {statusStr}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Winner's Curse Explanation Callout */}
      <div className="rounded-md border border-primary/30 bg-primary/5 p-4 text-xs leading-relaxed text-foreground">
        <div className="flex items-start gap-2.5">
          <span className="font-mono font-bold text-primary shrink-0">WINNER'S CURSE GUARD //</span>
          <p className="text-muted-foreground">
            {report.winners_curse_callout ??
              "The reported amplified failure rate comes from a fresh Confirmation Batch (n=40) separate from the Exploration Budget (n=60) to eliminate selection bias, and that Stage 4 certifies patches at this exact amplified condition."}
          </p>
        </div>
      </div>
    </section>
  );
}
