import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, ComposedChart, ErrorBar, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Activity, BadgeCheck, Brain, Cpu, FlaskConical, Loader2, Play, ScrollText, ShieldAlert, ShieldCheck, XCircle } from "lucide-react";
import { CommandBar, Pipeline, Dots, Diff, CertificateSeal } from "@/components/lab-controls";
import { CausalLedger, RaceProfiler, GatekeeperAudit, AttestationBlock, useAttestation, FixSourceBadge } from "@/components/scientific-telemetry";
import { FALLBACK_TRACE, fetchTrace, fetchCaseTrace, fallbackForCase, makeDots, pct, runLive, type CaseId, type Trace } from "@/lib/trace";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "COINFLIP — Flaky-Test Investigator & Verifier" },
      { name: "description", content: "Statistical flaky-test investigation and fix certification dashboard powered by NVIDIA Nemotron on Nebius." },
      { property: "og:title", content: "COINFLIP — Flaky-Test Investigator & Verifier" },
      { property: "og:description", content: "Coin-toss dot matrices, Wilson CI ledgers and a certified fix — proof, not a single green run." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Dashboard,
});

const C = { pass: "var(--pass)", fail: "var(--fail)", stress: "var(--stress)", normal: "var(--normal)", grid: "var(--border)", muted: "var(--muted-foreground)" };
const tip = { contentStyle: { background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 6, fontFamily: "var(--font-mono)", fontSize: 12 }, labelStyle: { color: "var(--foreground)" } };

function Panel({ n, title, icon, children }: { n: string; title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <section id={`stage-${n}`} className="lab-panel">
      <header className="panel-heading">
        <span className="section-index">STAGE {n} {n === "03" ? "& 04" : ""} // {n === "01" ? "BASELINE COIN TOSS" : n === "02" ? "PERTURBATION LEDGER" : "STRESS REJECTION GATE"}</span>
        <span className="text-muted-foreground">{icon}</span>
        <h2 className="font-display text-2xl font-semibold">{title}</h2>
      </header>
      {children}
    </section>
  );
}

function Verdict({ v }: { v: "BROKEN" | "REJECTED" | "CERTIFIED" }) {
  const cls = v === "CERTIFIED" ? "border-pass/50 bg-pass/15 text-pass" : v === "REJECTED" ? "border-stress/50 bg-stress/15 text-stress" : "border-fail/50 bg-fail/15 text-fail";
  return <span className={`rounded border px-2 py-0.5 font-mono text-xs font-bold tracking-widest ${cls}`}>{v}</span>;
}

