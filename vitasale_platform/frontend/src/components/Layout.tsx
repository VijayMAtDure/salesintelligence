import { NavLink, Outlet } from "react-router-dom";
import { useActiveTrainingStatus } from "../hooks/useTraining";

const navStyle = ({ isActive }: { isActive: boolean }) => ({
  padding: "8px 14px",
  borderRadius: 6,
  textDecoration: "none",
  color: isActive ? "#fff" : "#334155",
  background: isActive ? "#334155" : "transparent",
  fontWeight: 600,
  fontSize: 14,
});

/** GPU status derived client-side from a small status-filtered query rather than a dedicated
 * backend endpoint — no need for a second source of truth for the same fact the training jobs
 * already carry. Uses useActiveTrainingStatus(), NOT the general useTrainingJobs() list — see
 * that hook's docstring for the pagination bug this fixes (the widget was structurally unable
 * to see any job past the first 25 ever created). */
function GpuStatusWidget() {
  const { data } = useActiveTrainingStatus();
  const running = data?.running;
  const queued = data?.queuedCount ?? 0;

  const color = running ? "#3b82f6" : "#22c55e";
  const label = running ? `GPU busy — ${running.track}/${running.target}` : "GPU idle";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
      <span style={{ width: 10, height: 10, borderRadius: "50%", background: color, display: "inline-block" }} />
      <span>{label}</span>
      {queued > 0 && (
        <span style={{ color: "#94a3b8" }}>· {queued} queued</span>
      )}
    </div>
  );
}

export function Layout() {
  return (
    <div style={{ fontFamily: "system-ui, sans-serif", minHeight: "100vh", background: "#f8fafc" }}>
      <header
        style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "12px 24px", background: "#fff", borderBottom: "1px solid #e2e8f0",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
          <strong style={{ fontSize: 15 }}>VITASale Sales Intelligence</strong>
          <nav style={{ display: "flex", gap: 4 }}>
            <NavLink to="/ingestion" style={navStyle}>Load Data</NavLink>
            <NavLink to="/pipeline" style={navStyle}>Transform</NavLink>
            <NavLink to="/training" style={navStyle}>Train</NavLink>
            <NavLink to="/models" style={navStyle}>Models</NavLink>
            <NavLink to="/predict" style={navStyle}>Predict</NavLink>
            <NavLink to="/activity" style={navStyle}>Activity</NavLink>
            <NavLink to="/analytics" style={navStyle}>Analytics</NavLink>
            <NavLink to="/map" style={navStyle}>Map</NavLink>
            <NavLink to="/assistant" style={navStyle}>Assistant</NavLink>
          </nav>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <NavLink
            to="/sandbox"
            style={({ isActive }) => ({
              padding: "6px 12px", borderRadius: 6, textDecoration: "none", fontSize: 12.5,
              fontWeight: 600, color: isActive ? "#92400e" : "#b45309",
              background: isActive ? "#fef3c7" : "#fffbeb", border: "1px solid #fde68a",
            })}
          >
            Sandbox
          </NavLink>
          <GpuStatusWidget />
        </div>
      </header>
      <main style={{ padding: 24, maxWidth: 1100, margin: "0 auto" }}>
        <Outlet />
      </main>
    </div>
  );
}
