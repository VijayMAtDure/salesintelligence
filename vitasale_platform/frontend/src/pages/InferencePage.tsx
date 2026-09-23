import { useEffect, useRef, useState } from "react";
import {
  useCreateInferenceJob,
  useInferenceJob,
  useRequestNarrative,
  useSampleLeads,
} from "../hooks/useInference";
import { ProvenanceBadge } from "../components/ProvenanceBadge";
import type { InferenceJob, Track } from "../api/types";

/**
 * Redesigned 2026-08-31 per explicit feedback: the previous dropdown-driven form + raw job
 * history table was "too confusing". This page is deliberately just two things — a grid of
 * one-click tests, and a single result card (prediction + LLM narrative together) for
 * whichever one you last ran. No job IDs, no track/target dropdowns, no separate "Explain"
 * click — narrative is fetched automatically once a prediction succeeds.
 */

type ForecastTarget = { key: string; label: string; blurb: string };

const FORECAST_TESTS: ForecastTarget[] = [
  { key: "calls_attempted", label: "Calls Attempted", blurb: "Outbound call volume" },
  { key: "calls_connected", label: "Calls Connected", blurb: "Calls that will connect" },
  { key: "new_leads_count", label: "New Leads", blurb: "Leads entering the pipeline" },
  { key: "connect_rate", label: "Connect Rate", blurb: "Share of calls that connect" },
  { key: "purchase_interest_rate", label: "Purchase Interest Rate", blurb: "Share expressing purchase interest" },
  { key: "purchase_interest_yes_count", label: "Purchase Interest (Count)", blurb: "Calls with expressed interest" },
  { key: "test_drive_interest_rate", label: "Test-Drive Interest Rate", blurb: "Share expressing test-drive interest" },
  { key: "retries_scheduled", label: "Retries Scheduled", blurb: "Re-contact attempts queued" },
  { key: "retries_executed", label: "Retries Executed", blurb: "Re-contact attempts carried out" },
  { key: "followups_due", label: "Follow-ups Due", blurb: "Follow-ups coming due" },
  { key: "followups_completed", label: "Follow-ups Completed", blurb: "Follow-ups actually done" },
];

const PROPENSITY_TESTS: ForecastTarget[] = [
  { key: "label_contacted", label: "Will This Lead Be Contacted?", blurb: "Probability of a successful contact" },
  { key: "label_assigned", label: "Will This Lead Be Assigned?", blurb: "Probability of rep assignment" },
  { key: "label_test_drive_booked_sim", label: "Will This Lead Book a Test Drive? (Preview)",
    blurb: "Real base features + preview hyperlocal signal — real test-drive bookings are too sparse (20 of 5,383) to train on directly yet" },
];

// Two preview variants, for two different reasons — kept as an array (not one SIM_TEST) so
// each can carry its own accurate blurb rather than sharing one that only describes the first:
// test_drive_interest_rate_sim: the real target is data-starved (3 of 184 real hours ever
// nonzero); meta_leads_count_sim: the real hyperlocal channel has zero leads at all yet. Never
// used for real staffing/channel decisions, never blended with or replacing a real target.
const SIM_TESTS: ForecastTarget[] = [
  {
    key: "test_drive_interest_rate_sim",
    label: "Test-Drive Interest Rate (Preview)",
    blurb: "Denser preview comparison — not real customer data",
  },
  {
    key: "meta_leads_count_sim",
    label: "Hyperlocal Lead Volume (Preview)",
    blurb: "Preview — real hyperlocal (Meta) lead volume is zero so far",
  },
];

