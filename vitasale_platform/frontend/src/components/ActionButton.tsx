/**
 * For a row of mutually-exclusive action buttons (e.g. Pull incremental / Full rebuild /
 * Validate) — fixes a real UX bug reported 2026-09-01: one button was always styled "primary"
 * (dark) regardless of which action was actually running, so clicking a different one still
 * left the FIRST button looking selected. `active` must reflect real current state (the
 * matching job/run's mode), not which button was last clicked — that way it self-corrects
 * once the job finishes, instead of staying stuck highlighted.
 */
export function ActionButton({
  label, onClick, disabled, active, title,
}: { label: string; onClick: () => void; disabled?: boolean; active: boolean; title?: string }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      style={{
        padding: "8px 14px",
        borderRadius: 4,
        fontWeight: 600,
        fontSize: 13,
        cursor: disabled ? "default" : "pointer",
        display: "inline-flex",
        alignItems: "center",
        gap: 7,
        opacity: disabled && !active ? 0.55 : 1,
        background: active ? "#334155" : "#fff",
        color: active ? "#fff" : "#334155",
        border: active ? "1px solid #334155" : "1px solid #cbd5e1",
      }}
    >
      {active && <PulsingDot />}
      {label}
    </button>
  );
}

function PulsingDot() {
  return (
    <span style={{ position: "relative", display: "inline-flex", width: 7, height: 7 }}>
      <span style={{
        position: "absolute", inset: 0, borderRadius: "50%", background: "#4ade80",
        animation: "action-btn-pulse 1.4s ease-out infinite",
      }} />
      <span style={{ position: "absolute", inset: 0, borderRadius: "50%", background: "#4ade80" }} />
      <style>{`@keyframes action-btn-pulse { 0% { transform: scale(1); opacity: 0.9; } 100% { transform: scale(2.8); opacity: 0; } }`}</style>
    </span>
  );
}
