export type CausalAnalytics = {
  relative_risk: number | null;
  rate_delta?: number;
  fishers_exact_p_value?: number;
  p_value: number;
  is_statistically_significant: boolean;
  h0_rejected?: boolean;
};

export type Condition = {
  perturbation: string;
  label: string;
  total_runs: number;
  failures: number;
  passes: number;
  failure_rate: number;
  ci_95_lower: number;
  ci_95_upper: number;
  execution_backend: string;
  sample_failure_logs: string[];
  run_dots: boolean[];
  causal_analytics?: CausalAnalytics;
  relative_risk?: number | null;
  p_value?: number;
};
export type CertResult = { total_runs: number; failures: number; failure_rate: number; run_dots: boolean[] };

export type AstAudit = {
  passed_gatekeeper: boolean;
  status_code: string;
  summary: string;
  original_assert_count?: number;
  patched_assert_count?: number;
  assertions_preserved?: boolean;
  no_skip_decorators?: boolean;
  no_bare_exception_swallowing?: boolean;
  sleep_inflation_detected?: boolean;
  synchronization_primitives_detected?: string[];
};

export type SprtTelemetry = {
  enabled?: boolean;
  early_stopped?: boolean;
  decision?: string;
  runs_executed_stress?: number;
  target_runs_stress?: number;
  runs_saved?: number;
  compute_saved_pct?: number;
  log_likelihood_ratio?: number;
  rejection_threshold_b?: number;
  stopped_at?: number;
  planned_runs?: number;
  llr?: number;
  saved_runs?: number;
  saved_percent?: number;
};

export type FixAttempt = {
  attempt_number: number;
  verdict: "REJECTED" | "CERTIFIED";
  fix_title: string;
  root_cause_diagnosis: string;
  git_diff_patch: string;
  normal_cert_result: CertResult;
  stress_cert_result: CertResult;
  upper_bound_95_normal: number;
  upper_bound_95_stress: number;
  target_limit: number;
  rejection_reason: string | null;
  ast_gatekeeper_audit?: AstAudit;
  ast_audit?: AstAudit;
  sprt_telemetry?: SprtTelemetry;
  sprt?: SprtTelemetry;
};
export type StreakPoint = {
  true_failure_rate_pct: number;
  pass_1_run_pct: number;
  pass_10_runs_pct: number;
  pass_100_runs_pct: number;
};

export type RaceTimeline = {
  measured_quiet_worker_ms?: number;
  measured_quiet_assert_ms?: number;
  quiet_margin_ms?: number;
  measured_stress_worker_ms?: number;
  measured_stress_assert_ms?: number;
  stress_race_violation_ms?: number;
  quiet?: { worker_ms: number; assert_ms: number; margin_ms: number };
  busy?: { worker_ms: number; assert_ms: number; margin_ms: number };
  explanation?: string;
};

export type Trace = {
  trace_id: string;
  timestamp_utc: string;
  is_recorded_replay: boolean;
  project_name: string;
  test_identifier: string;
  triggering_stress_condition: string;
  final_verdict: string;
  execution_mode_badge: string;
  models_used: { bulk_log_reading: string; deep_reasoning: string };
  log_summary?: string;
  stage1_baseline: Condition;
  stage2_ledger: Condition[];
  fix_attempts: FixAttempt[];
  streak_curve_data: { points: StreakPoint[]; rule_of_three_bars: { runs: string; bound: string; bound_pct: number }[] };
  is_fallback?: boolean;
  fallback_note?: string;
  evidence_kind?: "illustrative";
  race_timeline?: RaceTimeline;
  race_timeline_profile?: RaceTimeline;
  nemotron_reasoning_trace?: string;
  reasoning_trace?: string;
  attestation?: any;
  cryptographic_attestation?: any;
};

