import { webcrypto } from "node:crypto";
import { describe, expect, it, vi, afterEach, beforeEach } from "vitest";
import { FALLBACK_TRACE, fallbackForCase, fetchCaseTrace, BENCHMARK_CASES } from "@/lib/trace";
import { canonicalJSON, fisherExact, relativeRisk, holmBonferroniAdjust, sealTrace, sha256, verifyTrace, PROFILER_EXAMPLE, SPRT_EXAMPLE } from "@/lib/telemetry";

afterEach(() => vi.unstubAllGlobals());
beforeEach(() => vi.stubGlobal("crypto", webcrypto));

describe("Scientific comparisons from recorded counts", () => {
  const baseline = FALLBACK_TRACE.stage1_baseline;
  it("computes two-sided Fisher significance for 174/300 versus 21/300", () => {
    const row = { failures: 174, total_runs: 300 };
    expect(fisherExact(baseline, row) / 5.916791829377922e-44).toBeCloseTo(1, 9);
    expect(relativeRisk(baseline, row)).toBeCloseTo(174 / 21, 12);
  });
  it("does not label the 93/300 CPU row noise", () => {
    expect(fisherExact(baseline, { failures: 93, total_runs: 300 }) / 2.6334530856034697e-14).toBeCloseTo(1, 9);
    expect(relativeRisk(baseline, { failures: 93, total_runs: 300 })).toBeCloseTo(93 / 21, 12);
  });
  it("handles identical and zero-failure controls", () => {
    expect(fisherExact(baseline, baseline)).toBeCloseTo(1);
    expect(relativeRisk({ failures: 0, total_runs: 300 }, { failures: 0, total_runs: 300 })).toBeNull();
    expect(relativeRisk({ failures: 0, total_runs: 300 }, baseline)).toBe(Infinity);
  });
});

describe("Offline archetypes", () => {
  it("preserves the hero and labels new fixtures illustrative", () => {
    expect(fallbackForCase("hero")).toBe(FALLBACK_TRACE);
    for (const benchmark of BENCHMARK_CASES.slice(1)) {
      const trace = fallbackForCase(benchmark.id);
      expect(trace.evidence_kind).toBe("illustrative");
      expect(trace.triggering_stress_condition).toBe(benchmark.trigger);
      expect(trace.stage2_ledger.find(c => c.perturbation === benchmark.trigger)?.failures).toBe(174);
      expect(trace.stage2_ledger.every(c => c.run_dots.filter(d => !d).length === c.failures)).toBe(true);
    }
  });
  it("requests the named case endpoint and falls back when offline", async () => {
    const fetch = vi.fn().mockRejectedValue(new Error("offline"));
    vi.stubGlobal("fetch", fetch);
    const result = await fetchCaseTrace("clock_expiry");
    expect(fetch.mock.calls[0]?.[0]).toBe("/api/traces/clock_expiry");
    expect(result.trace.triggering_stress_condition).toBe("clock_shift");
    expect(result.source).toBe("fallback");
  });
  it("reads supplied API evidence without replacing it with examples", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => FALLBACK_TRACE }));
    const result = await fetchCaseTrace("hero");
    expect(result.source).toBe("api");
    expect(result.trace.stage1_baseline.failures).toBe(21);
  });
});

describe("Explicitly illustrative profiler and sequential stop", () => {
  it("uses the supplied micro-timing examples without mutating evidence", () => {
    expect(PROFILER_EXAMPLE.quiet.worker_ms).toBe(4.10);
    expect(PROFILER_EXAMPLE.quiet.assert_ms - PROFILER_EXAMPLE.quiet.worker_ms).toBeCloseTo(0.72);
    expect(PROFILER_EXAMPLE.busy.assert_ms - PROFILER_EXAMPLE.busy.worker_ms).toBeCloseTo(-6.58);
    expect(FALLBACK_TRACE.fix_attempts[0]?.git_diff_patch).toContain("time.sleep(2.0)");
  });
  it("shows the 35/1000 early stop only as a separate example", () => {
    expect(SPRT_EXAMPLE.planned_runs - SPRT_EXAMPLE.stopped_at).toBe(965);
    expect(SPRT_EXAMPLE.saved_percent).toBe(96.5);
    expect(SPRT_EXAMPLE.llr).toBe(14.8);
    expect(FALLBACK_TRACE.fix_attempts[0]?.stress_cert_result.total_runs).toBe(1000);
  });
});

