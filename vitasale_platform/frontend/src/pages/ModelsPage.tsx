import { useModelVersions, usePromoteModelVersion } from "../hooks/useTraining";
import { ProvenanceBadge } from "../components/ProvenanceBadge";

const CARD: React.CSSProperties = {
  background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: 20, marginBottom: 20,
};

export function ModelsPage() {
  const { data: versions, isLoading } = useModelVersions();
  const promote = usePromoteModelVersion();

  const grouped = new Map<string, typeof versions>();
  for (const v of versions ?? []) {
    const key = `${v.track}/${v.target}`;
    grouped.set(key, [...(grouped.get(key) ?? []), v]);
  }

  return (
    <div>
      <h1 style={{ fontSize: 20 }}>Model registry</h1>
      <p style={{ color: "#64748b", fontSize: 14 }}>
        Every successful training run lands here as a new version. One version per
        track/target is marked "latest" — the one inference would use.
      </p>

      {isLoading ? <p>Loading...</p> : (
        [...grouped.entries()].map(([key, list]) => (
          <div key={key} style={CARD}>
            <h3 style={{ marginTop: 0, fontSize: 15 }}>{key}</h3>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid #e2e8f0" }}>
                  <th style={th}>Version</th><th style={th}>Model</th><th style={th}>Metric</th>
                  <th style={th}>Score</th><th style={th}>Provenance</th><th style={th}>Trained</th>
                  <th style={th}>Latest</th><th style={th}></th>
                </tr>
              </thead>
              <tbody>
                {list?.sort((a, b) => b.id - a.id).map((v) => (
                  <tr key={v.id} style={{ borderBottom: "1px solid #f1f5f9" }}>
                    <td style={td}>{v.version_label}</td>
                    <td style={td}>{v.model_name}</td>
                    <td style={td}>{v.validation_metric}</td>
                    <td style={td}>{v.validation_score.toFixed(4)}</td>
                    <td style={td}><ProvenanceBadge provenance={v.provenance} /></td>
                    <td style={td}>{new Date(v.created_at).toLocaleString()}</td>
                    <td style={td}>{v.is_latest ? "✓" : ""}</td>
                    <td style={td}>
                      {!v.is_latest && (
                        <button onClick={() => promote.mutate(v.id)} style={linkBtn} disabled={promote.isPending}>
                          promote
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {list?.find((v) => v.is_latest)?.caveat && (
              <p style={{ fontSize: 12, color: "#7c2d12", marginTop: 10, background: "#fff7ed", padding: 8, borderRadius: 4 }}>
                ⚠ {list.find((v) => v.is_latest)!.caveat}
              </p>
            )}
          </div>
        ))
      )}
    </div>
  );
}

const th: React.CSSProperties = { padding: "6px 8px", color: "#64748b", fontWeight: 600 };
const td: React.CSSProperties = { padding: "6px 8px" };
const linkBtn: React.CSSProperties = { border: "none", background: "none", color: "#3b82f6", cursor: "pointer", fontSize: 12, padding: 0 };
