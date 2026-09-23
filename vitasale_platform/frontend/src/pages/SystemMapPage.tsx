import { useSystemMap } from "../hooks/useAnalytics";
import { ProvenanceBadge } from "../components/ProvenanceBadge";
import type { DerivedTable, NamedItem, SourceTable } from "../api/analytics";

const CARD: React.CSSProperties = {
  background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 20, marginBottom: 20,
};
const SECTION_TITLE: React.CSSProperties = {
  fontSize: 14, color: "#475569", textTransform: "uppercase", letterSpacing: 0.5, marginTop: 32, marginBottom: 4,
};
const SECTION_SUB: React.CSSProperties = { fontSize: 13, color: "#94a3b8", marginTop: 0, marginBottom: 14 };
const TH: React.CSSProperties = { padding: "6px 8px", color: "#64748b", fontWeight: 600, textAlign: "left" };
const TD: React.CSSProperties = { padding: "6px 8px", verticalAlign: "top" };

const FLOW_STAGES = [
  "Source tables\n(real MDB)", "Ingestion\n(pull / upload)", "Pipeline transform\n(extract → events → features → aggregates)",
  "Derived tables\n(feature_snapshot, timeseries)", "Training\n(forecast + propensity)", "Predict + Analytics\n(16 predictions, 3 cards)",
];

