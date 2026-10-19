import type { Condition, Trace } from "@/lib/trace";

function logChoose(n: number, k: number): number {
  if (k < 0 || k > n) return -Infinity;
  let result = 0;
  for (let i = 1; i <= Math.min(k, n - k); i++) result += Math.log(n - i + 1) - Math.log(i);
  return result;
}

/** Two-sided Fisher exact test: sum tables at least as unlikely as the observed table. */
export function fisherExact(base: Pick<Condition, "failures" | "total_runs">, row: Pick<Condition, "failures" | "total_runs">): number {
  const failures = base.failures + row.failures;
  const total = base.total_runs + row.total_runs;
  const logP = (k: number) => logChoose(failures, k) + logChoose(total - failures, row.total_runs - k) - logChoose(total, row.total_runs);
  const observed = logP(row.failures);
  let p = 0;
  for (let k = Math.max(0, row.total_runs - (total - failures)); k <= Math.min(row.total_runs, failures); k++) {
    const value = logP(k);
    if (value <= observed + 1e-9) p += Math.exp(value);
  }
  return Math.min(1, p);
}

export function relativeRisk(base: Pick<Condition, "failures" | "total_runs">, row: Pick<Condition, "failures" | "total_runs">): number | null {
  if (!base.total_runs || !row.total_runs) return null;
  if (!base.failures) return row.failures ? Infinity : null;
  return (row.failures / row.total_runs) / (base.failures / base.total_runs);
}

export function canonicalJSON(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
  if (Array.isArray(value)) return `[${value.map(canonicalJSON).join(",")}]`;
  const object = value as Record<string, unknown>;
  return `{${Object.keys(object).filter(k => object[k] !== undefined).sort().map(k => `${JSON.stringify(k)}:${canonicalJSON(object[k])}`).join(",")}}`;
}

export async function sha256(value: string): Promise<string> {
  const hash = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, "0")).join("");
}

export type Attestation = {
  algorithm: "SHA-256";
  scope: "client-side integrity; not a signed execution attestation";
  ledger_merkle_root: string;
  patch_diff_sha256: string;
  trace_sha256: string;
  execution_backend: string;
};

export async function sealTrace(trace: Trace): Promise<Attestation> {
  let leaves = await Promise.all(trace.stage2_ledger.map(row => sha256(`leaf:${canonicalJSON(row)}`)));
  if (!leaves.length) leaves = [await sha256("empty-ledger")];
  while (leaves.length > 1) {
    const parents: Promise<string>[] = [];
    for (let i = 0; i < leaves.length; i += 2) parents.push(sha256(`node:${leaves[i]}:${leaves[i + 1] ?? leaves[i]}`));
    leaves = await Promise.all(parents);
  }
  const patch = trace.fix_attempts.find(a => a.verdict === "CERTIFIED")?.git_diff_patch ?? "";
  return {
    algorithm: "SHA-256", scope: "client-side integrity; not a signed execution attestation",
    ledger_merkle_root: leaves[0] ?? "", patch_diff_sha256: await sha256(patch),
    trace_sha256: await sha256(canonicalJSON(trace)), execution_backend: trace.stage1_baseline.execution_backend,
  };
}

export async function verifyTrace(trace: Trace, expected: Attestation): Promise<boolean> {
  const actual = await sealTrace(trace);
  return actual.ledger_merkle_root === expected.ledger_merkle_root && actual.patch_diff_sha256 === expected.patch_diff_sha256 && actual.trace_sha256 === expected.trace_sha256 && actual.execution_backend === expected.execution_backend;
}

export const PROFILER_EXAMPLE = {
  quiet: { worker_ms: 4.10, assert_ms: 4.82, margin_ms: 0.72 },
  busy: { worker_ms: 11.43, assert_ms: 4.85, margin_ms: -6.58 },
};
export const SPRT_EXAMPLE = { stopped_at: 35, planned_runs: 1000, llr: 14.8, saved_runs: 965, saved_percent: 96.5 };