describe("SHA-256 client integrity", () => {
  it("uses standard SHA-256 and deterministic object ordering", async () => {
    expect(await sha256("abc")).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    expect(canonicalJSON({ b: 2, a: 1 })).toBe(canonicalJSON({ a: 1, b: 2 }));
  });
  it("verifies the original and rejects changed counts or patches", async () => {
    const seal = await sealTrace(FALLBACK_TRACE);
    expect(await verifyTrace(FALLBACK_TRACE, seal)).toBe(true);
    const changed = structuredClone(FALLBACK_TRACE);
    const row = changed.stage2_ledger[0];
    if (!row) throw new Error("Missing baseline");
    row.failures = 22;
    expect(await verifyTrace(changed, seal)).toBe(false);
    const patchChanged = structuredClone(FALLBACK_TRACE);
    const fix = patchChanged.fix_attempts[1];
    if (!fix) throw new Error("Missing fix");
    fix.git_diff_patch += "\n# changed";
    expect(await verifyTrace(patchChanged, seal)).toBe(false);
  });
});

describe("Holm-Bonferroni adjustment", () => {
  it("enforces step-down monotonicity and correct bounds", () => {
    const raw = [0.005, 0.04, 0.02, 0.10];
    const adj = holmBonferroniAdjust(raw);
    expect(adj.length).toBe(4);
    // sorted: 0.005 (x4 = 0.02), 0.02 (x3 = 0.06), 0.04 (x2 = 0.08), 0.10 (x1 = 0.10)
    expect(adj[0]).toBeCloseTo(0.02);
    expect(adj[2]).toBeCloseTo(0.06);
    expect(adj[1]).toBeCloseTo(0.08);
    expect(adj[3]).toBeCloseTo(0.10);
    expect(holmBonferroniAdjust([])).toEqual([]);
  });
});

describe("Phase 7 scientific UI telemetry badges and labels", () => {
  it("renders provenance badges correctly", async () => {
    const React = (await import("react")).default;
    const { FixSourceBadge } = await import("@/components/scientific-telemetry");
    const { render, screen } = await import("@testing-library/react");
    const { unmount } = render(
      React.createElement(
        "div",
        null,
        React.createElement(FixSourceBadge, { source: "nemotron_live" }),
        React.createElement(FixSourceBadge, { source: "naive_baseline_fixture" }),
        React.createElement(FixSourceBadge, { source: "offline_fallback_fixture" })
      )
    );
    expect(screen.getByText(/LIVE NEMOTRON PATCH/i)).toBeInTheDocument();
    expect(screen.getByText(/REFERENCE NAIVE AGENT FIXTURE/i)).toBeInTheDocument();
    expect(screen.getByText(/OFFLINE FALLBACK PATCH \(API TIMEOUT\)/i)).toBeInTheDocument();
    unmount();
  });

  it("renders AST Static Anti-Cheat Gatekeeper and IN_PROGRESS_CONTINUE in SPRT", async () => {
    const React = (await import("react")).default;
    const { GatekeeperAudit } = await import("@/components/scientific-telemetry");
    const { render, screen } = await import("@testing-library/react");
    const inProgressAttempt = {
      ...FALLBACK_TRACE.fix_attempts[0]!,
      sprt_telemetry: {
        enabled: true,
        status: "IN_PROGRESS_CONTINUE",
        decision: "IN_PROGRESS_CONTINUE",
        llr: 0.84,
        stopped_at: 25,
      },
    };
    const { unmount } = render(React.createElement(GatekeeperAudit, { attempt: inProgressAttempt, trace: FALLBACK_TRACE }));
    expect(screen.getAllByText(/AST Static Anti-Cheat Gatekeeper/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/IN_PROGRESS_CONTINUE/i).length).toBeGreaterThan(0);
    unmount();
  });

  it("renders SHA-256 Merkle & HMAC Attested and displays ATTESTATION FAILED — TRACE TAMPERED when tampered", async () => {
    const React = (await import("react")).default;
    const { AttestationBlock } = await import("@/components/scientific-telemetry");
    const { render, screen, fireEvent, waitFor } = await import("@testing-library/react");
    const seal = await sealTrace(FALLBACK_TRACE);

    // Mock fetch returning verified: false (tampering detected)
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ verified: false, reason: "Tampering detected: failures count mismatch" }),
    }));

    const { unmount } = render(React.createElement(AttestationBlock, { trace: FALLBACK_TRACE, seal }));
    expect(screen.getByText(/SHA-256 Merkle & HMAC Attested/i)).toBeInTheDocument();

    const verifyBtn = screen.getByRole("button", { name: /Verify Cryptographic Signature/i });
    fireEvent.click(verifyBtn);

    await waitFor(() => {
      expect(screen.getByText(/ATTESTATION FAILED — TRACE TAMPERED/i)).toBeInTheDocument();
    });
    unmount();
  });

  it("displays holm_adjusted_p_value in CausalLedger", async () => {
    const React = (await import("react")).default;
    const { CausalLedger } = await import("@/components/scientific-telemetry");
    const { render, screen } = await import("@testing-library/react");
    const { unmount } = render(React.createElement(CausalLedger, { trace: FALLBACK_TRACE }));
    expect(screen.getAllByText(/holm_adjusted_p_value/i).length).toBeGreaterThan(0);
    unmount();
  });
});