export function InferencePage() {
  const { data: leads } = useSampleLeads();
  const createJob = useCreateInferenceJob();
  const requestNarrative = useRequestNarrative();

  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [activeTile, setActiveTile] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const narrativeRequestedFor = useRef<number | null>(null);

  const job = useInferenceJob(selectedJobId);

  // Auto-fetch the narrative the moment a prediction succeeds — no separate click.
  useEffect(() => {
    const j = job.data;
    if (j && j.status === "SUCCEEDED" && j.narrative === "" && narrativeRequestedFor.current !== j.id) {
      narrativeRequestedFor.current = j.id;
      requestNarrative.mutate(j.id);
    }
  }, [job.data, requestNarrative]);

  async function runTest(track: Track, key: string) {
    setBanner(null);
    setActiveTile(key);
    const input: Record<string, unknown> = track === "FORECAST"
      ? { horizon_hours: 24 }
      : { source_call_decision_id: leads?.[0]?.source_call_decision_id };
    if (track === "PROPENSITY" && !input.source_call_decision_id) {
      setBanner("No sample lead available to score yet — try again shortly.");
      return;
    }
    try {
      const created = await createJob.mutateAsync({ track, target: key, input });
      narrativeRequestedFor.current = null;
      setSelectedJobId(created.id);
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setBanner(detail ?? "Something went wrong running that test.");
    }
  }

  return (
    <div>
      <h1 style={{ fontSize: 22, marginBottom: 4 }}>Predict</h1>
      <p style={{ color: "#64748b", fontSize: 14, marginTop: 0, marginBottom: 24 }}>
        Pick a signal to test. The result and a plain-language explanation appear below.
      </p>

      {banner && (
        <div style={{ padding: 12, borderRadius: 6, marginBottom: 16, fontSize: 13, background: "#fee2e2", color: "#991b1b" }}>
          {banner}
        </div>
      )}

      <TestSection title="Forecasts — next 24 hours" tests={FORECAST_TESTS} track="FORECAST" activeTile={activeTile} busy={createJob.isPending} onRun={runTest} />

      <div style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 14, color: "#475569", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>
          Preview Comparisons
        </h2>
        <p style={{ fontSize: 12.5, color: "#94a3b8", marginTop: 0, marginBottom: 10, maxWidth: 560 }}>
          Real targets above are too data-sparse to validate on their own (a real target with
          too little history, or a real channel with no volume yet). These run on preview data
          instead, so you can see the pipeline work — never a real signal to act on.
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 10 }}>
          {SIM_TESTS.map((t) => (
            <button
              key={t.key}
              onClick={() => runTest("FORECAST", t.key)}
              disabled={createJob.isPending}
              style={{
                textAlign: "left",
                padding: "12px 14px",
                borderRadius: 8,
                cursor: createJob.isPending ? "default" : "pointer",
                border: activeTile === t.key ? "1.5px solid #7c3aed" : "1px solid #e9d5ff",
                background: activeTile === t.key ? "#f3e8ff" : "#faf5ff",
              }}
            >
              <div style={{ fontWeight: 600, fontSize: 13.5, color: "#1e293b" }}>{t.label}</div>
              <div style={{ fontSize: 12, color: "#a78bfa", marginTop: 2 }}>{t.blurb}</div>
            </button>
          ))}
        </div>
      </div>

      <TestSection title="Lead Scoring" tests={PROPENSITY_TESTS} track="PROPENSITY" activeTile={activeTile} busy={createJob.isPending} onRun={runTest} />

      {selectedJobId !== null && <ResultCard job={job.data} />}
    </div>
  );
}

