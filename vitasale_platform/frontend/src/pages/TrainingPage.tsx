import { useState } from "react";
import { isAxiosError } from "axios";
import { useCreateTrainingJob, useTrainingJobs } from "../hooks/useTraining";
import { StatusBadge } from "../components/StatusBadge";
import { EventTimeline } from "../components/EventTimeline";
import type { Track, Transform } from "../api/types";

const CARD: React.CSSProperties = {
  background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: 20, marginBottom: 20,
};

const FORECAST_TARGETS = [
  "calls_attempted", "calls_connected", "new_leads_count", "connect_rate",
  "purchase_interest_rate", "purchase_interest_yes_count", "test_drive_interest_rate",
  "retries_scheduled", "retries_executed", "followups_due", "followups_completed",
];
const PROPENSITY_TARGETS = ["label_contacted", "label_assigned", "label_test_drive_booked_sim"];

export function TrainingPage() {
  const { data: jobs, isLoading } = useTrainingJobs();
  const createJob = useCreateTrainingJob();

  const [track, setTrack] = useState<Track>("PROPENSITY");
  const [target, setTarget] = useState(PROPENSITY_TARGETS[0]);
  const [preset, setPreset] = useState("medium_quality");
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [banner, setBanner] = useState<{ kind: "error" | "info"; text: string } | null>(null);

  const activeJob = jobs?.find((j) => j.status === "QUEUED" || j.status === "RUNNING");
  const targets = track === "FORECAST" ? FORECAST_TARGETS : PROPENSITY_TARGETS;

  function handleTrackChange(t: Track) {
    setTrack(t);
    setTarget(t === "FORECAST" ? FORECAST_TARGETS[0] : PROPENSITY_TARGETS[0]);
  }

  async function handleTrain() {
    setBanner(null);
    try {
      const transform: Transform = track === "FORECAST" ? "LOG1P" : null;
      const job = await createJob.mutateAsync({ track, target, transform, preset });
      setSelectedJobId(job.id);
    } catch (e) {
      // The backend is the real enforcement (only_one_active_training_job constraint) — this
      // catch is what makes a 409 read as a clear message instead of a raw request failure.
      if (isAxiosError(e) && e.response?.status === 409) {
        setBanner({ kind: "info", text: e.response.data.detail });
      } else {
        setBanner({ kind: "error", text: "Something went wrong starting training." });
      }
    }
  }

  return (
    <div>
      <h1 style={{ fontSize: 20 }}>Train</h1>
      <p style={{ color: "#64748b", fontSize: 14 }}>
        GPU training is mandatory — a job fails immediately if the GPU isn't available rather
        than silently running on CPU. Only one job runs at a time; the button stays enabled,
        but a second click while one is active is rejected with a clear reason.
      </p>

      {banner && (
        <div style={{
          padding: 12, borderRadius: 6, marginBottom: 16, fontSize: 13,
          background: banner.kind === "error" ? "#fee2e2" : "#e0f2fe",
          color: banner.kind === "error" ? "#991b1b" : "#075985",
        }}>
          {banner.text}
        </div>
      )}

      <div style={CARD}>
        <div style={{ display: "flex", gap: 16, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div>
            <label style={labelStyle}>Track</label>
            <select value={track} onChange={(e) => handleTrackChange(e.target.value as Track)} style={inputStyle}>
              <option value="PROPENSITY">Propensity</option>
              <option value="FORECAST">Forecast</option>
            </select>
          </div>
          <div>
            <label style={labelStyle}>Target</label>
            <select value={target} onChange={(e) => setTarget(e.target.value)} style={inputStyle}>
              {targets.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label style={labelStyle}>Preset</label>
            <select value={preset} onChange={(e) => setPreset(e.target.value)} style={inputStyle}>
              <option value="medium_quality">medium_quality</option>
              <option value="best_quality">best_quality</option>
            </select>
          </div>
          <button onClick={handleTrain} disabled={createJob.isPending} style={btnPrimary}>
            {createJob.isPending ? "Starting..." : "Train"}
          </button>
        </div>
        {activeJob && (
          <p style={{ fontSize: 12, color: "#3b82f6", marginTop: 10 }}>
            {activeJob.track}/{activeJob.target} is currently {activeJob.status.toLowerCase()} —
            clicking Train now will be rejected until it finishes.
          </p>
        )}
        {track === "PROPENSITY" && (
          <p style={{ fontSize: 12, color: "#7c2d12", marginTop: 10 }}>
            ⚠ Propensity labels are currently PREVIEW — results validate the pipeline, not
            real customer behaviour. See ModelVersion.caveat once trained.
          </p>
        )}
      </div>

      <h2 style={{ fontSize: 16 }}>Recent training jobs</h2>
      {isLoading ? <p>Loading...</p> : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #e2e8f0" }}>
              <th style={th}>ID</th><th style={th}>Track/Target</th><th style={th}>Status</th>
              <th style={th}>GPU host</th><th style={th}>Finished</th><th style={th}></th>
            </tr>
          </thead>
          <tbody>
            {jobs?.map((j) => (
              <tr key={j.id} style={{ borderBottom: "1px solid #f1f5f9" }}>
                <td style={td}>{j.id}</td>
                <td style={td}>{j.track}/{j.target}{j.transform ? ` (${j.transform})` : ""}</td>
                <td style={td}>
                  <StatusBadge status={j.status} />
                  {j.status === "QUEUED" && j.queue_position && (
                    <span style={{ fontSize: 11, color: "#94a3b8", marginLeft: 6 }}>#{j.queue_position}</span>
                  )}
                </td>
                <td style={td}>{j.gpu_host || "—"}</td>
                <td style={td}>{j.finished_at ? new Date(j.finished_at).toLocaleString() : "—"}</td>
                <td style={td}><button onClick={() => setSelectedJobId(j.id)} style={linkBtn}>details</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selectedJobId !== null && (
        <div style={{ ...CARD, marginTop: 20 }}>
          <h3 style={{ marginTop: 0, fontSize: 15 }}>Job #{selectedJobId}</h3>
          {(() => {
            const job = jobs?.find((j) => j.id === selectedJobId);
            if (job?.status === "FAILED") {
              return (
                <div style={{ padding: 10, background: "#fee2e2", borderRadius: 4, marginBottom: 12, fontSize: 13 }}>
                  <strong>{job.failure_reason || "Failed"}</strong>
                  {job.error_message && <pre style={{ fontSize: 11, whiteSpace: "pre-wrap", marginTop: 6 }}>{job.error_message}</pre>}
                </div>
              );
            }
            return null;
          })()}
          <EventTimeline events={jobs?.find((j) => j.id === selectedJobId)?.events ?? []} />
        </div>
      )}
    </div>
  );
}

const th: React.CSSProperties = { padding: "6px 8px", color: "#64748b", fontWeight: 600 };
const td: React.CSSProperties = { padding: "6px 8px" };
const labelStyle: React.CSSProperties = { display: "block", fontSize: 12, color: "#64748b", marginBottom: 4 };
const inputStyle: React.CSSProperties = { padding: 8, border: "1px solid #cbd5e1", borderRadius: 4, fontSize: 13, minWidth: 180 };
const btnPrimary: React.CSSProperties = { padding: "9px 20px", background: "#334155", color: "#fff", border: "none", borderRadius: 4, fontWeight: 600, cursor: "pointer", fontSize: 13 };
const linkBtn: React.CSSProperties = { border: "none", background: "none", color: "#3b82f6", cursor: "pointer", fontSize: 12, padding: 0 };