export function SystemMapPage() {
  const { data, isLoading, error } = useSystemMap();

  return (
    <div>
      <h1 style={{ fontSize: 22, marginBottom: 4 }}>System Map</h1>
      <p style={{ color: "#64748b", fontSize: 14, marginTop: 0, marginBottom: 24 }}>
        Where every table comes from, how it's transformed, what's been built, and what's real
        versus preview — end to end, in one place.
      </p>

      {isLoading && <p style={{ fontSize: 13, color: "#94a3b8" }}>Loading…</p>}
      {error && <p style={{ fontSize: 13, color: "#991b1b" }}>Couldn't load — try refreshing.</p>}
      {data && (
        <>
          {/* --- Flow diagram --- */}
          <div style={{ ...CARD, overflowX: "auto" }}>
            <div style={{ display: "flex", alignItems: "stretch", gap: 4, minWidth: 900 }}>
              {FLOW_STAGES.map((stage, i) => (
                <div key={stage} style={{ display: "flex", alignItems: "center", flex: 1 }}>
                  <div style={{
                    flex: 1, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8,
                    padding: "12px 10px", fontSize: 12.5, fontWeight: 600, color: "#1e293b",
                    textAlign: "center", whiteSpace: "pre-line", lineHeight: 1.4,
                  }}>
                    {stage}
                  </div>
                  {i < FLOW_STAGES.length - 1 && (
                    <div style={{ padding: "0 6px", color: "#cbd5e1", fontSize: 18 }}>→</div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* --- 1. Source tables --- */}
          <h2 style={SECTION_TITLE}>1. Source tables — where we picked what</h2>
          <p style={SECTION_SUB}>The real, pre-existing MDB tables this platform reads from.</p>
          <div style={CARD}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #e2e8f0" }}>
                  <th style={TH}>Table</th><th style={TH}>Rows</th><th style={TH}>What we use it for</th><th style={TH}>Fields used</th>
                </tr>
              </thead>
              <tbody>
                {data.source_tables.map((t: SourceTable) => (
                  <tr key={t.name} style={{ borderBottom: "1px solid #f1f5f9" }}>
                    <td style={{ ...TD, fontWeight: 600, fontFamily: "ui-monospace, monospace", fontSize: 12.5 }}>{t.name}</td>
                    <td style={{ ...TD, color: t.row_count === 0 ? "#dc2626" : "#94a3b8" }}>{t.row_count.toLocaleString()}</td>
                    <td style={TD}>{t.description}</td>
                    <td style={{ ...TD, color: "#94a3b8", fontSize: 12 }}>{t.fields_used.join(", ") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* --- 2 & 8. Derived tables + REAL/SIMULATED ledger --- */}
          <h2 style={SECTION_TITLE}>2. New tables we've created — and what's real vs. preview</h2>
          <p style={SECTION_SUB}>
            Everything under sales_intelligence_* — every row tagged, nothing blended.
          </p>
          <div style={CARD}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #e2e8f0" }}>
                  <th style={TH}>Table</th><th style={TH}>Rows</th><th style={TH}>Provenance</th><th style={TH}>What it is</th>
                </tr>
              </thead>
              <tbody>
                {data.derived_tables.map((t: DerivedTable) => (
                  <tr key={t.name} style={{ borderBottom: "1px solid #f1f5f9" }}>
                    <td style={{ ...TD, fontWeight: 600, fontFamily: "ui-monospace, monospace", fontSize: 12.5 }}>{t.name}</td>
                    <td style={{ ...TD, color: "#94a3b8" }}>{t.row_count.toLocaleString()}</td>
                    <td style={TD}><ProvenanceBadge provenance={t.provenance} /></td>
                    <td style={TD}>{t.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* --- 3. Transform --- */}
          <h2 style={SECTION_TITLE}>3. How we transformed the data</h2>
          <p style={SECTION_SUB}>Doc §12.1's four stages, run in one of four modes.</p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
            <div style={CARD}>
              <h3 style={{ fontSize: 14, marginTop: 0 }}>Pipeline stages</h3>
              {data.pipeline_stages.map((s, i) => (
                <div key={s.name} style={{ marginBottom: 10 }}>
                  <span style={{ fontWeight: 700, fontSize: 12.5, color: "#0ea5b7" }}>{i + 1}. {s.name}</span>
                  <p style={{ fontSize: 12.5, color: "#64748b", margin: "2px 0 0" }}>{s.description}</p>
                </div>
              ))}
            </div>
            <div style={CARD}>
              <h3 style={{ fontSize: 14, marginTop: 0 }}>Run modes (Transform page)</h3>
              {data.pipeline_modes.map((m) => (
                <div key={m.name} style={{ marginBottom: 10 }}>
                  <span style={{ fontWeight: 700, fontSize: 12.5, color: "#334155" }}>{m.name}</span>
                  <p style={{ fontSize: 12.5, color: "#64748b", margin: "2px 0 0" }}>{m.description}</p>
                </div>
              ))}
            </div>
          </div>

          {/* --- 5. Normalization --- */}
          <h2 style={SECTION_TITLE}>4. How we normalized the data</h2>
          <div style={CARD}>
            {data.normalization.map((n) => (
              <div key={n.name} style={{ marginBottom: 12 }}>
                <span style={{ fontWeight: 700, fontSize: 13 }}>{n.name}</span>
                <p style={{ fontSize: 12.5, color: "#64748b", margin: "2px 0 0" }}>{n.description}</p>
              </div>
            ))}
          </div>

          {/* --- 6. Data flow / options --- */}
          <h2 style={SECTION_TITLE}>5. Where and how we pull, train, and infer — every option</h2>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
            <FlowCard title="Load Data (ingestion)" section={data.flow.ingestion} />
            <FlowCard title="Transform (pipeline)" section={data.flow.transform} />
            <FlowCard title="Train" section={data.flow.training} />
            <FlowCard title="Predict (inference)" section={data.flow.inference} />
            <FlowCard title="Sandbox" section={data.flow.sandbox} />
            <FlowCard title="Analytics" section={data.flow.analytics} />
            <FlowCard title="Assistant (chat)" section={data.flow.assistant} />
          </div>

          {/* --- 7. Predictions count --- */}
          <h2 style={SECTION_TITLE}>6. How many predictions we're doing</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12 }}>
            <StatCard label="Forecast targets" value={data.predictions.forecast_targets} />
            <StatCard label="Propensity targets" value={data.predictions.propensity_targets} />
            <StatCard label="Preview variants" value={data.predictions.simulated_demo_variants} />
            <StatCard label="Total on Predict page" value={data.predictions.total_selectable_in_predict_ui} highlight />
            <StatCard label="Analytics cards built" value={data.predictions.analytics_cards} />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginTop: 20 }}>
            <NamedListCard title="Forecast targets (11)" items={data.predictions.forecast_target_list} accent="#0ea5b7" />
            <NamedListCard title="Propensity targets (2)" items={data.predictions.propensity_target_list} accent="#0ea5b7" />
            <NamedListCard title="Preview variants (3)" items={data.predictions.simulated_demo_list} accent="#a78bfa" />
            <NamedListCard title="Analytics cards built (3)" items={data.predictions.analytics_card_list} accent="#7c2d12" />
          </div>
        </>
      )}
    </div>
  );
}

function FlowCard({ title, section }: { title: string; section: { page?: string; options?: string[]; note?: string; description?: string } }) {
  return (
    <div style={CARD}>
      <h3 style={{ fontSize: 14, marginTop: 0, marginBottom: 8 }}>{title}</h3>
      {section.description && <p style={{ fontSize: 12.5, color: "#64748b", marginTop: 0 }}>{section.description}</p>}
      {section.options && (
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, color: "#334155" }}>
          {section.options.map((o) => <li key={o} style={{ marginBottom: 4 }}>{o}</li>)}
        </ul>
      )}
      {section.note && <p style={{ fontSize: 11.5, color: "#94a3b8", marginTop: 8, marginBottom: 0 }}>{section.note}</p>}
    </div>
  );
}

function StatCard({ label, value, highlight }: { label: string; value: number; highlight?: boolean }) {
  return (
    <div style={{
      ...CARD, marginBottom: 0, textAlign: "center",
      background: highlight ? "#ecfdf5" : "#fff", borderColor: highlight ? "#10b981" : "#e2e8f0",
    }}>
      <div style={{ fontSize: 32, fontWeight: 800, color: highlight ? "#065f46" : "#0f172a" }}>{value}</div>
      <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>{label}</div>
    </div>
  );
}

function NamedListCard({ title, items, accent }: { title: string; items: NamedItem[]; accent: string }) {
  return (
    <div style={CARD}>
      <h3 style={{ fontSize: 14, marginTop: 0, marginBottom: 10 }}>{title}</h3>
      {items.map((item) => (
        <div key={item.key} style={{ marginBottom: 10, paddingLeft: 10, borderLeft: `2px solid ${accent}` }}>
          <div style={{ fontWeight: 600, fontSize: 13, color: "#1e293b" }}>{item.label}</div>
          <div style={{ fontSize: 11.5, color: "#94a3b8", fontFamily: "ui-monospace, monospace", marginTop: 1 }}>{item.key}</div>
          <div style={{ fontSize: 12.5, color: "#64748b", marginTop: 2 }}>{item.blurb}</div>
        </div>
      ))}
    </div>
  );
}
