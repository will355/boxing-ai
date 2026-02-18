const { useEffect, useMemo, useState } = React;

function num(v, digits = 3) {
  if (v === undefined || v === null || Number.isNaN(Number(v))) return "-";
  return Number(v).toFixed(digits);
}

function App() {
  const [health, setHealth] = useState({ ok: false, text: "Checking API status..." });
  const [presets, setPresets] = useState(["balanced"]);
  const [settings, setSettings] = useState({
    preset: "balanced",
    min_confidence: 0.35,
    min_visibility: 0.5,
    speed_threshold: 0.022,
    extension_threshold: 0.006,
    elbow_angle_threshold: 120,
    cooldown_sec: 0.15,
    combo_gap_sec: 0.8,
    timeline_bucket_sec: 10,
  });
  const [file, setFile] = useState(null);
  const [runStatus, setRunStatus] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch("/health")
      .then((r) => r.json())
      .then((data) => {
        setHealth({
          ok: data.status === "ok",
          text: data.status === "ok" ? "API online" : "API returned non-ok status",
        });
      })
      .catch(() => setHealth({ ok: false, text: "API unreachable" }));

    fetch("/settings-presets")
      .then((r) => r.json())
      .then((data) => {
        const keys = Object.keys(data.preset_overrides || {});
        if (keys.length > 0) setPresets(keys);
      })
      .catch(() => {});
  }, []);

  const cards = useMemo(() => {
    if (!result || !result.video_stats) return [];
    const stats = result.video_stats;
    const analytics = stats.analytics || {};
    return [
      { label: "Counted punches", value: stats.counted_punches ?? "-" },
      { label: "Raw detections", value: stats.detected_punches_raw ?? "-" },
      { label: "Pose coverage", value: num(stats.pose_coverage, 2) },
      { label: "Punches / minute", value: analytics.punches_per_minute ?? "-" },
      { label: "Combo count", value: analytics.combo_count ?? "-" },
      { label: "Max combo", value: analytics.max_combo ?? "-" },
    ];
  }, [result]);

  function onSettingChange(e) {
    const { name, value } = e.target;
    setSettings((prev) => ({ ...prev, [name]: value }));
  }

  function buildFormData() {
    const fd = new FormData();
    if (file) fd.append("file", file);
    Object.entries(settings).forEach(([k, v]) => fd.append(k, v));
    return fd;
  }

  async function analyze(e) {
    e.preventDefault();
    if (!file) {
      setRunStatus("Select a video file first.");
      return;
    }
    setBusy(true);
    setRunStatus("Analyzing video...");
    setResult(null);
    try {
      const res = await fetch("/upload", { method: "POST", body: buildFormData() });
      if (!res.ok) throw new Error("Upload failed");
      const json = await res.json();
      setResult(json);
      setRunStatus("Analysis complete.");
    } catch (err) {
      setRunStatus(`Error: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function downloadCsv() {
    if (!file) {
      setRunStatus("Select a video file first.");
      return;
    }
    setBusy(true);
    setRunStatus("Preparing CSV...");
    try {
      const res = await fetch("/upload-csv", { method: "POST", body: buildFormData() });
      if (!res.ok) throw new Error("CSV export failed");
      const blob = await res.blob();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `${file.name.replace(/\.[^.]+$/, "")}_events.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setRunStatus("CSV downloaded.");
    } catch (err) {
      setRunStatus(`Error: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  const events = result?.video_stats?.punch_events || [];

  return (
    <main className="shell">
      <section className="hero">
        <h1>Boxing AI Console</h1>
        <p>Upload footage, tune detection, and inspect punch analytics.</p>
        <div className="status-row">
          <span className={`dot ${health.ok ? "ok" : "bad"}`}></span>
          <span>{health.text}</span>
        </div>
      </section>

      <section className="panel">
        <h2>Analyze Video</h2>
        <form onSubmit={analyze}>
          <div className="grid">
            <label>Video file
              <input type="file" accept="video/*" required onChange={(e) => setFile(e.target.files?.[0] || null)} />
            </label>
            <label>Preset
              <select name="preset" value={settings.preset} onChange={onSettingChange}>
                {presets.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
            <label>Min confidence
              <input name="min_confidence" value={settings.min_confidence} type="number" min="0" max="1" step="0.01" onChange={onSettingChange} />
            </label>
            <label>Min visibility
              <input name="min_visibility" value={settings.min_visibility} type="number" min="0" max="1" step="0.01" onChange={onSettingChange} />
            </label>
            <label>Speed threshold
              <input name="speed_threshold" value={settings.speed_threshold} type="number" min="0" step="0.001" onChange={onSettingChange} />
            </label>
            <label>Extension threshold
              <input name="extension_threshold" value={settings.extension_threshold} type="number" min="0" step="0.001" onChange={onSettingChange} />
            </label>
            <label>Elbow angle threshold
              <input name="elbow_angle_threshold" value={settings.elbow_angle_threshold} type="number" min="60" max="180" step="1" onChange={onSettingChange} />
            </label>
            <label>Cooldown (sec)
              <input name="cooldown_sec" value={settings.cooldown_sec} type="number" min="0" step="0.01" onChange={onSettingChange} />
            </label>
            <label>Combo gap (sec)
              <input name="combo_gap_sec" value={settings.combo_gap_sec} type="number" min="0" step="0.01" onChange={onSettingChange} />
            </label>
            <label>Timeline bucket (sec)
              <input name="timeline_bucket_sec" value={settings.timeline_bucket_sec} type="number" min="1" step="1" onChange={onSettingChange} />
            </label>
          </div>
          <div className="actions">
            <button type="submit" disabled={busy}>Analyze</button>
            <button type="button" disabled={busy} onClick={downloadCsv}>Download CSV</button>
          </div>
        </form>
        <p className="status">{runStatus}</p>
      </section>

      {result && (
        <section className="panel">
          <h2>Results</h2>
          <div className="cards">
            {cards.map((c) => (
              <article key={c.label} className="card">
                <p>{c.label}</p>
                <strong>{c.value}</strong>
              </article>
            ))}
          </div>
          <h3>Top Events</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>t (s)</th>
                  <th>Hand</th>
                  <th>Type</th>
                  <th>Conf.</th>
                  <th>Counted</th>
                </tr>
              </thead>
              <tbody>
                {events.slice(0, 40).map((e, idx) => (
                  <tr key={`${e.frame}-${idx}`}>
                    <td>{num(e.time_sec, 3)}</td>
                    <td>{e.hand}</td>
                    <td>{e.type}</td>
                    <td>{num(e.confidence, 2)}</td>
                    <td>{e.counted ? "yes" : "no"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <details>
            <summary>Raw JSON</summary>
            <pre>{JSON.stringify(result, null, 2)}</pre>
          </details>
        </section>
      )}
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
