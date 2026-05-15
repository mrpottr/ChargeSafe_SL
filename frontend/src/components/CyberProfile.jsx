import React, { useEffect, useMemo, useState } from "react";

const riskBadgeMap = {
  LOW: "green",
  MEDIUM: "amber",
  HIGH: "red",
  CRITICAL: "red",
};

const getRiskBadge = (riskLevel = "LOW") => riskBadgeMap[riskLevel] || "amber";

const formatRiskTitle = (riskLevel = "LOW") => `${riskLevel} RISK`;

const formatTimestamp = (value) => {
  if (!value) return "No scans recorded";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "No scans recorded";
  return parsed.toLocaleString("en-GB");
};

function CyberProfile({ currentStation, authApi, nav, addToast }) {
  const [cyberProfile, setCyberProfile] = useState(null);
  const [cyberBusy, setCyberBusy] = useState(false);

  useEffect(() => {
    if (!currentStation?.id) return undefined;

    let cancelled = false;

    const loadCyberProfile = async () => {
      setCyberBusy(true);
      try {
        const data = await authApi(`/stations/${currentStation.id}/cyber-score`);
        if (!cancelled) {
          setCyberProfile(data);
        }
      } catch (error) {
        if (!cancelled) {
          setCyberProfile(null);
          addToast(error.message || "Unable to load cyber profile", "warn");
        }
      } finally {
        if (!cancelled) {
          setCyberBusy(false);
        }
      }
    };

    loadCyberProfile();

    return () => {
      cancelled = true;
    };
  }, [currentStation?.id, authApi, addToast]);

  const breakdown = cyberProfile?.breakdown || [];
  const riskLevel = cyberProfile?.overall_risk_level || "LOW";
  const badge = getRiskBadge(riskLevel);

  const flaggedVulnerabilities = useMemo(
    () =>
      breakdown.filter((item) => {
        const itemRisk = item.risk_rating || "";
        return item.score_value >= 4 || itemRisk === "HIGH" || itemRisk === "CRITICAL";
      }),
    [breakdown]
  );

  const complianceSummary = useMemo(() => {
    if (!breakdown.length) {
      return {
        iec: "PENDING",
        owasp: "PENDING",
      };
    }

    const hasHighRisk = breakdown.some((item) => (item.risk_rating || "").match(/HIGH|CRITICAL/));
    const hasMediumRisk = breakdown.some((item) => item.risk_rating === "MEDIUM" || item.score_value === 2);

    return {
      iec: hasHighRisk ? "NON-COMPLIANT" : hasMediumRisk ? "PARTIAL" : "COMPLIANT",
      owasp: hasHighRisk ? "HIGH EXPOSURE" : hasMediumRisk ? "PARTIAL" : "ALIGNED",
    };
  }, [breakdown]);

  return (
    <div className="view active" style={{ padding: "24px" }}>
      <div className="flex-between mb24">
        <div>
          <div className="page-label" style={{ color: "var(--cyan)" }}>
            // CYBER SECURITY ANALYSIS
          </div>
          <div className="page-title" style={{ fontSize: "24px" }}>
            CYBER SECURITY ANALYSIS
          </div>
        </div>
        <button className="btn btn-ghost" onClick={() => nav("station")}>
          ← STATION DETAILS
        </button>
      </div>

      <div className="grid2 mb24">
        <div className="card" style={{ padding: "20px" }}>
          <div className="card-header">
            <span className="card-title">Overall Risk Rating (FR-28)</span>
            <span className={`badge badge-${badge}`}>{formatRiskTitle(riskLevel)}</span>
          </div>
          <div style={{ textAlign: "center", padding: "24px 0" }}>
            <div style={{ fontSize: "10px", color: "var(--txt3)", marginBottom: "8px", fontFamily: "Fira Code" }}>
              COMPOSITE SECURITY SCORE
            </div>
            <div className={badge} style={{ fontSize: "56px", fontWeight: 800, fontFamily: "Orbitron" }}>
              {cyberProfile ? cyberProfile.overall_score.toFixed(1) : "--"}
            </div>
            <div style={{ marginTop: "12px", fontSize: "11px", color: "var(--txt2)" }}>
              Last scan: {formatTimestamp(breakdown[0]?.evaluated_at)}
            </div>
            {cyberBusy && (
              <div style={{ marginTop: "12px", fontSize: "11px", color: "var(--txt3)" }}>
                Loading live cyber profile...
              </div>
            )}
          </div>
        </div>

        <div className="card" style={{ padding: "20px" }}>
          <div className="card-header">
            <span className="card-title">Compliance Status</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginTop: "10px" }}>
            <div
              className="flex-between"
              style={{ padding: "12px", background: "rgba(255,255,255,0.03)", borderRadius: "4px", border: "1px solid var(--border)" }}
            >
              <div style={{ fontSize: "12px", fontWeight: 500 }}>IEC 62443 Standard</div>
              <span className={`badge badge-${complianceSummary.iec === "COMPLIANT" ? "green" : complianceSummary.iec === "PARTIAL" ? "amber" : "red"}`}>
                {complianceSummary.iec}
              </span>
            </div>
            <div
              className="flex-between"
              style={{ padding: "12px", background: "rgba(255,255,255,0.03)", borderRadius: "4px", border: "1px solid var(--border)" }}
            >
              <div style={{ fontSize: "12px", fontWeight: 500 }}>OWASP IoT Top 10</div>
              <span className={`badge badge-${complianceSummary.owasp === "ALIGNED" ? "green" : complianceSummary.owasp === "PARTIAL" ? "amber" : "red"}`}>
                {complianceSummary.owasp}
              </span>
            </div>
            <div
              className="flex-between"
              style={{ padding: "12px", background: "rgba(255,255,255,0.03)", borderRadius: "4px", border: "1px solid var(--border)" }}
            >
              <div style={{ fontSize: "12px", fontWeight: 500 }}>Assessed Criteria</div>
              <span className="badge badge-cyan">{cyberProfile?.criteria_count ?? 0}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="card mb24" style={{ padding: "20px" }}>
        <div className="card-header">
          <span className="card-title">Criterion Breakdown (FR-25)</span>
        </div>
        {!breakdown.length && !cyberBusy ? (
          <div style={{ fontSize: "12px", color: "var(--txt3)", padding: "8px 0" }}>
            No cyber score records exist for this station yet. Add rows to the <span className="mono">cyber_scores</span> table to display live results.
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Criterion</th>
                <th>Reference</th>
                <th>Weight</th>
                <th>Score</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {breakdown.map((item) => {
                const itemBadge = getRiskBadge(item.risk_rating || "MEDIUM");
                return (
                  <tr key={item.criterion_id}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{item.criterion_name}</div>
                      <div style={{ fontSize: "11px", color: "var(--txt3)", marginTop: "4px" }}>{item.description}</div>
                    </td>
                    <td style={{ fontSize: "11px", color: "var(--txt2)" }}>{item.iec_reference || "-"}</td>
                    <td className="mono">{item.weight}</td>
                    <td className="mono">{item.score_value}</td>
                    <td>
                      <span className={`badge badge-${itemBadge}`}>{item.risk_rating || "MEDIUM"}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <div className="card" style={{ padding: "20px" }}>
        <div className="card-header">
          <span className="card-title">Flagged High-Risk Vulnerabilities (FR-302)</span>
        </div>
        {!flaggedVulnerabilities.length ? (
          <div style={{ fontSize: "12px", color: "var(--txt3)", padding: "8px 0" }}>
            No high-risk vulnerabilities are currently flagged for this station.
          </div>
        ) : (
          <div style={{ display: "grid", gap: "12px" }}>
            {flaggedVulnerabilities.map((item) => (
              <div
                key={`risk-${item.criterion_id}`}
                style={{
                  padding: "14px",
                  border: "1px solid rgba(255,68,68,0.25)",
                  background: "rgba(255,68,68,0.06)",
                  borderRadius: "6px",
                }}
              >
                <div className="flex-between" style={{ gap: "12px" }}>
                  <div style={{ fontWeight: 700, color: "var(--red)" }}>{item.criterion_name}</div>
                  <span className="badge badge-red">{item.risk_rating || "HIGH"}</span>
                </div>
                <div style={{ fontSize: "12px", color: "var(--txt2)", marginTop: "8px", lineHeight: "1.7" }}>
                  {item.notes || item.description || "No vulnerability notes were supplied for this criterion."}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default CyberProfile;