function Dashboard() {
  const [trace, setTrace] = useState<Trace>(FALLBACK_TRACE);
  const [source, setSource] = useState<"loading" | "api" | "fallback">("loading");
  const [live, setLive] = useState<{ busy: boolean; note?: string | undefined }>({ busy: false });

  const [caseId, setCaseId] = useState<CaseId>("hero");
  const attestation = useAttestation(trace);
  useEffect(() => {
    let active = true;
    const ctrl = new AbortController();
    setSource("loading");
    setTrace(fallbackForCase(caseId));
    setLive({ busy: false });
    const request = fetchCaseTrace(caseId, ctrl.signal).then(result => caseId === "hero" && result.source === "fallback" && !ctrl.signal.aborted ? fetchTrace() : result);
    request.then(result => { if (active) { setTrace(result.trace); setSource(result.source); } });
    return () => { active = false; ctrl.abort(); };
  }, [caseId]);
  const onCase = (id: CaseId) => { if (!live.busy) setCaseId(id); };

  const onLive = async () => {
    setLive({ busy: true });
    const r = await runLive(caseId);
    if (r.ok && r.data) {
      if (r.data.stage2_ledger) setTrace((t) => ({ ...t, ...r.data } as Trace));
      setLive({ busy: false, note: r.data.is_fallback ? r.data.fallback_note ?? "Backend returned fallback data." : `Live mini-batch complete (30 runs/condition for ${caseId}).` });
    } else setLive({ busy: false, note: r.error });
  };

  const a1 = trace.fix_attempts[0] ?? FALLBACK_TRACE.fix_attempts[0];
  if (!a1) throw new Error("Trace has no fix attempts");
  const a2 = trace.fix_attempts[1] ?? a1;
  const stressCond = trace.stage2_ledger.find((c) => c.perturbation === trace.triggering_stress_condition) ?? trace.stage1_baseline;
  const base = trace.stage1_baseline;
  const origStressDots = useMemo(() => stressCond.run_dots?.length ? stressCond.run_dots : makeDots(stressCond.total_runs, stressCond.failures), [stressCond]);

  const ledgerData = trace.stage2_ledger.map((c) => ({
    label: c.label, key: c.perturbation, rate: +(c.failure_rate * 100).toFixed(2),
    err: [+((c.failure_rate - c.ci_95_lower) * 100).toFixed(2), +((c.ci_95_upper - c.failure_rate) * 100).toFixed(2)],
    lo: c.ci_95_lower, hi: c.ci_95_upper, f: c.failures, n: c.total_runs,
  }));
  const verdictData = [
    { name: "Original Test", normal: base.failure_rate * 100, stress: stressCond.failure_rate * 100 },
    { name: "Rejected Quick Fix", normal: a1.normal_cert_result.failure_rate * 100, stress: a1.stress_cert_result.failure_rate * 100 },
    { name: "Certified Fix", normal: a2.normal_cert_result.failure_rate * 100, stress: a2.stress_cert_result.failure_rate * 100 },
  ];
  const fmtN = (n: number) => n.toLocaleString("en-US");

  return (
    <>
      <CommandBar trace={trace} busy={live.busy} note={live.note} onLive={onLive} caseId={caseId} caseBusy={source === "loading"} onCase={onCase} />
      <main className="lab-main">
      <header className="lab-hero">
        <div className="hero-topline"><span className="font-mono text-xs text-primary">COINFLIP / RESEARCH CONSOLE</span><span className="font-mono text-xs text-muted-foreground">NEBIUS × NVIDIA · 2026</span></div>
        <div className="hero-title-row"><div><h1 className="font-display">Proof. Not probability.</h1><p className="hero-subtitle">Statistical Flaky-Test Investigator &amp; Verifier</p></div><div className="hero-verdict"><span className="font-mono text-[10px] text-muted-foreground">FINAL VERDICT</span><strong className="font-mono text-pass">{trace.final_verdict}<BadgeCheck /></strong><span className="font-mono text-xs text-muted-foreground">95% confidence</span></div></div>
        <div className="hero-metadata"><span className="replay-badge"><Activity className="h-3 w-3" />{trace.execution_mode_badge}</span><span className="font-mono text-[10px] text-muted-foreground">{source === "loading" ? "CONNECTING…" : source === "api" ? "API TRACE" : trace.evidence_kind === "illustrative" ? "ILLUSTRATIVE OFFLINE FIXTURE" : "BUILT-IN RECORDED TRACE"}</span></div>
        <dl className="hero-trace"><div><dt>PROJECT</dt><dd>{trace.project_name}</dd></div><div><dt>TEST IDENTIFIER</dt><dd className="break-all">{trace.test_identifier}</dd></div><div><dt>TRACE</dt><dd>{trace.trace_id}</dd></div></dl>
      </header>
      <Pipeline />
      {/* 2. Dot matrix */}
      <Panel n="01" title="The Coin-Toss Dot Matrix" icon={<FlaskConical className="h-4 w-4" />}>
        <div className="grid gap-5 lg:grid-cols-3 items-start">
          {[
            {
              t: "Original Test",
              v: "BROKEN" as const,
              n: base.run_dots,
              s: origStressDots,
              summary: `${base.failures}/${base.total_runs} quiet (${pct(base.failure_rate)}) · ${stressCond.failures}/${stressCond.total_runs} stress (${pct(stressCond.failure_rate)})`,
            },
            {
              t: "Attempt 1 · Naive Quick Fix",
              v: "REJECTED" as const,
              n: a1.normal_cert_result.run_dots,
              s: a1.stress_cert_result.run_dots,
              summary: `${a1.normal_cert_result.failures}/${fmtN(a1.normal_cert_result.total_runs)} quiet · ${a1.stress_cert_result.failures}/${fmtN(a1.stress_cert_result.total_runs)} stress (${pct(a1.stress_cert_result.failure_rate)})`,
            },
            {
              t: "Attempt 2 · Coinflip Fix",
              v: "CERTIFIED" as const,
              n: a2.normal_cert_result.run_dots,
              s: a2.stress_cert_result.run_dots,
              summary: `0/${fmtN(a2.normal_cert_result.total_runs)} quiet · 0/${fmtN(a2.stress_cert_result.total_runs)} stress (Upper bound < ${pct(a2.upper_bound_95_stress, 2)})`,
            },
          ].map((x) => (
            <div key={x.t} className="matrix-item space-y-4">
              <div className="flex items-center justify-between"><h3 className="text-sm font-semibold">{x.t}</h3><Verdict v={x.v} /></div>
              <Dots dots={x.n} label="Quiet Baseline" />
              <Dots dots={x.s} label={stressCond.label} />
              <div className="border-t border-border/80 pt-3 font-mono text-[11px] text-muted-foreground flex justify-between items-center">
                <span>Summary:</span>
                <span className="font-semibold text-foreground/90">{x.summary}</span>
              </div>
            </div>
          ))}
        </div>
      </Panel>

      {/* 3. Ledger */}
      <Panel n="02" title="Stage 2 · Experiment Ledger" icon={<Cpu className="h-4 w-4" />}>
        <div className="grid gap-5 lg:grid-cols-5">
          <div className="space-y-4 lg:col-span-3">
            <div className="h-[380px]">
              <ResponsiveContainer>
                <BarChart data={ledgerData} layout="vertical" margin={{ left: 20, right: 30 }}>
                  <CartesianGrid stroke={C.grid} strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" unit="%" stroke={C.muted} fontSize={11} domain={[0, Math.max(70, ...ledgerData.map(d => Math.ceil(d.hi * 100)))]} />
                  <YAxis type="category" dataKey="label" width={195} stroke={C.muted} fontSize={11} />
                  <Tooltip {...tip} cursor={{ fill: "var(--accent)" }} formatter={(v: number, _n, p) => [`${v}% (${p.payload.f}/${p.payload.n}) · CI ${pct(p.payload.lo, 2)}–${pct(p.payload.hi, 2)}`, "failure rate"]} />
                  <Bar dataKey="rate" radius={[0, 4, 4, 0]}>
                    {ledgerData.map((d) => (
                      <Cell key={d.key} fill={d.key === trace.triggering_stress_condition ? C.fail : d.key.startsWith("cpu") ? C.stress : C.normal} />
                    ))}
                    <ErrorBar dataKey="err" width={6} stroke="var(--foreground)" direction="x" />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <p className="font-mono text-[11px] text-muted-foreground">Whiskers = 95% Wilson confidence interval · red = triggering condition</p>
            </div>
            <div className="ledger-table-wrap">
              <table className="ledger-table">
                <thead>
                  <tr>
                    <th>PERTURBATION</th>
                    <th>FAILED / RUNS</th>
                    <th>FAILURE RATE</th>
                    <th>95% WILSON INTERVAL</th>
                    <th>HOLM ADJ P-VALUE</th>
                    <th>OBSERVATION</th>
                  </tr>
                </thead>
                <tbody>
                  {trace.stage2_ledger.map(c => {
                    const holmP = c.causal_analytics?.holm_adjusted_p_value ?? c.holm_adjusted_p_value;
                    return (
                      <tr key={c.perturbation} className={c.perturbation === trace.triggering_stress_condition ? "trigger-row" : ""}>
                        <td>{c.label}<small>{c.perturbation}</small></td>
                        <td>{c.failures} / {c.total_runs}</td>
                        <td>{pct(c.failure_rate, 1)}</td>
                        <td>[{c.ci_95_lower.toFixed(4)}, {c.ci_95_upper.toFixed(4)}]</td>
                        <td className="font-mono text-xs">{holmP !== undefined ? (holmP < 0.0001 ? "< 0.0001" : holmP.toFixed(4)) : "—"}</td>
                        <td>
                          {c.perturbation === trace.triggering_stress_condition ? (
                            <span className="trigger-badge"><span className="status-dot" />TRIGGERING PERTURBATION DETECTED</span>
                          ) : (
                            <span className="text-muted-foreground">{c.perturbation.startsWith("cpu") ? "CPU SENSITIVE" : "CONTROL"}</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
          <div className="space-y-4 lg:col-span-2">
            <CausalLedger trace={trace} />
            <div className="rounded-md border border-primary/40 bg-primary/5 p-4">
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-primary"><Brain className="h-4 w-4" /> Root cause · {trace.models_used.deep_reasoning}</div>
              <p className="text-sm leading-relaxed">{a2.root_cause_diagnosis}</p>
            </div>
            <div className="rounded-md border border-border bg-background/60 p-4">
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-muted-foreground"><ScrollText className="h-4 w-4" /> Log summary · {trace.models_used.bulk_log_reading}</div>
              <p className="text-sm leading-relaxed">{trace.log_summary ?? "Failure logs share a single signature."}</p>
              <code className="mt-2 block break-all rounded bg-fail/10 p-2 font-mono text-[11px] text-fail">{base.sample_failure_logs[0]}</code>
            </div>
          </div>
        </div>
      </Panel>

      <RaceProfiler trace={trace} />

      {/* 4. Verdict comparison + diff + streak */}
      <Panel n="03" title="A fix is only as good as its evidence." icon={<ShieldAlert className="h-4 w-4" />}>
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="h-[300px]">
            <ResponsiveContainer>
              <BarChart data={verdictData}>
                <CartesianGrid stroke={C.grid} strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" stroke={C.muted} fontSize={11} />
                <YAxis unit="%" stroke={C.muted} fontSize={11} />
                <Tooltip {...tip} cursor={{ fill: "var(--accent)" }} formatter={(v: number) => `${v.toFixed(1)}%`} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="normal" name="Normal Machine" fill={C.normal} radius={[4, 4, 0, 0]} />
                <Bar dataKey="stress" name="Triggering Perturbation" fill={C.stress} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div>
            <h3 className="mb-2 text-sm font-semibold">Why One Green Run Proves Nothing</h3>
            <div className="h-[200px]">
              <ResponsiveContainer>
                <LineChart data={trace.streak_curve_data.points}>
                  <CartesianGrid stroke={C.grid} strokeDasharray="3 3" />
                  <XAxis dataKey="true_failure_rate_pct" unit="%" stroke={C.muted} fontSize={11} />
                  <YAxis unit="%" stroke={C.muted} fontSize={11} />
                  <Tooltip {...tip} labelFormatter={(l) => `true failure rate ${l}%`} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line dataKey="pass_1_run_pct" name="P(pass 1 run)" stroke={C.pass} dot={false} strokeWidth={2} />
                  <Line dataKey="pass_10_runs_pct" name="P(pass 10 runs)" stroke={C.stress} dot={false} strokeWidth={2} />
                  <Line dataKey="pass_100_runs_pct" name="P(pass 100 runs)" stroke={C.fail} dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="h-[90px]">
              <ResponsiveContainer>
                <ComposedChart data={trace.streak_curve_data.rule_of_three_bars} layout="vertical" margin={{ left: 10 }}>
                  <XAxis type="number" hide domain={[0, 3]} />
                  <YAxis type="category" dataKey="runs" width={70} stroke={C.muted} fontSize={10} />
                  <Tooltip {...tip} formatter={(_v, _n, p) => [p.payload.bound, "Rule of Three bound"]} />
                  <Bar dataKey="bound_pct" fill={C.normal} radius={[0, 3, 3, 0]} barSize={10} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <p className="font-mono text-[11px] text-muted-foreground">Rule of Three: 0 failures in N runs ⇒ true rate &lt; 3/N (95%)</p>
          </div>
        </div>
        <div id="stage-04" className="comparison-arena mt-6 grid gap-6 lg:grid-cols-2">
          {[a1, a2].map((a) => (
            <div key={a.attempt_number} className={`fix-item space-y-4 ${a.verdict === "CERTIFIED" ? "fix-certified" : "fix-rejected"}`}><div className={`arena-stamp ${a.verdict === "CERTIFIED" ? "text-pass" : "text-fail"}`}>{a.verdict === "CERTIFIED" ? `CERTIFIED (< ${pct(a.upper_bound_95_stress, 2)} BOUND)` : "REJECTED UNDER STRESS"}</div><div className="flex justify-between gap-4 border-b border-border pb-4 font-mono"><div><span className="text-[10px] text-muted-foreground">QUIET MACHINE</span><p className="text-2xl text-pass">{pct(a.normal_cert_result.failure_rate)}<span className="ml-2 text-xs text-muted-foreground">{a.normal_cert_result.failures}/{fmtN(a.normal_cert_result.total_runs)}</span></p></div><div><span className="text-[10px] text-muted-foreground">TRIGGER CONDITION</span><p className={`text-2xl ${a.verdict === "CERTIFIED" ? "text-pass" : "text-fail"}`}>{pct(a.stress_cert_result.failure_rate)}<span className="ml-2 text-xs text-muted-foreground">{a.stress_cert_result.failures}/{fmtN(a.stress_cert_result.total_runs)}</span></p></div></div>
              <div className="flex items-center justify-between gap-2">
                <div className="space-y-1">
                  <h3 className="text-sm font-semibold">Attempt {a.attempt_number} · {a.fix_title}</h3>
                  <FixSourceBadge source={a.fix_source} fallbackVerdict={a.verdict} />
                </div>
                <Verdict v={a.verdict} />
              </div>
              <Diff patch={a.git_diff_patch} />
              <GatekeeperAudit attempt={a} trace={trace} />
              {a.rejection_reason ? (
                <p className="flex gap-2 rounded-md border border-stress/40 bg-stress/10 p-3 text-xs text-stress"><XCircle className="h-4 w-4 shrink-0" />{a.rejection_reason}</p>
              ) : (
                <p className="flex gap-2 rounded-md border border-pass/40 bg-pass/10 p-3 text-xs text-pass"><BadgeCheck className="h-4 w-4 shrink-0" />0/1,000 normal · 0/1,000 stress. Upper bound {pct(a.upper_bound_95_stress, 2)} &lt; {pct(a.target_limit, 2)} target.</p>
              )}
            </div>
          ))}
        </div>
      </Panel>

      {/* 5. Certificate */}
      <section id="stage-05" className="certificate lab-panel">
        <span className="section-index">STAGE 05 // STATISTICAL CERTIFICATE</span>
        {trace.evidence_kind === "illustrative" && <p className="mb-4 border-b border-stress/30 pb-3 font-mono text-xs text-stress">ILLUSTRATIVE BENCHMARK CERTIFICATE · NOT RECORDED EXECUTION EVIDENCE</p>}
        
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-dashed border-border pb-5">
          <div className="flex items-center gap-3">
            <CertificateSeal />
            <div>
              <p className="font-mono text-xs tracking-[0.3em] text-muted-foreground">OFFICIAL</p>
              <h2 className="font-display text-3xl font-bold">Coinflip Certificate</h2>
            </div>
          </div>
          <div className="rounded-md border-2 border-pass px-5 py-2 text-center">
            <p className="font-mono text-[10px] tracking-widest text-muted-foreground">FINAL VERDICT</p>
            <p className="font-mono text-3xl font-bold text-pass">{trace.final_verdict}</p>
          </div>
        </div>
        <dl className="mt-6 grid gap-x-8 gap-y-5 font-mono text-sm md:grid-cols-2 lg:grid-cols-3">
          <Field k="Project & Test" v={<>{trace.project_name}<br /><span className="break-all text-xs text-muted-foreground">{trace.test_identifier}</span></>} />
          <Field k="Trace ID & Timestamp" v={<>{trace.trace_id}<br /><span className="text-xs text-muted-foreground">{trace.timestamp_utc}</span></>} />
          <Field k="Root Cause Found" v={<span className="text-xs leading-relaxed">Triggered by <span className="text-fail">{trace.triggering_stress_condition}</span></span>} />
          <Field k="Before the Fix" v={<><span className="text-fail">{base.failures} / {base.total_runs}</span> normal · <span className="text-fail">{stressCond.failures} / {stressCond.total_runs}</span> stress</>} />
          <Field k="Rejected Quick Fix" v={<>{a1.normal_cert_result.failures} / {fmtN(a1.normal_cert_result.total_runs)} normal · <span className="text-stress">{a1.stress_cert_result.failures} / {fmtN(a1.stress_cert_result.total_runs)}</span> stress</>} />
          <Field k="After the Fix" v={<span className="text-pass">{a2.normal_cert_result.failures} / {fmtN(a2.normal_cert_result.total_runs)} normal · {a2.stress_cert_result.failures} / {fmtN(a2.stress_cert_result.total_runs)} stress</span>} />
          <Field k="95% Confidence Upper Bound" v={<><span className="text-pass">&lt; {pct(a2.upper_bound_95_stress, 2)}</span> <span className="text-xs text-muted-foreground">(Rule of Three) vs {pct(a2.target_limit, 2)} target</span></>} />
          <Field k="Models Used" v={<span className="text-xs">{trace.models_used.bulk_log_reading}<br />{trace.models_used.deep_reasoning}</span>} />
          <Field k="Execution Backend" v={base.execution_backend} />
          <Field k="Attestation" v={<span className="text-primary font-bold">SHA-256 Merkle & HMAC Attested</span>} />
        </dl>
        <div className="formula-band"><span className="font-mono text-[10px] text-muted-foreground">RULE OF THREE / 95% CONFIDENCE</span><p className="font-mono">Upper Bound = 3 / N = {pct(3 / a2.stress_cert_result.total_runs, 2)}<span className="text-muted-foreground"> · N = {fmtN(a2.stress_cert_result.total_runs)}</span></p></div>
        <AttestationBlock trace={trace} seal={attestation} />
      </section>
    <footer className="lab-footer"><span>COINFLIP / STATISTICAL INVESTIGATION LAB</span><span>MEASURE. PERTURB. VERIFY.</span></footer></main>
    </>
  );
}

function Field({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div>
      <dt className="mb-1 text-[10px] uppercase tracking-widest text-muted-foreground">{k}</dt>
      <dd>{v}</dd>
    </div>
  );
}
