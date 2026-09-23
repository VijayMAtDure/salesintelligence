import { useState } from "react";
import { useNarrativeSandbox } from "../hooks/useInference";
import { ProvenanceBadge } from "../components/ProvenanceBadge";
import type { Provenance, Track } from "../api/types";

/**
 * Dev/test-only page (2026-08-31 testing plan, Part 2). The real Predict page can only ever
 * show scenarios our one fixed historical dataset happens to contain — it has never produced
 * a capacity surplus, a shrinking follow-up backlog, or a high-probability lead, because
 * that's just not what happened in this pilot's real data. This page calls the same
 * narrative-generation logic (build_forecast_evidence's evidence shape, generate_forecast_
 * narrative / generate_narrative) directly against hand-built evidence, bypassing
 * InferenceJob/ModelVersion entirely -- nothing here is persisted or shown anywhere else.
 */

type Preset = {
  name: string;
  track: Track;
  provenance: Provenance;
  caveat: string;
  evidence: Record<string, unknown>;
};

const PRESETS: Preset[] = [
  {
    name: "1. Capacity shortfall",
    track: "FORECAST", provenance: "REAL", caveat: "",
    evidence: {
      target: "calls_attempted", horizon_hours: 24, model_name: "WeightedEnsemble",
      forecast_total_p50: 380, forecast_total_p10: 0, forecast_total_p90: 5960,
      peak_hour: { timestamp: "2026-09-01T09:00:00", p50: 90 },
      capacity_reps_available: 6, capacity_leads_per_rep_per_day: 8,
      capacity_total_per_day: 48, capacity_provenance: "SIMULATED",
    },
  },
  {
    name: "2. Capacity surplus",
    track: "FORECAST", provenance: "REAL", caveat: "",
    evidence: {
      target: "calls_attempted", horizon_hours: 24, model_name: "WeightedEnsemble",
      forecast_total_p50: 20, forecast_total_p10: 5, forecast_total_p90: 40,
      peak_hour: { timestamp: "2026-09-01T10:00:00", p50: 4 },
      capacity_reps_available: 6, capacity_leads_per_rep_per_day: 8,
      capacity_total_per_day: 48, capacity_provenance: "SIMULATED",
    },
  },
  {
    name: "3. Near-zero sparse rate",
    track: "FORECAST", provenance: "REAL",
    caveat: "~191 points in the main series across 24.8 days with real gaps. 24h horizon is marginal.",
    evidence: {
      target: "test_drive_interest_rate", horizon_hours: 24, model_name: "SeasonalNaive",
      forecast_total_p50: 0, forecast_total_p10: 0, forecast_total_p90: 0.06,
      peak_hour: { timestamp: "2026-09-01T02:00:00", p50: 0 },
    },
  },
  {
    name: "4. Retries: executed > scheduled",
    track: "FORECAST", provenance: "REAL", caveat: "",
    evidence: {
      target: "retries_executed", horizon_hours: 24, model_name: "WeightedEnsemble",
      forecast_total_p50: 204.6, forecast_total_p10: 0, forecast_total_p90: 1210,
      peak_hour: { timestamp: "2026-09-01T10:00:00", p50: 34.9 },
      scheduled_vs_executed_comparison: "retries_executed (204.6) is HIGHER than retries_scheduled (16.2) by 188.4.",
    },
  },
  {
    name: "5. Retries: real backlog",
    track: "FORECAST", provenance: "REAL", caveat: "",
    evidence: {
      target: "retries_executed", horizon_hours: 24, model_name: "WeightedEnsemble",
      forecast_total_p50: 8, forecast_total_p10: 0, forecast_total_p90: 20,
      peak_hour: { timestamp: "2026-09-01T10:00:00", p50: 2 },
      scheduled_vs_executed_comparison: "retries_executed (8) is LOWER than retries_scheduled (30) by 22 — this signals a backlog building up.",
    },
  },
  {
    name: "6. Follow-ups keeping pace",
    track: "FORECAST", provenance: "REAL", caveat: "",
    evidence: {
      target: "followups_completed", horizon_hours: 24, model_name: "WeightedEnsemble",
      forecast_total_p50: 4.8, forecast_total_p10: 1, forecast_total_p90: 9,
      peak_hour: { timestamp: "2026-09-01T11:00:00", p50: 1.1 },
      due_vs_completed_comparison: "followups_completed (4.8) is HIGHER than followups_due (4.7) by 0.1.",
    },
  },
  {
    name: "7. Follow-ups severe backlog",
    track: "FORECAST", provenance: "REAL", caveat: "",
    evidence: {
      target: "followups_completed", horizon_hours: 24, model_name: "WeightedEnsemble",
      forecast_total_p50: 0.5, forecast_total_p10: 0, forecast_total_p90: 2,
      peak_hour: { timestamp: "2026-09-01T11:00:00", p50: 0.1 },
      due_vs_completed_comparison: "followups_completed (0.5) is LOWER than followups_due (18) by 17.5 — this signals a backlog building up.",
    },
  },
  {
    name: "8. PREVIEW provenance",
    track: "FORECAST", provenance: "SIMULATED",
    caveat: "PREVIEW VARIANT — trained on preview test-drive-interest events, not observed customer behavior.",
    evidence: {
      target: "test_drive_interest_rate_sim", horizon_hours: 24, model_name: "WeightedEnsemble",
      forecast_total_p50: 0.77, forecast_total_p10: 0.08, forecast_total_p90: 2.52,
      peak_hour: { timestamp: "2026-09-01T12:00:00", p50: 0.1 },
    },
  },
  {
    name: "9. Propensity: high probability",
    track: "PROPENSITY", provenance: "SIMULATED", caveat: "",
    evidence: { target: "label_contacted", probability: 0.92, model_name: "WeightedEnsemble" },
  },
  {
    name: "10. Propensity: low probability",
    track: "PROPENSITY", provenance: "SIMULATED", caveat: "",
    evidence: { target: "label_contacted", probability: 0.04, model_name: "WeightedEnsemble" },
  },
];