/** Deterministic spread of `fails` failures across `n` runs. */
export function makeDots(n: number, fails: number): boolean[] {
  // Rank indices by a deterministic hash; mark the lowest `fails` as failures.
  const order = Array.from({ length: n }, (_, i) => i).sort(
    (x, y) => Math.sin(x * 12.9898 + fails) * 43758.5453 % 1 - Math.sin(y * 12.9898 + fails) * 43758.5453 % 1,
  );
  const dots = Array<boolean>(n).fill(true);
  for (let k = 0; k < Math.min(fails, n); k++) {
    const index = order[k];
    if (index !== undefined) dots[index] = false;
  }
  return dots;
}

const LOG = "AssertionError: assert worker.status == 'DONE' (was 'RUNNING' after 1.0s sleep)";
const cond = (perturbation: string, label: string, failures: number, lo: number, hi: number): Condition => ({
  perturbation,
  label,
  total_runs: 300,
  failures,
  passes: 300 - failures,
  failure_rate: failures / 300,
  ci_95_lower: lo,
  ci_95_upper: hi,
  execution_backend: "nebius_sandbox",
  sample_failure_logs: [LOG],
  run_dots: makeDots(300, failures),
});
const cert = (failures: number): CertResult => ({
  total_runs: 1000,
  failures,
  failure_rate: failures / 1000,
  run_dots: makeDots(1000, failures),
});

const ledger = [
  cond("baseline", "Normal run (baseline)", 21, 0.0462, 0.1046),
  cond("shuffle_order", "Shuffle the test order", 21, 0.0462, 0.1046),
  cond("seed_change", "Use a different random seed", 18, 0.0383, 0.0928),
  cond("clock_shift", "Shift the clock", 21, 0.0462, 0.1046),
  cond("network_cut", "Cut the network", 21, 0.0462, 0.1046),
  cond("cpu_half_cores", "Halve the CPU cores", 93, 0.2603, 0.3645),
  cond("cpu_heavy_load", "Heavy CPU load (4x busier)", 174, 0.5235, 0.6345),
];

export const FALLBACK_TRACE: Trace = {
  trace_id: "trace-hero-2026",
  timestamp_utc: "2026-10-17T08:30:00Z",
  is_recorded_replay: true,
  project_name: "example-service",
  test_identifier: "example-service::test_worker.py::test_job_finishes",
  triggering_stress_condition: "cpu_heavy_load",
  final_verdict: "PASS",
  execution_mode_badge: "Replaying real recorded execution (2,000+ certification runs + NVIDIA Nemotron 3 Ultra)",
  models_used: {
    bulk_log_reading: "nvidia/Nemotron-3_5-Lightning",
    deep_reasoning: "nvidia/Nemotron-3-Ultra-550b-a55b",
  },
  log_summary:
    "All 369 failure logs share one signature: worker.status was still 'RUNNING' when asserted after a fixed 1.0s sleep. No network, ordering, or seed-related errors found.",
  stage1_baseline: ledger[0] ?? cond("baseline", "Normal run (baseline)", 21, 0.0462, 0.1046),
  stage2_ledger: ledger,
  fix_attempts: [
    {
      attempt_number: 1,
      verdict: "REJECTED",
      fix_title: "AI Agent Quick Fix: increase sleep(1) to sleep(2)",
      root_cause_diagnosis:
        "Naive symptom-hiding fix that increases fixed wait duration without synchronizing on worker completion.",
      git_diff_patch:
        "--- a/test_worker.py\n+++ b/test_worker.py\n@@ -12,2 +12,2 @@\n-    time.sleep(1.0)\n+    time.sleep(2.0)\n     assert worker.status == 'DONE'",
      normal_cert_result: cert(0),
      stress_cert_result: cert(61),
      upper_bound_95_normal: 0.003,
      upper_bound_95_stress: 0.0748,
      target_limit: 0.005,
      rejection_reason:
        "Naive fix detected: passed 1000/1000 runs on a quiet machine (0.0%), but failed 61/1000 runs (6.1%) under CPU stress.",
    },
    {
      attempt_number: 2,
      verdict: "CERTIFIED",
      fix_title: "Coinflip Deterministic Fix: wait for worker completion signal",
      root_cause_diagnosis:
        "Order, seed, clock, and network make no difference. Only CPU pressure spikes failures (31% at half cores, 58% under heavy load). The test races the background worker with a fixed sleep instead of waiting for the completion signal.",
      git_diff_patch:
        "--- a/test_worker.py\n+++ b/test_worker.py\n@@ -12,2 +12,2 @@\n-    time.sleep(1.0)\n+    assert worker.done_event.wait(timeout=5.0), 'Worker timed out'\n     assert worker.status == 'DONE'",
      normal_cert_result: cert(0),
      stress_cert_result: cert(0),
      upper_bound_95_normal: 0.003,
      upper_bound_95_stress: 0.003,
      target_limit: 0.005,
      rejection_reason: null,
    },
  ],
  streak_curve_data: {
    points: Array.from({ length: 21 }, (_, p) => {
      const q = 1 - p / 100;
      return {
        true_failure_rate_pct: p,
        pass_1_run_pct: +(q * 100).toFixed(2),
        pass_10_runs_pct: +(q ** 10 * 100).toFixed(2),
        pass_100_runs_pct: +(q ** 100 * 100).toFixed(2),
      };
    }),
    rule_of_three_bars: [
      { runs: "100 runs", bound: "<3%", bound_pct: 3 },
      { runs: "300 runs", bound: "<1%", bound_pct: 1 },
      { runs: "1,000 runs", bound: "<0.3%", bound_pct: 0.3 },
      { runs: "3,000 runs", bound: "<0.1%", bound_pct: 0.1 },
    ],
  },
};

