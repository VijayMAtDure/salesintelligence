import type { JobStatus } from "../api/types";

const COLORS: Record<JobStatus, string> = {
  PENDING: "#94a3b8",
  QUEUED: "#eab308",
  RUNNING: "#3b82f6",
  SUCCEEDED: "#22c55e",
  FAILED: "#ef4444",
  CANCELLED: "#94a3b8",
};

export function StatusBadge({ status }: { status: JobStatus }) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 10px",
        borderRadius: 999,
        fontSize: 12,
        fontWeight: 600,
        color: "#fff",
        background: COLORS[status] ?? "#94a3b8",
      }}
    >
      {status}
    </span>
  );
}
