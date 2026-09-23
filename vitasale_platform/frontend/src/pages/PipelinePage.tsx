import { useState } from "react";
import { isAxiosError } from "axios";
import { useCancelPipelineRun, useCreatePipelineRun, usePipelinePreview, usePipelineRuns } from "../hooks/usePipeline";
import { StatusBadge } from "../components/StatusBadge";
import { EventTimeline } from "../components/EventTimeline";
import { ActionButton } from "../components/ActionButton";
import type { PipelineMode } from "../api/types";

const CARD: React.CSSProperties = {
  background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: 20, marginBottom: 20,
};

const FEATURE_VERSION = "1.2";

export function PipelinePage() {
  const { data: runs, isLoading } = usePipelineRuns();
  const createRun = useCreatePipelineRun();
  const cancelRun = useCancelPipelineRun();
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

  const preview = usePipelinePreview(selectedRunId);

  const activeRun = runs?.find((r) => (r.status === "QUEUED" || r.status === "RUNNING") && r.mode !== "VALIDATE");
  // VALIDATE is exempt from the one-active-run lock, so it needs its own check to show as
  // active — it can be running alongside another mode, or on its own.
  const activeValidate = runs?.find((r) => (r.status === "QUEUED" || r.status === "RUNNING") && r.mode === "VALIDATE");

  async function trigger(mode: PipelineMode) {
    setBanner(null);
    try {
      const run = await createRun.mutateAsync({ mode, feature_version: FEATURE_VERSION });
      setSelectedRunId(run.id);
    } catch (e) {
      setBanner(isAxiosError(e) && e.response?.data?.detail ? e.response.data.detail : "Something went wrong.");
    }
  }

  async function handleCancel(id: number, mode: PipelineMode) {
    // REBUILD deletes feature_snapshot/timeseries before reinserting — cancelling mid-run can
    // leave both EMPTY until another Rebuild/Backfill completes (confirmed by a real incident
    // 2026-09-01 while testing this button). Other modes are additive/safe to interrupt.
    const message = mode === "REBUILD"
      ? "Cancel this rebuild? If it has already started deleting old data, the feature/timeseries tables may be left EMPTY until you run another Rebuild or Backfill to completion."
      : "Cancel this run? The in-progress process will be stopped immediately.";
    if (!window.confirm(message)) return;
    setBanner(null);
    try {
      await cancelRun.mutateAsync(id);
    } catch (e) {
      setBanner(isAxiosError(e) && e.response?.data?.detail ? e.response.data.detail : "Couldn't cancel — try again.");
    }
  }

  return (
    <div>
      <h1 style={{ fontSize: 20 }}>Transform</h1>
      <p style={{ color: "#64748b", fontSize: 14 }}>
        Runs extract → events → features → aggregates. Only one active run (of any mode except
        Validate) at a time — a second click while one is in progress is rejected.
      </p>

      {banner && (
        <div style={{ padding: 12, borderRadius: 6, marginBottom: 16, fontSize: 13, background: "#fee2e2", color: "#991b1b" }}>
          {banner}
        </div>
      )}

      <div style={CARD}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <ActionButton
            label="Run incremental"
            onClick={() => trigger("INCREMENTAL")}
            disabled={!!activeRun || createRun.isPending}
            active={activeRun?.mode === "INCREMENTAL"}
          />
          <ActionButton
            label="Full rebuild"
            onClick={() => trigger("REBUILD")}
            disabled={!!activeRun || createRun.isPending}
            active={activeRun?.mode === "REBUILD"}
          />
          <ActionButton
            label="Validate (read-only, always available)"
            onClick={() => trigger("VALIDATE")}
            disabled={createRun.isPending}
            active={!!activeValidate}
          />
        </div>
        {activeRun && (
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 10 }}>
            <p style={{ fontSize: 13, color: "#3b82f6", margin: 0 }}>
              A {activeRun.mode.toLowerCase()} run is {activeRun.status.toLowerCase()} — buttons re-enable once it finishes.
            </p>
            <button
              onClick={() => handleCancel(activeRun.id, activeRun.mode)}
              disabled={cancelRun.isPending}
              style={btnDanger}
            >
              {cancelRun.isPending ? "Cancelling…" : "Cancel run"}
            </button>
          </div>
        )}
      </div>

      <h2 style={{ fontSize: 16 }}>Recent runs</h2>
      {isLoading ? <p>Loading...</p> : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #e2e8f0" }}>
              <th style={th}>ID</th><th style={th}>Mode</th><th style={th}>Status</th>
              <th style={th}>Rows processed</th><th style={th}>Finished</th><th style={th}></th>
            </tr>
          </thead>
          <tbody>
            {runs?.map((r) => (
              <tr key={r.id} style={{ borderBottom: "1px solid #f1f5f9" }}>
                <td style={td}>{r.id}</td>
                <td style={td}>{r.mode}</td>
                <td style={td}><StatusBadge status={r.status} /></td>
                <td style={td}>{Object.entries(r.rows_processed).map(([k, v]) => `${k}: ${v}`).join(", ") || "—"}</td>
                <td style={td}>{r.finished_at ? new Date(r.finished_at).toLocaleString() : "—"}</td>
                <td style={td}><button onClick={() => setSelectedRunId(r.id)} style={linkBtn}>details</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selectedRunId !== null && (
        <div style={{ ...CARD, marginTop: 20 }}>
          <h3 style={{ marginTop: 0, fontSize: 15 }}>Run #{selectedRunId}</h3>
          <EventTimeline events={runs?.find((r) => r.id === selectedRunId)?.events ?? []} />
          {preview.data && (
            <>
              <h4 style={{ fontSize: 13, marginBottom: 4 }}>Feature snapshot sample</h4>
              <pre style={{ fontSize: 11, overflowX: "auto", background: "#f8fafc", padding: 10, maxHeight: 240 }}>
                {JSON.stringify(preview.data.feature_snapshot_sample.slice(0, 3), null, 2)}
              </pre>
            </>
          )}
        </div>
      )}
    </div>
  );
}

const th: React.CSSProperties = { padding: "6px 8px", color: "#64748b", fontWeight: 600 };
const td: React.CSSProperties = { padding: "6px 8px" };
const btnDanger: React.CSSProperties = { padding: "6px 12px", background: "#fff", color: "#991b1b", border: "1px solid #fca5a5", borderRadius: 4, fontWeight: 600, cursor: "pointer", fontSize: 12.5 };
const linkBtn: React.CSSProperties = { border: "none", background: "none", color: "#3b82f6", cursor: "pointer", fontSize: 12, padding: 0 };