export async function fetchTrace(): Promise<{ trace: Trace; source: "api" | "fallback" }> {
  for (const url of ["/api/trace", "http://localhost:8000/api/trace"]) {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 2500);
      const r = await fetch(url, { signal: ctrl.signal });
      clearTimeout(t);
      if (!r.ok) continue;
      const j = (await r.json()) as Trace;
      if (j && Array.isArray(j.stage2_ledger)) return { trace: normalize(j), source: "api" };
    } catch {
      /* try next */
    }
  }
  return { trace: FALLBACK_TRACE, source: "fallback" };
}

function normalize(t: Trace): Trace {
  const sc = t.streak_curve_data as unknown;
  if (Array.isArray(sc)) {
    return { ...t, streak_curve_data: { points: sc as StreakPoint[], rule_of_three_bars: FALLBACK_TRACE.streak_curve_data.rule_of_three_bars } };
  }
  return t;
}

export async function runLive(): Promise<{ ok: boolean; data?: Partial<Trace>; error?: string }> {
  for (const url of ["/api/run-live", "http://localhost:8000/api/run-live"]) {
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ runs_per_condition: 30 }),
      });
      if (!r.ok) continue;
      return { ok: true, data: await r.json() };
    } catch {
      /* next */
    }
  }
  return { ok: false, error: "Live sandbox backend unreachable — showing recorded replay." };
}

export const pct = (x: number, d = 1) => `${(x * 100).toFixed(d)}%`;

export const BENCHMARK_CASES = [
  { id: "hero", name: "Background Worker CPU Race", trigger: "cpu_heavy_load" },
  { id: "order_pollution", name: "Global Config Cache Pollution", trigger: "shuffle_order" },
  { id: "seed_sampling", name: "Reservoir Sampler Seed Sensitivity", trigger: "seed_change" },
  { id: "clock_expiry", name: "JWT Token TTL Boundary Race", trigger: "clock_shift" },
] as const;
export type CaseId = typeof BENCHMARK_CASES[number]["id"];

