import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, ComposedChart, ErrorBar, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Activity, BadgeCheck, Brain, Cpu, FlaskConical, Loader2, Play, ScrollText, ShieldAlert, ShieldCheck, XCircle } from "lucide-react";
import { FALLBACK_TRACE, fetchTrace, makeDots, pct, runLive, type Trace } from "@/lib/trace";

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
    <section className="rounded-lg border border-border bg-card/80 p-5 backdrop-blur">
      <header className="mb-4 flex items-center gap-3">
        <span className="font-mono text-xs text-primary">{n}</span>
        <span className="text-muted-foreground">{icon}</span>
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      </header>
      {children}
    </section>
  );
}

function Verdict({ v }: { v: "BROKEN" | "REJECTED" | "CERTIFIED" }) {
  const cls = v === "CERTIFIED" ? "border-pass/50 bg-pass/15 text-pass" : v === "REJECTED" ? "border-stress/50 bg-stress/15 text-stress" : "border-fail/50 bg-fail/15 text-fail";
  return <span className={`rounded border px-2 py-0.5 font-mono text-xs font-bold tracking-widest ${cls}`}>{v}</span>;
}

function Dots({ dots, label }: { dots: boolean[]; label: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const fails = dots.filter((d) => !d).length;
  const big = dots.length > 400;
  return (
    <div>
      <div className="mb-1.5 flex justify-between font-mono text-[11px] text-muted-foreground">
        <span>{label}</span>
        <span className={fails ? "text-fail" : "text-pass"}>
          {hover !== null ? `run #${hover + 1}: ${dots[hover] ? "PASS" : "FAIL"}` : `${fails}/${dots.length} failed`}
        </span>
      </div>
      <div className={`grid gap-[2px] ${big ? "grid-cols-[repeat(50,minmax(0,1fr))]" : "grid-cols-[repeat(30,minmax(0,1fr))]"}`} onMouseLeave={() => setHover(null)}>
        {dots.map((d, i) => (
          <span key={i} onMouseEnter={() => setHover(i)} className={`aspect-square rounded-full transition-transform hover:scale-150 ${d ? "bg-pass/80" : "bg-fail"}`} />
        ))}
      </div>
    </div>
  );
}

function Diff({ patch, attemptNumber }: { patch: string; attemptNumber?: number }) {
  return (
    <pre className="whitespace-pre-wrap break-words rounded-md border border-border bg-background p-3 font-mono text-xs leading-relaxed overflow-x-hidden">
      {patch.split("\n").map((l, i) => {
        let highlightClass = "";
        if (attemptNumber === 1 && l.includes("time.sleep")) {
          highlightClass = "bg-fail/20 text-fail font-semibold rounded px-1 -mx-1 border-l-2 border-fail";
        } else if (attemptNumber === 2 && (l.includes("wait_for_completion") || l.includes("done_event"))) {
          highlightClass = "bg-pass/20 text-pass font-semibold rounded px-1 -mx-1 border-l-2 border-pass";
        } else if (l.startsWith("+++") || l.startsWith("---")) {
          highlightClass = "text-muted-foreground";
        } else if (l.startsWith("+")) {
          highlightClass = "bg-pass/10 text-pass";
        } else if (l.startsWith("-")) {
          highlightClass = "bg-fail/10 text-fail";
        } else if (l.startsWith("@@")) {
          highlightClass = "text-normal";
        } else {
          highlightClass = "text-foreground/80";
        }
        return <div key={i} className={`px-1 py-0.5 ${highlightClass}`}>{l || " "}</div>;
      })}
    </pre>
  );
}

function Dashboard() {
  const [trace, setTrace] = useState<Trace>(FALLBACK_TRACE);
  const [source, setSource] = useState<"loading" | "api" | "fallback">("loading");
  const [live, setLive] = useState<{ busy: boolean; note?: string | undefined }>({ busy: false });

  useEffect(() => {
    fetchTrace().then(({ trace, source }) => { setTrace(trace); setSource(source); });
  }, []);

  const onLive = async () => {
    setLive({ busy: true });
    const r = await runLive();
    if (r.ok && r.data) {
      if (r.data.stage2_ledger) setTrace((t) => ({ ...t, ...r.data } as Trace));
      setLive({ busy: false, note: r.data.is_fallback ? r.data.fallback_note ?? "Backend returned fallback data." : "Live mini-batch complete (30 runs/condition)." });
    } else setLive({ busy: false, note: r.error });
  };

  const a1 = trace.fix_attempts[0]!;
  const a2 = trace.fix_attempts[1] ?? a1;
  const stressCond = trace.stage2_ledger.find((c) => c.perturbation === trace.triggering_stress_condition) ?? trace.stage2_ledger.at(-1)!;
  const base = trace.stage1_baseline;
  const origStressDots = useMemo(() => stressCond.run_dots?.length ? stressCond.run_dots : makeDots(stressCond.total_runs, stressCond.failures), [stressCond]);

  const ledgerData = trace.stage2_ledger.map((c) => ({
    label: c.label, key: c.perturbation, rate: +(c.failure_rate * 100).toFixed(1),
    err: [+((c.failure_rate - c.ci_95_lower) * 100).toFixed(1), +((c.ci_95_upper - c.failure_rate) * 100).toFixed(1)],
    lo: c.ci_95_lower, hi: c.ci_95_upper, f: c.failures, n: c.total_runs,
  }));
  const verdictData = [
    { name: "Original Test", normal: base.failure_rate * 100, stress: stressCond.failure_rate * 100 },
    { name: "Rejected Quick Fix", normal: a1.normal_cert_result.failure_rate * 100, stress: a1.stress_cert_result.failure_rate * 100 },
    { name: "Certified Fix", normal: a2.normal_cert_result.failure_rate * 100, stress: a2.stress_cert_result.failure_rate * 100 },
  ];
  const fmtN = (n: number) => n.toLocaleString("en-US");

  return (
    <main className="mx-auto max-w-7xl space-y-6 px-4 py-8 md:px-8">
      {/* 1. Header */}
      <header className="rounded-lg border border-border bg-card/80 p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <div className="grid h-10 w-10 place-items-center rounded-full border-2 border-primary font-mono text-lg font-bold text-primary">¢</div>
              <h1 className="font-mono text-3xl font-bold tracking-tight">COINFLIP</h1>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">Statistical Flaky-Test Investigator &amp; Verifier · Nebius × NVIDIA Hackathon</p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <button onClick={onLive} disabled={live.busy} className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition hover:brightness-110 disabled:opacity-60">
              {live.busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              Run Live Sandbox Mini-Batch (30 runs)
            </button>
            {live.note && <p className="max-w-sm text-right font-mono text-xs text-stress">{live.note}</p>}
          </div>
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/40 bg-primary/10 px-3 py-1 text-xs text-primary">
            <Activity className="h-3.5 w-3.5" /> {trace.execution_mode_badge}
          </span>
          <span className="rounded-full border border-border px-3 py-1 font-mono text-xs text-muted-foreground">
            data: {source === "loading" ? "connecting…" : source === "api" ? "live backend" : "built-in trace"}
          </span>
        </div>
        <dl className="mt-4 grid gap-3 font-mono text-xs md:grid-cols-3">
          <div><dt className="text-muted-foreground">project</dt><dd>{trace.project_name}</dd></div>
          <div className="md:col-span-2"><dt className="text-muted-foreground">test</dt><dd className="break-all">{trace.test_identifier}</dd></div>
        </dl>
      </header>

      {/* 2. Dot matrix */}
      <Panel n="01" title="The Coin-Toss Dot Matrix" icon={<FlaskConical className="h-4 w-4" />}>
        <div className="grid gap-5 lg:grid-cols-3">
          {[
            { t: "Original Test", v: "BROKEN" as const, n: base.run_dots, s: origStressDots },
            { t: "Attempt 1 · Naive Quick Fix", v: "REJECTED" as const, n: a1.normal_cert_result.run_dots, s: a1.stress_cert_result.run_dots },
            { t: "Attempt 2 · Coinflip Fix", v: "CERTIFIED" as const, n: a2.normal_cert_result.run_dots, s: a2.stress_cert_result.run_dots },
          ].map((x) => (
            <div key={x.t} className="space-y-4 rounded-md border border-border bg-background/60 p-4">
              <div className="flex items-center justify-between"><h3 className="text-sm font-semibold">{x.t}</h3><Verdict v={x.v} /></div>
              <Dots dots={x.n} label="Normal machine" />
              <Dots dots={x.s} label="CPU stress" />
            </div>
          ))}
        </div>
      </Panel>

      {/* 3. Ledger */}
      <Panel n="02" title="Stage 2 · Experiment Ledger" icon={<Cpu className="h-4 w-4" />}>
        <div className="grid gap-5 lg:grid-cols-5">
          <div className="h-[380px] lg:col-span-3">
            <ResponsiveContainer>
              <BarChart data={ledgerData} layout="vertical" margin={{ left: 20, right: 30 }}>
                <CartesianGrid stroke={C.grid} strokeDasharray="3 3" horizontal={false} />
                <XAxis
                  type="number"
                  stroke={C.muted}
                  fontSize={11}
                  domain={[0, 100]}
                  ticks={[0, 20, 40, 60, 80, 100]}
                  tickFormatter={(v: number) => `${Number(v).toFixed(0)}%`}
                />
                <YAxis type="category" dataKey="label" width={170} stroke={C.muted} fontSize={11} />
                <Tooltip
                  {...tip}
                  cursor={{ fill: "var(--accent)" }}
                  formatter={(v: number, _n, p) => [
                    `${Number(v).toFixed(1)}% (${p.payload.f}/${p.payload.n}) · CI ${pct(p.payload.lo, 1)}–${pct(p.payload.hi, 1)}`,
                    "failure rate",
                  ]}
                />
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
          <div className="space-y-4 lg:col-span-2">
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

      {/* 4. Verdict comparison + diff + streak */}
      <Panel n="03" title="Stage 4 · Fix Verdicts" icon={<ShieldAlert className="h-4 w-4" />}>
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
                <Bar dataKey="stress" name="Busy Machine / CPU Stress" fill={C.stress} radius={[4, 4, 0, 0]} />
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
        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          {[a1, a2].map((a) => (
            <div key={a.attempt_number} className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-sm font-semibold">Attempt {a.attempt_number} · {a.fix_title}</h3>
                <Verdict v={a.verdict} />
              </div>
              <Diff patch={a.git_diff_patch} attemptNumber={a.attempt_number} />
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
      <section className="relative overflow-hidden rounded-lg border-2 border-pass/60 bg-card p-8">
        <div className="pointer-events-none absolute -right-10 -top-10 h-56 w-56 rounded-full border-[14px] border-pass/10" />
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-dashed border-border pb-5">
          <div className="flex items-center gap-3">
            <ShieldCheck className="h-10 w-10 text-pass" />
            <div>
              <p className="font-mono text-xs tracking-[0.3em] text-muted-foreground">OFFICIAL</p>
              <h2 className="font-mono text-2xl font-bold">Coinflip Certificate</h2>
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
          <Field k="Root Cause Found" v={<span className="text-xs leading-relaxed">Race on fixed sleep; triggered by <span className="text-fail">{trace.triggering_stress_condition}</span></span>} />
          <Field k="Before the Fix" v={<><span className="text-fail">{base.failures} / {base.total_runs}</span> normal · <span className="text-fail">{stressCond.failures} / {stressCond.total_runs}</span> stress</>} />
          <Field k="Rejected Quick Fix" v={<>{a1.normal_cert_result.failures} / {fmtN(a1.normal_cert_result.total_runs)} normal · <span className="text-stress">{a1.stress_cert_result.failures} / {fmtN(a1.stress_cert_result.total_runs)}</span> stress</>} />
          <Field k="After the Fix" v={<span className="text-pass">{a2.normal_cert_result.failures} / {fmtN(a2.normal_cert_result.total_runs)} normal · {a2.stress_cert_result.failures} / {fmtN(a2.stress_cert_result.total_runs)} stress</span>} />
          <Field k="95% Confidence Upper Bound" v={<><span className="text-pass">&lt; {pct(a2.upper_bound_95_stress, 2)}</span> <span className="text-xs text-muted-foreground">(Rule of Three) vs {pct(a2.target_limit, 2)} target</span></>} />
          <Field k="Models Used" v={<span className="text-xs">{trace.models_used.bulk_log_reading}<br />{trace.models_used.deep_reasoning}</span>} />
          <Field k="Execution Backend" v={base.execution_backend} />
        </dl>
      </section>
    </main>
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
