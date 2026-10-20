import { useEffect, useRef, useState } from "react";
import { Activity, ArrowDown, Check, Copy, Download, Loader2, Play, Radio, Cpu, ChevronDown, FlaskConical as FlaskIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { BENCHMARK_CASES, type CaseId, type Trace } from "@/lib/trace";
import type { Attestation } from "@/lib/telemetry";

const themes = [
  { id: "porcelain-signal", name: "Porcelain & Signal Blue" },
  { id: "graphite-lime", name: "Graphite & Lime" },
  { id: "berry-vanilla", name: "Berry & Vanilla" },
  { id: "phantom-ice", name: "Phantom & Ice" },
  { id: "butter-iris", name: "Butter & Iris" },
];

export function CommandBar({ trace, busy, note, onLive, caseId, caseBusy, onCase }: { trace: Trace; busy: boolean; note?: string | undefined; onLive: () => void; caseId: CaseId; caseBusy: boolean; onCase: (id: CaseId) => void }) {
  const [theme, setTheme] = useState("porcelain-signal");
  const [open, setOpen] = useState(false);
  const [caseOpen, setCaseOpen] = useState(false);
  const [mode, setMode] = useState("replay");

  const caseRef = useRef<HTMLDivElement>(null);
  const themeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let saved: string | null = null;
    try { saved = localStorage.getItem("coinflip-theme"); if (saved === "olive-butter") saved = "butter-iris"; } catch { /* storage unavailable */ }
    const chosen = themes.some(t => t.id === saved) && saved ? saved : "porcelain-signal";
    setTheme(chosen); document.documentElement.dataset['theme'] = chosen;
    document.documentElement.classList.remove("dark");
  }, []);

  useEffect(() => {
    if (!caseOpen && !open) return;

    function handleClickOutside(event: MouseEvent | TouchEvent) {
      const target = event.target as Node | null;
      if (!target) return;

      if (caseOpen && caseRef.current && !caseRef.current.contains(target)) {
        setCaseOpen(false);
      }
      if (open && themeRef.current && !themeRef.current.contains(target)) {
        setOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setCaseOpen(false);
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("touchstart", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("touchstart", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [caseOpen, open]);

  function choose(id: string) {
    setTheme(id); setOpen(false); document.documentElement.dataset['theme'] = id;
    try { localStorage.setItem("coinflip-theme", id); } catch { /* storage unavailable */ }
  }
  return <header className="command-bar">
    <div className="command-inner">
      <a href="#" className="brand-lockup"><span className="brand-mark">c<span>f</span></span><span><strong className="font-display text-xl">coinflip<span className="text-primary">.</span></strong><span className="brand-subtitle">STATISTICAL INVESTIGATION LAB</span></span></a>
      <div className="command-actions flex flex-wrap items-center gap-3">
        <div className="relative" ref={caseRef}>
          <Button variant="outline" size="sm" className="case-selector bg-card" aria-label="Case Selector" aria-expanded={caseOpen} disabled={busy} onClick={() => { setCaseOpen(prev => !prev); setOpen(false); }}>{caseBusy ? <Loader2 className="animate-spin" /> : <FlaskIcon />}<span>{BENCHMARK_CASES.find(c => c.id === caseId)?.name}</span><ChevronDown /></Button>
          {caseOpen && <div className="theme-menu case-menu" role="group" aria-label="Benchmark cases">{BENCHMARK_CASES.map(c => <Button key={c.id} variant="ghost" className="w-full justify-start" aria-pressed={caseId === c.id} onClick={() => { setCaseOpen(false); onCase(c.id); }}>{c.name}{caseId === c.id && <Check className="ml-auto" />}</Button>)}</div>}
        </div>
        <div className="relative" ref={themeRef}>
          <Button variant="outline" size="sm" className="rounded-full bg-card" aria-expanded={open} onClick={() => { setOpen(prev => !prev); setCaseOpen(false); }}><span className="theme-swatch" data-palette={theme} />{themes.find(t => t.id === theme)?.name}<ChevronDown /></Button>
          {open && <div className="theme-menu" role="group" aria-label="Design Studio">{themes.map(t => <Button key={t.id} variant="ghost" className="w-full justify-start" onClick={() => choose(t.id)} aria-pressed={theme === t.id}><span className="theme-swatch" data-palette={t.id} />{t.name}{theme === t.id && <Check className="ml-auto" />}</Button>)}</div>}
        </div>
        <div className="segmented" aria-label="Execution mode">
          <Button variant="ghost" size="sm" aria-pressed={mode === "replay"} onClick={() => setMode("replay")}><Activity />Replay</Button>
          <Button variant="ghost" size="sm" aria-pressed={mode === "live"} onClick={() => setMode("live")}><Radio />Live sandbox</Button>
        </div>
        {mode === "replay" ? (
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-medium bg-secondary text-secondary-foreground border border-border">
              <span className="status-dot" />
              Attested 2,000-Run Corpus
            </span>
            <Button variant="outline" size="sm" onClick={() => setMode("live")}>
              Switch to Live Sandbox →
            </Button>
          </div>
        ) : (
          <Button size="sm" onClick={onLive} disabled={busy || caseBusy}>
            {busy ? <Loader2 className="animate-spin" /> : <Play />}
            {busy ? "Running live mini-batch…" : "▶ Run Live Mini-Batch (30 runs)"}
          </Button>
        )}
      </div>
    </div>
    <div className="telemetry-strip"><span className="telemetry-label"><span className="status-dot" /> PLATFORM TELEMETRY</span><span><Cpu />Nebius Token Factory</span><span>Sandboxes (ConTree)</span><span title="Log Reader">{trace.models_used.bulk_log_reading}<small>LOG READER</small></span><span title="Root-Cause & Patch Engine">{trace.models_used.deep_reasoning}<small>PATCH ENGINE</small></span></div>
    {busy && (
      <div className="live-progress-bar bg-primary/10 border-t border-primary/20 px-6 py-1.5 flex items-center justify-between text-xs font-mono text-primary animate-pulse">
        <span className="flex items-center gap-2">
          <Loader2 className="animate-spin w-3.5 h-3.5" />
          <span>Executing Live Sandbox ({BENCHMARK_CASES.find(c => c.id === caseId)?.name}): Measuring baseline &amp; running stress perturbations...</span>
        </span>
        <span className="opacity-75 font-mono">~10-12s</span>
      </div>
    )}
    {busy && <div className="live-progress" />}
    {note && <p role="status" className="border-t border-border px-6 py-2 font-mono text-xs text-stress">{note}</p>}
  </header>;
}

export function Pipeline() {
  const [active, setActive] = useState("01");
  useEffect(() => {
    const observer = new IntersectionObserver(entries => {
      const entry = entries.find(e => e.isIntersecting);
      if (entry) setActive(entry.target.id.replace("stage-", ""));
    }, { rootMargin: "-15% 0px -55% 0px" });
    document.querySelectorAll("[id^=stage-]").forEach(e => observer.observe(e));
    return () => observer.disconnect();
  }, []);
  return <nav className="pipeline" aria-label="Scientific workflow">{["Measure", "Experiment", "Find & Fix", "Certify", "Report"].map((name, i) => {
    const n = `0${i + 1}`;
    return <Button key={name} variant="ghost" aria-current={active === n ? "step" : undefined} onClick={() => { setActive(n); document.getElementById(`stage-${n}`)?.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" }); }}><span className="font-mono text-xs">{n}</span><span>{name}</span><ArrowDown className="ml-auto" /></Button>;
  })}</nav>;
}

export function Dots({ dots, label }: { dots: boolean[]; label: string }) {
  const [filter, setFilter] = useState(false);
  const [hover, setHover] = useState<number | null>(null);
  const failures = dots.filter(d => !d).length;
  return <div className="dot-instrument">
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><span className="font-mono text-[10px] uppercase text-muted-foreground">{label}</span><div className="segmented dot-filter"><Button size="sm" variant="ghost" aria-pressed={!filter} onClick={() => setFilter(false)}>All Runs</Button><Button size="sm" variant="ghost" aria-pressed={filter} onClick={() => setFilter(true)}>Highlight Failures</Button></div></div>
    <div className="mb-3 flex items-baseline justify-between"><strong className={`font-mono text-xl ${failures ? "text-fail" : "text-pass"}`}>{(failures / dots.length * 100 || 0).toFixed(1)}<span className="text-xs">%</span></strong><span className="font-mono text-[11px] text-muted-foreground">{failures.toLocaleString("en-US")} / {dots.length.toLocaleString("en-US")} FAILED</span></div>
    <div className={`dot-matrix ${filter ? "highlight-failures" : ""}`} onMouseLeave={() => setHover(null)}>{dots.map((pass, i) => <span key={i} tabIndex={0} onFocus={() => setHover(i)} onBlur={() => setHover(null)} onMouseEnter={() => setHover(i)} title={`Run #${i + 1} · Status: ${pass ? "PASS" : "FAIL"} · ${label}`} aria-label={`Run #${i + 1}, ${pass ? "PASS" : "FAIL"}, ${label}`} className={`dot-cell ${pass ? "dot-pass" : "dot-fail"}`} />)}</div>
    <div className="dot-readout font-mono text-[10px] text-muted-foreground" aria-live="polite">{hover === null ? <><span className="text-pass">●</span> PASS <span className="ml-3 text-fail">●</span> FAIL</> : `RUN #${hover + 1} // STATUS: ${dots[hover] ? "PASS" : "FAIL"} // ${label.toUpperCase()}`}</div>
  </div>;
}

export function Diff({ patch }: { patch: string }) {
  const [status, setStatus] = useState("Copy patch");
  return <div className="ide-diff"><div className="ide-bar"><span className="flex items-center gap-2"><span className="status-dot" />PATCH DIFF <span className="text-muted-foreground">/ unified</span></span><Button size="sm" variant="ghost" onClick={async () => { try { await navigator.clipboard.writeText(patch); setStatus("Copied"); } catch { setStatus("Copy failed"); } setTimeout(() => setStatus("Copy patch"), 2000); }}><Copy />{status}</Button></div><pre className="overflow-x-auto py-3 font-mono text-xs leading-7">{patch.split("\n").map((line, i) => <div key={i} className={`diff-line ${line.startsWith("+++") || line.startsWith("---") ? "text-muted-foreground" : line.startsWith("+") ? "bg-pass/10 text-pass" : line.startsWith("-") ? "bg-fail/10 text-fail" : line.startsWith("@@") ? "text-primary" : "text-foreground"}`}><span className="line-number">{i + 1}</span><span>{line || " "}</span></div>)}</pre></div>;
}

export function CertificateActions({ trace, attestation }: { trace: Trace; attestation: Attestation | null }) {
  const [status, setStatus] = useState("Copy GitHub PR Verification Badge");
  return <div className="mt-8 flex flex-wrap gap-3 border-t border-border pt-5"><Button variant="outline" disabled={!attestation} onClick={() => { const url = URL.createObjectURL(new Blob([JSON.stringify({ ...trace, attestation }, null, 2)], { type: "application/json" })); const a = document.createElement("a"); a.href = url; a.download = `coinflip-${trace.trace_id}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }}><Download />Export Certificate JSON</Button><Button variant="outline" onClick={async () => { const fix = trace.fix_attempts.find(a => a.verdict === "CERTIFIED"); const bound = fix ? (fix.upper_bound_95_stress * 100).toFixed(2) : "N/A"; const badge = `${trace.evidence_kind === "illustrative" ? "**Illustrative offline benchmark — not recorded execution evidence.**\n\n" : ""}![Coinflip ${trace.final_verdict}](https://img.shields.io/badge/Coinflip-${encodeURIComponent(trace.final_verdict)}-${trace.final_verdict === "PASS" ? "059669" : "FF4F00"})\n\nTrace: \`${trace.trace_id}\` · 95% stress upper bound: ${bound}% · ${trace.timestamp_utc}`; try { await navigator.clipboard.writeText(badge); setStatus("Verification badge copied"); } catch { setStatus("Copy failed — try again"); } setTimeout(() => setStatus("Copy GitHub PR Verification Badge"), 2500); }}><Copy />{status}</Button></div>;
}

export function CertificateSeal() {
  return <svg viewBox="0 0 120 120" className="certificate-seal text-pass" role="img" aria-label="Coinflip statistical certification seal"><circle cx="60" cy="60" r="55" fill="none" stroke="currentColor" strokeWidth="1" /><circle cx="60" cy="60" r="48" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="1 3" /><circle cx="60" cy="60" r="39" fill="none" stroke="currentColor" strokeWidth="1" />{Array.from({ length: 24 }, (_, i) => <path key={i} d="M60 3V10" transform={`rotate(${i * 15} 60 60)`} stroke="currentColor" />)}<path d="m41 60 12 12 27-28" fill="none" stroke="currentColor" strokeWidth="3" /><text x="60" y="90" textAnchor="middle" fill="currentColor" fontFamily="monospace" fontSize="7">COINFLIP · VERIFIED</text></svg>;
}