function wilson(failures: number, n: number): [number, number] {
  const p = failures / n, z = 1.959963984540054, denom = 1 + z * z / n;
  const center = (p + z * z / (2 * n)) / denom;
  const half = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom;
  return [Math.max(0, center - half), Math.min(1, center + half)];
}

/** Offline archetype fixtures are demonstrations, not claimed recorded executions. */
export function fallbackForCase(id: CaseId): Trace {
  if (id === "hero") return FALLBACK_TRACE;
  const benchmark = BENCHMARK_CASES.find(c => c.id === id) ?? BENCHMARK_CASES[0];
  const details = {
    order_pollution: { test: "test_config.py::test_default_region", cause: "A previous test mutates a shared configuration cache. Isolate configuration per test and restore global state.", quick: "+    config.region = 'eu'", fix: "+    config = ConfigCache.fresh()" },
    seed_sampling: { test: "test_sampler.py::test_sample_distribution", cause: "A random sample is checked against an exact count. Use a fixed seed for reproducibility and validate the sampling invariant.", quick: "+    random.seed(42)", fix: "+    assert sampler.invariants_hold()" },
    clock_expiry: { test: "test_token.py::test_token_valid", cause: "The assertion races the JWT expiry boundary. Freeze the test clock and explicitly test each side of the TTL boundary.", quick: "+    ttl_seconds = 60", fix: "+    clock.freeze(issued_at + ttl_seconds - 1)" },
  }[id];
  const rows = FALLBACK_TRACE.stage2_ledger.map(c => {
    const f = c.perturbation === benchmark.trigger ? 174 : 18;
    const [lo, hi] = wilson(f, 300);
    return { ...c, failures: f, passes: 300 - f, failure_rate: f / 300, ci_95_lower: lo, ci_95_upper: hi, run_dots: makeDots(300, f), execution_backend: "illustrative_offline_fixture", sample_failure_logs: ["Illustrative fixture — recorded failure logs unavailable."] };
  });
  const baseline = rows[0];
  if (!baseline) return FALLBACK_TRACE;
  return { ...FALLBACK_TRACE, evidence_kind: "illustrative", is_recorded_replay: false, trace_id: `demo-${id}`, project_name: "benchmark-demo", test_identifier: details.test, triggering_stress_condition: benchmark.trigger,
    execution_mode_badge: "Illustrative offline benchmark · not recorded execution", stage1_baseline: baseline, stage2_ledger: rows, log_summary: "Illustrative archetype fixture. Connect the case API to view recorded evidence.",
    fix_attempts: FALLBACK_TRACE.fix_attempts.map((a, i) => ({ ...a, fix_title: i ? "Isolate the underlying invariant" : "Symptom-only workaround", root_cause_diagnosis: details.cause, git_diff_patch: `--- a/${details.test.split("::")[0]}\n+++ b/${details.test.split("::")[0]}\n@@ -1 +1 @@\n-    # flaky assertion setup\n${i ? details.fix : details.quick}`, rejection_reason: i ? null : "Illustrative workaround fails under the triggering perturbation." })) };
}

export async function fetchCaseTrace(id: CaseId, signal?: AbortSignal): Promise<{ trace: Trace; source: "api" | "fallback" }> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 2500);
  const abort = () => ctrl.abort();
  signal?.addEventListener("abort", abort, { once: true });
  try {
    if (signal?.aborted) ctrl.abort();
    const response = await fetch(`/api/traces/${id}`, { signal: ctrl.signal });
    if (response.ok) {
      const value = await response.json() as Trace;
      if (Array.isArray(value.stage2_ledger) && Array.isArray(value.fix_attempts) && value.stage1_baseline && value.streak_curve_data && value.models_used) return { trace: normalize(value), source: "api" };
    }
  } catch { /* explicit offline fixture */ }
  finally { clearTimeout(timer); signal?.removeEventListener("abort", abort); }
  return { trace: fallbackForCase(id), source: "fallback" };
}
