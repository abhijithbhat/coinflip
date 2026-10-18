import { describe, expect, it } from "vitest";
import { FALLBACK_TRACE } from "@/lib/trace";

describe("Recorded evidence preservation", () => {
  it("retains the recorded baseline and perturbation evidence", () => {
    expect(FALLBACK_TRACE.stage1_baseline.failures).toBe(21);
    expect(FALLBACK_TRACE.stage1_baseline.total_runs).toBe(300);
    expect(FALLBACK_TRACE.stage2_ledger.map(c => c.failures)).toEqual([21, 21, 18, 21, 21, 93, 174]);
    expect(FALLBACK_TRACE.stage2_ledger.at(-1)?.failure_rate).toBe(0.58);
  });
  it("retains certification counts and statistical bounds", () => {
    const [rejected, certified] = FALLBACK_TRACE.fix_attempts;
    expect(rejected?.stress_cert_result.failures).toBe(61);
    expect(certified?.normal_cert_result).toMatchObject({ failures: 0, total_runs: 1000 });
    expect(certified?.stress_cert_result).toMatchObject({ failures: 0, total_runs: 1000 });
    expect(certified?.upper_bound_95_stress).toBe(0.003);
    expect(certified?.target_limit).toBe(0.005);
  });
  it("retains patches rather than substituting visual-brief examples", () => {
    expect(FALLBACK_TRACE.fix_attempts[0]?.git_diff_patch).toContain("+    time.sleep(2.0)");
    expect(FALLBACK_TRACE.fix_attempts[1]?.git_diff_patch).toContain("+    assert worker.done_event.wait(timeout=5.0), 'Worker timed out'");
  });
});