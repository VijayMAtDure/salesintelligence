import type { EventItem } from "../api/types";

/** Shared renderer for TrainingEvent/PipelineEvent/IngestionEvent — the append-only audit
 * trail is the direct UI expression of the "GPU properly utilised" requirement (architecture
 * doc §7.4): every state transition, visible, in order. This is also the "why did this fail"
 * view flagged as missing in the original architecture doc §5.2 — the raw detail JSON is
 * shown rather than hidden, since a generic "failed" with no reason is exactly what was
 * called out as insufficient. */
export function EventTimeline({ events }: { events: EventItem[] }) {
  if (events.length === 0) {
    return <p style={{ color: "#94a3b8", fontSize: 13 }}>No events yet.</p>;
  }
  return (
    <ol style={{ listStyle: "none", padding: 0, margin: 0, borderLeft: "2px solid #e2e8f0" }}>
      {events.map((e) => (
        <li key={e.id} style={{ padding: "6px 0 6px 16px", marginLeft: -1, position: "relative" }}>
          <span
            style={{
              position: "absolute", left: -6, top: 10, width: 10, height: 10,
              borderRadius: "50%", background: eventColor(e.event_type),
            }}
          />
          <div style={{ fontSize: 13, fontWeight: 600 }}>{e.event_type}</div>
          <div style={{ fontSize: 11, color: "#94a3b8" }}>
            {new Date(e.timestamp).toLocaleString()}
            {e.gpu_host ? ` · ${e.gpu_host}` : ""}
          </div>
          {Object.keys(e.detail).length > 0 && (
            <pre
              style={{
                fontSize: 11, background: "#f8fafc", padding: 6, borderRadius: 4,
                marginTop: 4, maxWidth: 640, overflowX: "auto", whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {JSON.stringify(e.detail, null, 2)}
            </pre>
          )}
        </li>
      ))}
    </ol>
  );
}

function eventColor(eventType: string): string {
  if (eventType === "SUCCEEDED") return "#22c55e";
  if (eventType === "FAILED") return "#ef4444";
  if (eventType === "CANCELLED") return "#94a3b8";
  if (eventType === "STARTED") return "#3b82f6";
  return "#cbd5e1";
}
