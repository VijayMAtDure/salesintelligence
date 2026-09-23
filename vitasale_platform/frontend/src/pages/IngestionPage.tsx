import { useState } from "react";
import { isAxiosError } from "axios";
import { useIngestionJobs, useIngestionPreview, usePullDb, useUploadCsv } from "../hooks/useIngestion";
import { StatusBadge } from "../components/StatusBadge";
import { EventTimeline } from "../components/EventTimeline";
import { ActionButton } from "../components/ActionButton";

const CARD: React.CSSProperties = {
  background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: 20, marginBottom: 20,
};

export function IngestionPage() {
  const { data: jobs, isLoading } = useIngestionJobs();
  const uploadCsv = useUploadCsv();
  const pullDb = usePullDb();
  const [file, setFile] = useState<File | null>(null);
  const [targetTable, setTargetTable] = useState("call_decision");
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [banner, setBanner] = useState<{ kind: "error" | "info"; text: string } | null>(null);

  const preview = useIngestionPreview(selectedJobId);
  const activeDbPull = jobs?.find((j) => (j.status === "QUEUED" || j.status === "RUNNING") && j.job_type === "DB_PULL");

  async function handleUpload() {
    if (!file) return;
    setBanner(null);
    try {
      const result = await uploadCsv.mutateAsync({ file, targetTable });
      if ("detail" in result) {
        setBanner({ kind: "info", text: result.detail });
      } else {
        setSelectedJobId(result.id);
      }
      setFile(null);
    } catch (e) {
      setBanner({ kind: "error", text: extractError(e) });
    }
  }

  async function handlePullDb(mode: "INCREMENTAL" | "FULL") {
    setBanner(null);
    try {
      await pullDb.mutateAsync(mode);
    } catch (e) {
      setBanner({ kind: "error", text: extractError(e) });
    }
  }

  return (
    <div>
      <h1 style={{ fontSize: 20 }}>Load Data</h1>
      <p style={{ color: "#64748b", fontSize: 14 }}>
        Pull new data from the database, or upload a CSV — both feed the same downstream pipeline.
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

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
        <div style={CARD}>
          <h3 style={{ marginTop: 0, fontSize: 15 }}>From database</h3>
          <p style={{ fontSize: 13, color: "#64748b" }}>
            Incremental (default) picks up only what's new since the last watermark. Full
            reprocesses everything under the current feature version.
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <ActionButton
              label="Pull incremental"
              onClick={() => handlePullDb("INCREMENTAL")}
              disabled={pullDb.isPending}
              active={activeDbPull?.mode === "INCREMENTAL"}
            />
            <ActionButton
              label="Full rebuild"
              onClick={() => handlePullDb("FULL")}
              disabled={pullDb.isPending}
              active={activeDbPull?.mode === "FULL"}
            />
          </div>
        </div>

        <div style={CARD}>
          <h3 style={{ marginTop: 0, fontSize: 15 }}>From CSV</h3>
          <label style={{ display: "block", fontSize: 13, marginBottom: 4 }}>Target table</label>
          <select value={targetTable} onChange={(e) => setTargetTable(e.target.value)} style={inputStyle}>
            <option value="call_decision">call_decision</option>
          </select>
          <input
            type="file" accept=".csv"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            style={{ margin: "12px 0", display: "block", fontSize: 13 }}
          />
          <button onClick={handleUpload} disabled={!file || uploadCsv.isPending} style={btnPrimary}>
            {uploadCsv.isPending ? "Uploading..." : "Upload"}
          </button>
        </div>
      </div>

      <h2 style={{ fontSize: 16, marginTop: 32 }}>Recent ingestion jobs</h2>
      {isLoading ? <p>Loading...</p> : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #e2e8f0" }}>
              <th style={th}>ID</th><th style={th}>Type</th><th style={th}>Source</th>
              <th style={th}>Status</th><th style={th}>Rows</th><th style={th}>Created</th><th style={th}></th>
            </tr>
          </thead>
          <tbody>
            {jobs?.map((j) => (
              <tr key={j.id} style={{ borderBottom: "1px solid #f1f5f9" }}>
                <td style={td}>{j.id}</td>
                <td style={td}>{j.job_type}</td>
                <td style={td}>{j.uploaded_file?.original_filename ?? "—"}</td>
                <td style={td}><StatusBadge status={j.status} /></td>
                <td style={td}>{j.rows_ingested ?? "—"}</td>
                <td style={td}>{new Date(j.created_at).toLocaleString()}</td>
                <td style={td}>
                  {j.uploaded_file && (
                    <button onClick={() => setSelectedJobId(j.id)} style={linkBtn}>preview</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selectedJobId !== null && (
        <div style={{ ...CARD, marginTop: 20 }}>
          <h3 style={{ marginTop: 0, fontSize: 15 }}>Preview — job #{selectedJobId}</h3>
          {preview.data?.sample.length ? (
            <pre style={{ fontSize: 12, overflowX: "auto", background: "#f8fafc", padding: 10 }}>
              {JSON.stringify(preview.data.sample, null, 2)}
            </pre>
          ) : <p style={{ fontSize: 13, color: "#94a3b8" }}>No rows yet — job may still be running.</p>}
          {jobs?.find((j) => j.id === selectedJobId)?.events && (
            <EventTimeline events={jobs.find((j) => j.id === selectedJobId)!.events} />
          )}
        </div>
      )}
    </div>
  );
}

function extractError(e: unknown): string {
  if (isAxiosError(e) && e.response?.data?.detail) return e.response.data.detail;
  return "Something went wrong.";
}

const th: React.CSSProperties = { padding: "6px 8px", color: "#64748b", fontWeight: 600 };
const td: React.CSSProperties = { padding: "6px 8px" };
const inputStyle: React.CSSProperties = { width: "100%", padding: 8, border: "1px solid #cbd5e1", borderRadius: 4, fontSize: 13 };
const btnPrimary: React.CSSProperties = { padding: "8px 14px", background: "#334155", color: "#fff", border: "none", borderRadius: 4, fontWeight: 600, cursor: "pointer", fontSize: 13 };
const linkBtn: React.CSSProperties = { border: "none", background: "none", color: "#3b82f6", cursor: "pointer", fontSize: 12, padding: 0 };
