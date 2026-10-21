import { useCallback, useEffect, useState } from "react";

type Incident = {
  id: string; fingerprint: string; scenario: string; status: string;
  capture_count: number; created_at: string; updated_at: string;
};
type Replay = {
  id: string; capture_id: string; status: string;
  original: { measurements?: { latency_ms?: number; status_code?: number } };
  replay: { injected?: { latency_ms?: number; status_code?: number }; recovery?: { latency_ms?: number; status_code?: number } } | null;
  comparison: { result: string; reason: string; latency_delta_ms: number | null; signature_match: boolean | null } | null;
  error: string | null;
};
type Detail = {
  incident: Incident;
  captures: { id: string; snapshot: { measurements: { latency_ms: number; status_code: number }; captured_at: string } }[];
  replays: Replay[];
  history: { event_type: string; created_at: string; details: Record<string, string> }[];
};

const apiBase = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export default function App() {
  const [apiKey, setApiKey] = useState(sessionStorage.getItem("failure-engine-key") ?? "");
  const [keyInput, setKeyInput] = useState(apiKey);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [statusBusy, setStatusBusy] = useState(false);

  const request = useCallback(async (path: string, init: RequestInit = {}) => {
    const response = await fetch(`${apiBase}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
        ...init.headers,
      },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail ?? `Request failed (${response.status})`);
    }
    return response.json();
  }, [apiKey]);

  const refreshIncidents = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await request("/v1/incidents?limit=50");
      setIncidents(data.items);
      if (!selected && data.items.length) setSelected(data.items[0].id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load incidents");
    } finally {
      setLoading(false);
    }
  }, [request, selected]);

  useEffect(() => {
    if (apiKey) void refreshIncidents();
  }, [apiKey, refreshIncidents]);

  const refreshDetail = useCallback(async () => {
    if (!selected || !apiKey) return;
    try {
      setError("");
      setDetail(await request(`/v1/incidents/${selected}`));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load incident");
    }
  }, [apiKey, request, selected]);

  useEffect(() => {
    setDetail(null);
    void refreshDetail();
  }, [refreshDetail]);

  useEffect(() => {
    if (!detail?.replays.some((replay) => replay.status === "queued" || replay.status === "running")) return;
    const timer = window.setInterval(() => { void refreshDetail(); }, 2500);
    return () => window.clearInterval(timer);
  }, [detail, refreshDetail]);

  async function launchReplay(captureId: string) {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      await request(`/v1/incidents/${selected}/replays`, {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ capture_id: captureId }),
      });
      await refreshDetail();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not queue replay");
    } finally {
      setBusy(false);
    }
  }

  async function changeStatus(status: string) {
    if (!selected) return;
    setStatusBusy(true);
    try {
      await request(`/v1/incidents/${selected}`, { method: "PATCH", body: JSON.stringify({ status }) });
      await refreshIncidents();
      await refreshDetail();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not update incident");
    } finally {
      setStatusBusy(false);
    }
  }

  if (!apiKey) {
    return (
      <main className="auth-shell">
        <form className="auth-card" onSubmit={(event) => {
          event.preventDefault();
          sessionStorage.setItem("failure-engine-key", keyInput);
          setApiKey(keyInput);
        }}>
          <div className="brand-mark">FE</div>
          <p className="eyebrow">PRODUCTION RELIABILITY</p>
          <h1>Failure Engine</h1>
          <p className="muted">Connect to your incident workspace using an organization API key.</p>
          <label htmlFor="api-key">Organization API key</label>
          <input id="api-key" type="password" value={keyInput} onChange={(event) => setKeyInput(event.target.value)} autoComplete="current-password" required />
          <button className="primary" type="submit">Connect workspace</button>
          <small>Key stays in this browser tab and is never included in the build.</small>
        </form>
      </main>
    );
  }

  const current = detail?.incident;
  const chartData = detail?.replays.slice(0, 12).flatMap((replay) => [
    { label: `${replay.id.slice(0, 6)} original`, latency: replay.original.measurements?.latency_ms },
    { label: `${replay.id.slice(0, 6)} injected`, latency: replay.replay?.injected?.latency_ms },
    { label: `${replay.id.slice(0, 6)} recovery`, latency: replay.replay?.recovery?.latency_ms },
  ]).filter((point): point is { label: string; latency: number } => typeof point.latency === "number") ?? [];
  const chartMaximum = Math.max(1, ...chartData.map((point) => point.latency));
  const chartCoordinates = chartData.map((point, index) => ({
    ...point,
    x: chartData.length < 2 ? 320 : 42 + (index * 548) / (chartData.length - 1),
    y: 176 - (point.latency / chartMaximum) * 150,
  }));
  const chartTicks = chartCoordinates.filter((_, index) =>
    index === 0 || index === chartCoordinates.length - 1 || index % Math.ceil(chartCoordinates.length / 6) === 0,
  );

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#"><span className="brand-mark">FE</span> Failure Engine</a>
        <div className="top-actions">
          <span className="live"><i /> API connected</span>
          <button className="subtle" onClick={() => { sessionStorage.removeItem("failure-engine-key"); setApiKey(""); }}>Disconnect</button>
        </div>
      </header>
      <main className="layout">
        <aside className="sidebar">
          <div className="section-heading"><div><p className="eyebrow">WORKSPACE</p><h2>Incidents</h2></div><button className="icon-button" onClick={() => void refreshIncidents()} aria-label="Refresh incidents">↻</button></div>
          <div className="filters">{incidents.length} tracked <span>·</span> latest first</div>
          {loading && <div className="empty">Loading incidents…</div>}
          {!loading && incidents.length === 0 && <div className="empty">No incidents yet. Captures from your SDK will appear here.</div>}
          <nav className="incident-list" aria-label="Incidents">
            {incidents.map((incident) => (
              <button className={`incident-item ${selected === incident.id ? "selected" : ""}`} key={incident.id} onClick={() => setSelected(incident.id)}>
                <span className={`status-dot ${incident.status}`} />
                <span className="incident-copy"><strong>{incident.scenario} failure</strong><small>{new Date(incident.updated_at).toLocaleString()}</small><code>{incident.fingerprint.slice(0, 12)}</code></span>
                <span className="count">{incident.capture_count}</span>
              </button>
            ))}
          </nav>
        </aside>
        <section className="content">
          {error && <div className="error-banner" role="alert"><span>{error}</span><button onClick={() => setError("")}>Dismiss</button></div>}
          {!current && <div className="empty detail-empty">{loading ? "Loading incident…" : "Select an incident to inspect evidence and run a replay."}</div>}
          {current && detail && <>
            <div className="detail-header">
              <div><p className="eyebrow">INCIDENT · {current.id.slice(0, 8)}</p><h1>{current.scenario[0].toUpperCase() + current.scenario.slice(1)} failure</h1><div className="fingerprint">Fingerprint <code>{current.fingerprint}</code></div></div>
              <select disabled={statusBusy} value={current.status} onChange={(event) => void changeStatus(event.target.value)} aria-label="Incident status">
                <option value="open">Open</option><option value="investigating">Investigating</option><option value="resolved">Resolved</option>
              </select>
            </div>
            <div className="stat-grid">
              <article className="stat-card"><span>CAPTURES</span><strong>{detail.captures.length}</strong><small>redacted evidence snapshots</small></article>
              <article className="stat-card"><span>REPLAY RUNS</span><strong>{detail.replays.length}</strong><small>isolated synthetic execution</small></article>
              <article className="stat-card"><span>LATEST RESULT</span><strong className={detail.replays[0]?.comparison?.result === "PASS" ? "pass" : detail.replays[0]?.comparison?.result === "FAIL" ? "fail" : ""}>{detail.replays[0]?.comparison?.result ?? "—"}</strong><small>{detail.replays[0]?.status ?? "No replay submitted"}</small></article>
            </div>
            <section className="panel">
              <div className="panel-heading"><div><h2>Original vs replay</h2><p className="muted">Measured latency in milliseconds. Injected and clean recovery runs are separate.</p></div></div>
              <div className="chart-wrap">
                {chartData.length ? <svg className="latency-chart" viewBox="0 0 640 220" role="img" aria-label="Original, injected replay, and recovery latency comparison">
                  {[0, 1, 2, 3, 4].map((tick) => {
                    const y = 176 - tick * 37.5;
                    return <g key={tick}><line x1="42" y1={y} x2="590" y2={y} stroke="#202b3c" /><text x="37" y={y - 4} textAnchor="end" fill="#8693a8" fontSize="10">{Math.round(chartMaximum * tick / 4)} ms</text></g>;
                  })}
                  {chartCoordinates.length > 1 && <polyline points={chartCoordinates.map((point) => `${point.x},${point.y}`).join(" ")} fill="none" stroke="#59d2b5" strokeWidth="2.5" />}
                  {chartCoordinates.map((point) => <circle key={point.label} cx={point.x} cy={point.y} r="4" fill="#59d2b5"><title>{point.label}: {point.latency} ms</title></circle>)}
                  {chartTicks.map((point) => <text key={`${point.label}-label`} x={point.x} y="201" textAnchor="middle" fill="#8693a8" fontSize="9">{point.label.slice(-8)}</text>)}
                </svg> : <div className="empty">Queue a replay to compare measured original, injected, and recovery latency.</div>}
              </div>
            </section>
            <section className="panel">
              <div className="panel-heading"><div><h2>Evidence & replay history</h2><p className="muted">Every replay is queued asynchronously with a clean recovery check.</p></div></div>
              {detail.captures.length === 0 && <div className="empty">This incident has no captures.</div>}
              {detail.captures.map((capture) => <div className="capture-row" key={capture.id}>
                <div><strong>Capture <code>{capture.id.slice(0, 8)}</code></strong><small>{new Date(capture.snapshot.captured_at).toLocaleString()} · HTTP {capture.snapshot.measurements.status_code} · {capture.snapshot.measurements.latency_ms} ms</small></div>
                <button className="primary compact" disabled={busy} onClick={() => void launchReplay(capture.id)}>{busy ? "Queueing…" : "Run replay"}</button>
              </div>)}
              {detail.replays.map((replay) => <div className="replay-row" key={replay.id}>
                <div className="replay-title"><strong>Replay <code>{replay.id.slice(0, 8)}</code></strong><span className={`result-badge ${(replay.comparison?.result ?? replay.status).toLowerCase()}`}>{replay.comparison?.result ?? replay.status}</span></div>
                {replay.comparison && <p>{replay.comparison.reason}{replay.comparison.signature_match !== null ? ` · fingerprint ${replay.comparison.signature_match ? "matched" : "different"}` : ""}{replay.comparison.latency_delta_ms !== null ? ` · Δ ${replay.comparison.latency_delta_ms} ms` : ""}</p>}
                {replay.error && <p className="error-text">{replay.error}</p>}
              </div>)}
            </section>
            <section className="panel history-panel"><div className="panel-heading"><div><h2>Incident history</h2><p className="muted">Audit events for this organization-scoped incident.</p></div></div>
              {detail.history.map((event, index) => <div className="history-row" key={`${event.event_type}-${index}`}><span className="history-line" /><strong>{event.event_type.replace(".", " ")}</strong><time>{new Date(event.created_at).toLocaleString()}</time></div>)}
            </section>
          </>}
        </section>
      </main>
    </div>
  );
}
