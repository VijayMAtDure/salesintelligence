import type { Provenance } from "../api/types";

/**
 * Not decoration — this is the single most load-bearing UI habit carried over from the whole
 * session's backend work (SIMULATION_REGISTER.md, analytics.py's [SIMULATED]/[REAL] tags).
 * Anywhere a number or a prediction appears, this must sit next to it. A simulated result
 * with no visible tag is exactly the kind of thing that gets mistaken for a real finding.
 */
export function ProvenanceBadge({ provenance, label }: { provenance: Provenance; label?: string }) {
  const isReal = provenance === "REAL";
  return (
    <span
      title={isReal ? "Computed from real production data" : "PREVIEW — built to show how this will read once real data is available, not yet evidence about real customers"}
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: 4,
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: 0.5,
        color: isReal ? "#065f46" : "#7c2d12",
        background: isReal ? "#d1fae5" : "#fed7aa",
        border: `1px solid ${isReal ? "#10b981" : "#f97316"}`,
      }}
    >
      {label ? `${label}: ` : ""}{isReal ? "REAL" : "PREVIEW"}
    </span>
  );
}
