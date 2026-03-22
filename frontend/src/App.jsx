import { useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

export default function App() {
  const [health, setHealth] = useState("Checking...");
  const [stations, setStations] = useState([]);

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((response) => response.json())
      .then((data) => setHealth(data.status))
      .catch(() => setHealth("Backend unavailable"));

    fetch(`${API_BASE}/stations`)
      .then((response) => response.json())
      .then((data) => setStations(data))
      .catch(() => setStations([]));
  }, []);

  return (
    <main className="page-shell">
      <section className="hero">
        <p className="eyebrow">ChargeSafe SL</p>
        <h1>EV charging safety monitoring for Sri Lanka.</h1>
        <p className="subtitle">
          FastAPI powers the backend, React handles the interface, and PostgreSQL
          stores the platform data model. The stack is ready for team development
          with a shared Docker workflow.
        </p>
        <div className="status-card">
          <span>API Health</span>
          <strong>{health}</strong>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Recent Charging Stations</h2>
          <p>Showing up to 50 records from the PostgreSQL database.</p>
        </div>

        <div className="station-grid">
          {stations.length === 0 ? (
            <article className="station-card empty-state">
              <h3>No stations yet</h3>
              <p>Add seed data later and they will appear here.</p>
            </article>
          ) : (
            stations.map((station) => (
              <article className="station-card" key={station.id}>
                <h3>{station.name}</h3>
                <p>{station.city || "City not set"}</p>
                <p>Status: {station.status}</p>
                <p>Safety score: {station.safety_score ?? "N/A"}</p>
              </article>
            ))
          )}
        </div>
      </section>
    </main>
  );
}