export function SandboxPage() {
  const [track, setTrack] = useState<Track>("FORECAST");
  const [provenance, setProvenance] = useState<Provenance>("REAL");
  const [caveat, setCaveat] = useState("");
  const [evidenceText, setEvidenceText] = useState(JSON.stringify(PRESETS[0].evidence, null, 2));
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [activePreset, setActivePreset] = useState(PRESETS[0].name);
  const mutation = useNarrativeSandbox();

  function loadPreset(p: Preset) {
    setActivePreset(p.name);
    setTrack(p.track);
    setProvenance(p.provenance);
    setCaveat(p.caveat);
    setEvidenceText(JSON.stringify(p.evidence, null, 2));
    setJsonError(null);
    mutation.reset();
  }

  function handleRun() {
    let evidence: Record<string, unknown>;
    try {
      evidence = JSON.parse(evidenceText);
      setJsonError(null);
    } catch {
      setJsonError("Evidence isn't valid JSON — fix it before running.");
      return;
    }
    mutation.mutate({ track, provenance, caveat, evidence });
  }

  return (
    <div>
      <h1 style={{ fontSize: 22, marginBottom: 4 }}>Narrative Sandbox</h1>
      <p style={{ color: "#64748b", fontSize: 14, marginTop: 0, marginBottom: 8 }}>
        Test the narrative logic against hand-built scenarios — nothing here runs a real model or gets saved.
      </p>
      <p style={{ fontSize: 12, color: "#b45309", background: "#fffbeb", display: "inline-block", padding: "4px 10px", borderRadius: 4, marginBottom: 20 }}>
        Dev/test tool — not a real prediction
      </p>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 20 }}>
        {PRESETS.map((p) => (
          <button
            key={p.name}
            onClick={() => loadPreset(p)}
            style={{
              padding: "7px 12px", borderRadius: 6, fontSize: 12.5, cursor: "pointer",
              border: activePreset === p.name ? "1.5px solid #334155" : "1px solid #e2e8f0",
              background: activePreset === p.name ? "#f1f5f9" : "#fff", color: "#1e293b",
            }}
          >
            {p.name}
          </button>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
        <div style={cardStyle}>
          <div style={{ display: "flex", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
            <div>
              <label style={labelStyle}>Track</label>
              <select value={track} onChange={(e) => setTrack(e.target.value as Track)} style={inputStyle}>
                <option value="FORECAST">Forecast</option>
                <option value="PROPENSITY">Propensity</option>
              </select>
            </div>
            <div>
              <label style={labelStyle}>Provenance</label>
              <select value={provenance} onChange={(e) => setProvenance(e.target.value as Provenance)} style={inputStyle}>
                <option value="REAL">REAL</option>
                <option value="SIMULATED">PREVIEW</option>
              </select>
            </div>
          </div>
          <label style={labelStyle}>Caveat (optional)</label>
          <textarea
            value={caveat}
            onChange={(e) => setCaveat(e.target.value)}
            rows={2}
            style={{ ...inputStyle, width: "100%", marginBottom: 12, fontFamily: "inherit" }}
          />
          <label style={labelStyle}>Evidence (JSON — edit freely)</label>
          <textarea
            value={evidenceText}
            onChange={(e) => setEvidenceText(e.target.value)}
            rows={16}
            style={{ ...inputStyle, width: "100%", fontFamily: "ui-monospace, monospace", fontSize: 12.5 }}
          />
          {jsonError && <p style={{ color: "#991b1b", fontSize: 12, marginTop: 6 }}>{jsonError}</p>}
          <button onClick={handleRun} disabled={mutation.isPending} style={btnPrimary}>
            {mutation.isPending ? "Generating…" : "Generate narrative"}
          </button>
        </div>

        <div style={cardStyle}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <h3 style={{ margin: 0, fontSize: 15 }}>Result</h3>
            <ProvenanceBadge provenance={provenance} />
          </div>
          {mutation.isError && (
            <p style={{ color: "#991b1b", fontSize: 13 }}>
              {(mutation.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Request failed."}
            </p>
          )}
          {mutation.data ? (
            <NarrativeDisplay text={mutation.data} />
          ) : (
            !mutation.isError && <p style={{ fontSize: 13, color: "#94a3b8" }}>Run a scenario to see the narrative here.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function NarrativeDisplay({ text }: { text: string }) {
  const marker = "Recommended action";
  const idx = text.indexOf(marker);
  const explanation = idx === -1 ? text : text.slice(0, idx).trim();
  const action = idx === -1 ? null : text.slice(idx + marker.length).replace(/^[\s:—-]+/, "").trim();
  return (
    <div>
      <p style={{ fontSize: 13.5, lineHeight: 1.6, color: "#334155", margin: 0 }}>{explanation}</p>
      {action && (
        <p style={{ fontSize: 13.5, lineHeight: 1.6, marginTop: 10, marginBottom: 0, padding: "8px 10px", background: "#ecfdf5", borderLeft: "3px solid #10b981", borderRadius: 4 }}>
          <strong>Recommended action —</strong> {action}
        </p>
      )}
    </div>
  );
}

const cardStyle: React.CSSProperties = { background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 20 };
const labelStyle: React.CSSProperties = { display: "block", fontSize: 12, color: "#64748b", marginBottom: 4 };
const inputStyle: React.CSSProperties = { padding: 8, border: "1px solid #cbd5e1", borderRadius: 4, fontSize: 13 };
const btnPrimary: React.CSSProperties = { marginTop: 12, padding: "9px 20px", background: "#334155", color: "#fff", border: "none", borderRadius: 4, fontWeight: 600, cursor: "pointer", fontSize: 13 };
