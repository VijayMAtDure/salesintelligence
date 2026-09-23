import { useTrainingJobs } from "../hooks/useTraining";
import { usePipelineRuns } from "../hooks/usePipeline";
import { useIngestionJobs } from "../hooks/useIngestion";

/** Merges events from all three job types into one feed, client-side — architecture doc
 * §5.2's "unified activity feed" flagged as missing from the original ask. No dedicated
 * backend endpoint for this; the three existing job lists already carry everything needed,
 * and a fourth "activity" endpoint would just be a merge of data already fetched elsewhere. */
interface FeedItem {
  source: "training" | "pipeline" | "ingestion";
  label: string;
  eventType: string;
  timestamp: string;
  detail: Record<string, unknown>;
}

export function ActivityPage() {
  const { data: trainingJobs } = useTrainingJobs();
  const { data: pipelineRuns } = usePipelineRuns();
  const { data: ingestionJobs } = useIngestionJobs();

  const feed: FeedItem[] = [
    ...(trainingJobs ?? []).flatMap((j) =>
      j.events.map((e) => ({
        source: "training" as const, label: `${j.track}/${j.target}`,
        eventType: e.event_type, timestamp: e.timestamp, detail: e.detail,
      }))
    ),
    ...(pipelineRuns ?? []).flatMap((r) =>
      r.events.map((e) => ({
        source: "pipeline" as const, label: r.mode,
        eventType: e.event_type, timestamp: e.timestamp, detail: e.detail,
      }))
    ),
    ...(ingestionJobs ?? []).flatMap((j) =>
      j.events.map((e) => ({
        source: "ingestion" as const, label: j.job_type,
        eventType: e.event_type, timestamp: e.timestamp, detail: e.detail,
      }))
    ),
  ].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

  return (
    <div>
      <h1 style={{ fontSize: 20 }}>Activity</h1>
      <p style={{ color: "#64748b", fontSize: 14 }}>
        Every event across ingestion, transform, and training, newest first.
      </p>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid #e2e8f0" }}>
            <th style={th}>Time</th><th style={th}>Source</th><th style={th}>Item</th><th style={th}>Event</th>
          </tr>
        </thead>
        <tbody>
          {feed.slice(0, 100).map((item, i) => (
            <tr key={i} style={{ borderBottom: "1px solid #f1f5f9" }}>
              <td style={td}>{new Date(item.timestamp).toLocaleString()}</td>
              <td style={td}><SourceTag source={item.source} /></td>
              <td style={td}>{item.label}</td>
              <td style={td}>{item.eventType}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {feed.length === 0 && <p style={{ color: "#94a3b8" }}>No activity yet.</p>}
    </div>
  );
}

function SourceTag({ source }: { source: FeedItem["source"] }) {
  const colors = { training: "#3b82f6", pipeline: "#a855f7", ingestion: "#f59e0b" };
  return (
    <span style={{
      fontSize: 11, fontWeight: 600, color: "#fff", padding: "2px 8px",
      borderRadius: 4, background: colors[source],
    }}>
      {source}
    </span>
  );
}

const th: React.CSSProperties = { padding: "6px 8px", color: "#64748b", fontWeight: 600 };
const td: React.CSSProperties = { padding: "6px 8px" };
