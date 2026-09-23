import { useNbaEffectiveness, useResponseWindow, useResponseWindowSim } from "../hooks/useAnalytics";
import { ProvenanceBadge } from "../components/ProvenanceBadge";

const CARD: React.CSSProperties = {
  background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 20, marginBottom: 20,
};

const PRIORITY_LABELS: Record<string, string> = {
  IMMEDIATE: "Immediate",
  WITHIN_48_HOURS: "Within 48 hours",
  SCHEDULED: "Scheduled",
  NO_ACTION: "No action",
};

export function AnalyticsPage() {
  const { data, isLoading, error } = useNbaEffectiveness();
  const rw = useResponseWindow();
  const rwSim = useResponseWindowSim();

  return (
    <div>
      <h1 style={{ fontSize: 22, marginBottom: 4 }}>Analytics</h1>
      <p style={{ color: "#64748b", fontSize: 14, marginTop: 0, marginBottom: 24 }}>
        Doc §9's high-value use cases, built one at a time — each tagged REAL or PREVIEW,
        never blended.
      </p>

      <div style={CARD}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
          <div>
            <div style={{ fontSize: 12, color: "#94a3b8", textTransform: "uppercase", letterSpacing: 0.5 }}>
              Use case 5 of 8
            </div>
            <h3 style={{ margin: "2px 0 0", fontSize: 18 }}>NBA Effectiveness</h3>
            <p style={{ fontSize: 13, color: "#64748b", marginTop: 4, marginBottom: 0 }}>
              Did leads whose recommended action was acted on progress differently, by how
              urgently it was recommended?
            </p>
          </div>
          {data && <ProvenanceBadge provenance={data.provenance} />}
        </div>

        {isLoading && <p style={{ fontSize: 13, color: "#94a3b8" }}>Loading…</p>}
        {error && <p style={{ fontSize: 13, color: "#991b1b" }}>Couldn't load — try refreshing.</p>}

        {data && (
          <>
            <p style={{ fontSize: 12, color: "#7c2d12", background: "#fff7ed", padding: "10px 12px", borderRadius: 6, lineHeight: 1.5 }}>
              ⚠ {data.caveat}
            </p>

            <div style={{ marginTop: 16 }}>
              {data.breakdown.map((row) => (
                <div key={row.priority} style={{ marginBottom: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
                    <span style={{ fontWeight: 600, color: "#1e293b" }}>
                      {PRIORITY_LABELS[row.priority] ?? row.priority}
                      <span style={{ fontWeight: 400, color: "#94a3b8", marginLeft: 6 }}>n={row.n}</span>
                    </span>
                    <span style={{ fontWeight: 600, color: "#1e293b" }}>
                      {row.acted_on_pct !== null ? `${row.acted_on_pct}%` : "—"}
                    </span>
                  </div>
                  <div style={{ height: 8, background: "#f1f5f9", borderRadius: 4, overflow: "hidden" }}>
                    <div style={{
                      height: "100%", borderRadius: 4, background: "#0ea5b7",
                      width: `${row.acted_on_pct ?? 0}%`,
                    }} />
                  </div>
                </div>
              ))}
            </div>

            <p style={{ fontSize: 11.5, color: "#94a3b8", marginTop: 14, marginBottom: 0 }}>
              {data.total_outcome_rows} preview outcome rows joined against {data.total_feature_rows} real
              leads (seed {data.sim_seed}){data.unmatched_rows > 0 ? `, ${data.unmatched_rows} unmatched` : ""}.
            </p>
          </>
        )}
      </div>

      <div style={CARD}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
          <div>
            <div style={{ fontSize: 12, color: "#94a3b8", textTransform: "uppercase", letterSpacing: 0.5 }}>
              Use case 2 of 8
            </div>
            <h3 style={{ margin: "2px 0 0", fontSize: 18 }}>Response-Window Intelligence</h3>
            <p style={{ fontSize: 13, color: "#64748b", marginTop: 4, marginBottom: 0 }}>
              Does contacting a lead sooner after the NBA associate with more real expressed interest?
            </p>
          </div>
          {rw.data && (
            <div style={{ display: "flex", gap: 6 }}>
              <ProvenanceBadge provenance="SIMULATED" label="Timing" />
              <ProvenanceBadge provenance="REAL" label="Outcome" />
            </div>
          )}
        </div>

        {rw.isLoading && <p style={{ fontSize: 13, color: "#94a3b8" }}>Loading…</p>}
        {rw.error && <p style={{ fontSize: 13, color: "#991b1b" }}>Couldn't load — try refreshing.</p>}

        {rw.data && (
          <>
            <p style={{ fontSize: 12, color: "#7c2d12", background: "#fff7ed", padding: "10px 12px", borderRadius: 6, lineHeight: 1.5 }}>
              ⚠ {rw.data.caveat}
            </p>

            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, marginTop: 16 }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid #e2e8f0" }}>
                  <th style={{ padding: "6px 8px", color: "#64748b", fontWeight: 600 }}>Time to contact</th>
                  <th style={{ padding: "6px 8px", color: "#64748b", fontWeight: 600 }}>Share of all NBA contacts</th>
                  <th style={{ padding: "6px 8px", color: "#64748b", fontWeight: 600 }}>Test drives booked (real)</th>
                  <th style={{ padding: "6px 8px", color: "#64748b", fontWeight: 600 }}>Purchase interest = YES (real)</th>
                </tr>
              </thead>
              <tbody>
                {rw.data.breakdown.map((row) => {
                  const tooSmall = row.n > 0 && row.n < 20;
                  return (
                    <tr key={row.window} style={{ borderBottom: "1px solid #f1f5f9" }}>
                      <td style={{ padding: "6px 8px", fontWeight: 600 }}>{row.window}</td>
                      <td style={{ padding: "6px 8px" }}>
                        <span style={{ fontWeight: 600 }}>{row.n}</span>
                        <span style={{ color: "#94a3b8" }}> leads ({row.pct_of_all_nba ?? 0}% of all {rw.data!.total_nba_suggested})</span>
                      </td>
                      <td style={{ padding: "6px 8px" }}>
                        {row.test_drive_booked} of {rw.data!.total_test_drives_booked} total
                      </td>
                      <td style={{ padding: "6px 8px" }}>
                        {row.n === 0 ? "—" : tooSmall
                          ? <span><span style={{ fontWeight: 600 }}>{row.purchase_interest_yes_count}</span> of {row.n} — too few to read as a rate</span>
                          : `${row.purchase_interest_yes_pct}% (${row.purchase_interest_yes_count} of ${row.n})`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            <p style={{ fontSize: 11.5, color: "#94a3b8", marginTop: 14, marginBottom: 0 }}>
              {rw.data.total_nba_suggested} NBA-suggested contacts total, {rw.data.total_test_drives_booked} real
              test drives booked across all of them (seed {rw.data.sim_seed})
              {rw.data.unmatched_rows > 0 ? `, ${rw.data.unmatched_rows} unmatched` : ""}.
            </p>
          </>
        )}
      </div>

      <div style={{ ...CARD, background: "#faf5ff", border: "1px solid #e9d5ff" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
          <div>
            <div style={{ fontSize: 12, color: "#a78bfa", textTransform: "uppercase", letterSpacing: 0.5 }}>
              Higher-volume preview comparison
            </div>
            <h3 style={{ margin: "2px 0 0", fontSize: 18 }}>Response-Window — More Volume (Preview)</h3>
            <p style={{ fontSize: 13, color: "#64748b", marginTop: 4, marginBottom: 0 }}>
              The real card above has only 20 bookings total — too sparse for most buckets.
              This shows the same breakdown with a larger preview booking volume, kept fully
              separate from the real count.
            </p>
          </div>
          {rwSim.data && (
            <div style={{ display: "flex", gap: 6 }}>
              <ProvenanceBadge provenance="SIMULATED" label="Timing" />
              <ProvenanceBadge provenance="SIMULATED" label="Outcome" />
            </div>
          )}
        </div>

        {rwSim.isLoading && <p style={{ fontSize: 13, color: "#94a3b8" }}>Loading…</p>}
        {rwSim.error && <p style={{ fontSize: 13, color: "#991b1b" }}>Couldn't load — try refreshing.</p>}

        {rwSim.data && (
          <>
            <p style={{ fontSize: 12, color: "#6b21a8", background: "#f3e8ff", padding: "10px 12px", borderRadius: 6, lineHeight: 1.5 }}>
              ⚠ {rwSim.data.caveat}
            </p>

            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, marginTop: 16 }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid #e9d5ff" }}>
                  <th style={{ padding: "6px 8px", color: "#a78bfa", fontWeight: 600 }}>Time to contact</th>
                  <th style={{ padding: "6px 8px", color: "#a78bfa", fontWeight: 600 }}>Share of all NBA contacts</th>
                  <th style={{ padding: "6px 8px", color: "#a78bfa", fontWeight: 600 }}>Test drives booked (preview)</th>
                </tr>
              </thead>
              <tbody>
                {rwSim.data.breakdown.map((row) => {
                  const tooSmall = row.n > 0 && row.n < 20;
                  return (
                    <tr key={row.window} style={{ borderBottom: "1px solid #f3e8ff" }}>
                      <td style={{ padding: "6px 8px", fontWeight: 600 }}>{row.window}</td>
                      <td style={{ padding: "6px 8px" }}>
                        <span style={{ fontWeight: 600 }}>{row.n}</span>
                        <span style={{ color: "#94a3b8" }}> leads ({row.pct_of_all_nba ?? 0}% of all {rwSim.data!.total_nba_suggested})</span>
                      </td>
                      <td style={{ padding: "6px 8px" }}>
                        {row.n === 0 ? "—" : tooSmall
                          ? <span><span style={{ fontWeight: 600 }}>{row.test_drive_booked}</span> of {row.n} — too few to read as a rate</span>
                          : `${row.test_drive_booked_pct}% (${row.test_drive_booked} of ${row.n})`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            <p style={{ fontSize: 11.5, color: "#94a3b8", marginTop: 14, marginBottom: 0 }}>
              {rwSim.data.total_nba_suggested} NBA-suggested contacts total, {rwSim.data.total_test_drives_booked} preview
              test drives booked across all of them (seed {rwSim.data.sim_seed}).
            </p>
          </>
        )}
      </div>
    </div>
  );
}