function TestSection({
  title, tests, track, activeTile, busy, onRun,
}: {
  title: string; tests: ForecastTarget[]; track: Track; activeTile: string | null; busy: boolean;
  onRun: (track: Track, key: string) => void;
}) {
  return (
    <div style={{ marginBottom: 24 }}>
      <h2 style={{ fontSize: 14, color: "#475569", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 10 }}>{title}</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 10 }}>
        {tests.map((t) => (
          <button
            key={t.key}
            onClick={() => onRun(track, t.key)}
            disabled={busy}
            style={{
              textAlign: "left",
              padding: "12px 14px",
              borderRadius: 8,
              cursor: busy ? "default" : "pointer",
              border: activeTile === t.key ? "1.5px solid #334155" : "1px solid #e2e8f0",
              background: activeTile === t.key ? "#f1f5f9" : "#fff",
            }}
          >
            <div style={{ fontWeight: 600, fontSize: 13.5, color: "#1e293b" }}>{t.label}</div>
            <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 2 }}>{t.blurb}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

function ResultCard({ job }: { job?: InferenceJob }) {
  if (!job) {
    return <div style={cardStyle}><p style={{ fontSize: 13, color: "#94a3b8" }}>Loading…</p></div>;
  }

  if (job.status !== "SUCCEEDED") {
    return (
      <div style={cardStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Spinner active={job.status === "RUNNING" || job.status === "QUEUED"} />
          <span style={{ fontSize: 14, color: "#475569" }}>
            {job.status === "FAILED" ? `Failed: ${job.error_message}` : "Running the model against real data…"}
          </span>
        </div>
      </div>
    );
  }

  const all = [...FORECAST_TESTS, ...PROPENSITY_TESTS, ...SIM_TESTS];
  const meta = all.find((t) => t.key === job.target);
  const isForecast = job.track === "FORECAST";

  const preds = isForecast
    ? (job.result.predictions as Array<{ timestamp: string; p10: number; p50: number; p90: number }> ?? [])
    : [];
  const totalP50 = preds.reduce((s, p) => s + p.p50, 0);
  const totalP10 = preds.reduce((s, p) => s + p.p10, 0);
  const totalP90 = preds.reduce((s, p) => s + p.p90, 0);
  const probability = !isForecast ? (job.result.probability as number) : null;

  const [explanation, recommendedAction] = splitNarrative(job.narrative);

  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 12, color: "#94a3b8", textTransform: "uppercase", letterSpacing: 0.5 }}>
            {isForecast ? "24h forecast" : "Lead score"}
          </div>
          <h3 style={{ margin: "2px 0 0", fontSize: 18 }}>{meta?.label ?? job.target}</h3>
        </div>
        <ProvenanceBadge provenance={job.model_version.provenance} />
      </div>

      {isForecast ? (
        <div style={{ display: "flex", alignItems: "flex-end", gap: 24, marginBottom: 8 }}>
          <div>
            <div style={{ fontSize: 40, fontWeight: 800, color: "#0f172a", lineHeight: 1 }}>{fmt(totalP50)}</div>
            <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 4 }}>
              p10 {fmt(totalP10)} · p90 {fmt(totalP90)} &nbsp;(median over 24h)
            </div>
          </div>
          <Sparkline points={preds.map((p) => p.p50)} />
        </div>
      ) : (
        <div style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 40, fontWeight: 800, color: "#0f172a", lineHeight: 1 }}>
            {probability !== null ? `${(probability * 100).toFixed(1)}%` : "—"}
          </div>
          <ProbabilityBar value={probability ?? 0} />
        </div>
      )}

      {job.model_version.caveat && (
        <p style={{ fontSize: 12, color: "#7c2d12", marginTop: 10, background: "#fff7ed", padding: "8px 10px", borderRadius: 6 }}>
          ⚠ {job.model_version.caveat}
        </p>
      )}

      <div style={{ marginTop: 16, borderTop: "1px solid #f1f5f9", paddingTop: 14 }}>
        <div style={{ fontSize: 11, color: "#94a3b8", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
          What this means
        </div>
        {job.narrative ? (
          <>
            <p style={{ fontSize: 13.5, lineHeight: 1.6, color: "#334155", margin: 0 }}>{explanation}</p>
            {recommendedAction && (
              <p style={{ fontSize: 13.5, lineHeight: 1.6, marginTop: 10, marginBottom: 0, padding: "8px 10px", background: "#ecfdf5", borderLeft: "3px solid #10b981", borderRadius: 4 }}>
                <strong>Recommended action —</strong> {recommendedAction}
              </p>
            )}
          </>
        ) : (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Spinner active />
            <span style={{ fontSize: 13, color: "#94a3b8" }}>Generating explanation…</span>
          </div>
        )}
      </div>

      <div style={{ marginTop: 14, display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        <span style={badgeStyle}>{job.model_version.model_name}</span>
        <span style={badgeStyle}>{job.model_version.version_label}</span>
        {(job.finished_at ?? job.created_at) && (
          <span style={{ fontSize: 11, color: "#94a3b8" }}>
            Run {new Date(job.finished_at ?? job.created_at).toLocaleString()}
          </span>
        )}
      </div>
    </div>
  );
}

function splitNarrative(text: string): [string, string | null] {
  const marker = "Recommended action";
  const idx = text.indexOf(marker);
  if (idx === -1) return [text, null];
  const before = text.slice(0, idx).trim();
  const after = text.slice(idx + marker.length).replace(/^[\s:—-]+/, "").trim();
  return [before, after || null];
}

function fmt(n: number): string {
  if (n < 1) return n.toFixed(2);
  if (n < 100) return n.toFixed(1);
  return Math.round(n).toLocaleString();
}

function Sparkline({ points }: { points: number[] }) {
  if (points.length === 0) return null;
  const w = 160, h = 40, max = Math.max(...points, 0.001);
  const step = w / Math.max(points.length - 1, 1);
  const path = points.map((v, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${(h - (v / max) * h).toFixed(1)}`).join(" ");
  return (
    <svg width={w} height={h} style={{ overflow: "visible" }}>
      <path d={path} fill="none" stroke="#0ea5b7" strokeWidth={1.75} />
    </svg>
  );
}

function ProbabilityBar({ value }: { value: number }) {
  return (
    <div style={{ height: 8, background: "#f1f5f9", borderRadius: 4, marginTop: 8, maxWidth: 260, overflow: "hidden" }}>
      <div style={{ height: "100%", width: `${Math.min(100, Math.max(0, value * 100))}%`, background: "#0ea5b7", borderRadius: 4 }} />
    </div>
  );
}

function Spinner({ active }: { active: boolean }) {
  return (
    <span
      style={{
        display: "inline-block", width: 14, height: 14, borderRadius: "50%",
        border: "2px solid #e2e8f0", borderTopColor: active ? "#0ea5b7" : "#94a3b8",
        animation: active ? "spin 0.8s linear infinite" : "none",
      }}
    >
      <style>{"@keyframes spin { to { transform: rotate(360deg); } }"}</style>
    </span>
  );
}

const cardStyle: React.CSSProperties = {
  background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 22, marginTop: 8,
};
const badgeStyle: React.CSSProperties = {
  fontSize: 11, color: "#475569", background: "#f1f5f9", padding: "3px 8px", borderRadius: 4,
};
