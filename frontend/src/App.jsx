import { useCallback, useEffect, useState } from 'react';
import { api } from './api';
import FindingCard from './components/FindingCard';

const SEVERITIES = ['critical', 'high', 'medium', 'low', 'info'];
const SEV_COLORS = {
  critical: 'var(--critical)',
  high: 'var(--high)',
  medium: 'var(--medium)',
  low: 'var(--low)',
  info: 'var(--info)',
};

function Spectrum({ bySeverity }) {
  const total = SEVERITIES.reduce((n, s) => n + (bySeverity?.[s] || 0), 0);
  if (!total) return <div className="spectrum" aria-hidden="true" />;
  return (
    <div className="spectrum" title={`${total} findings`}>
      {SEVERITIES.map((s) =>
        bySeverity?.[s] ? (
          <i
            key={s}
            style={{ width: `${(bySeverity[s] / total) * 100}%`, background: SEV_COLORS[s] }}
          />
        ) : null
      )}
    </div>
  );
}

function NewProject({ onCreated }) {
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const submit = async () => {
    if (!name || !url) return;
    await api.createProject(name, url);
    setName('');
    setUrl('');
    onCreated();
  };
  return (
    <div style={{ marginBottom: 20 }}>
      <h2>New project</h2>
      <input type="text" placeholder="Project name" value={name} onChange={(e) => setName(e.target.value)} />
      <input
        type="text"
        placeholder="Git URL or local path"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
      />
      <button className="primary" onClick={submit} disabled={!name || !url}>
        Add project
      </button>
    </div>
  );
}

export default function App() {
  const [projects, setProjects] = useState([]);
  const [activeScan, setActiveScan] = useState(null);
  const [findings, setFindings] = useState([]);
  const [sevFilter, setSevFilter] = useState(null);
  const [srcFilter, setSrcFilter] = useState(null);
  const [hideClosed, setHideClosed] = useState(true);

  const refreshProjects = useCallback(() => api.projects().then(setProjects), []);
  useEffect(() => {
    refreshProjects();
  }, [refreshProjects]);

  // Poll while a scan is running.
  useEffect(() => {
    const running = activeScan && !['completed', 'failed'].includes(activeScan.status);
    if (!running) return;
    const t = setInterval(async () => {
      const s = await api.scan(activeScan.id);
      setActiveScan(s);
      refreshProjects();
      if (s.status === 'completed') setFindings(await api.findings(s.id));
    }, 1000);  // Poll every 1 second for real-time progress
    return () => clearInterval(t);
  }, [activeScan, refreshProjects]);

  const openScan = async (scan) => {
    setActiveScan(scan);
    setFindings(scan.status === 'completed' ? await api.findings(scan.id) : []);
  };

  const startScan = async (projectId) => {
    const scan = await api.startScan(projectId);
    await refreshProjects();
    openScan(scan);
  };

  const setStatus = async (id, status) => {
    await api.setStatus(id, status);
    setFindings((fs) => fs.map((f) => (f.id === id ? { ...f, status } : f)));
  };

  const deleteScan = async (scanId) => {
    if (!window.confirm('Delete this scan and all its findings?')) return;
    try {
      await api.deleteScan(scanId);
      if (activeScan?.id === scanId) setActiveScan(null);
      await refreshProjects();
    } catch (e) {
      alert(`Failed to delete scan: ${e.message}`);
    }
  };

  const deleteProject = async (projectId) => {
    if (!window.confirm('Delete this project and all its scans?')) return;
    try {
      await api.deleteProject(projectId);
      if (activeScan && projects.find((p) => p.id === projectId)?.scans.some((s) => s.id === activeScan.id)) {
        setActiveScan(null);
      }
      await refreshProjects();
    } catch (e) {
      alert(`Failed to delete project: ${e.message}`);
    }
  };

  const visible = findings.filter(
    (f) =>
      (!sevFilter || f.severity === sevFilter) &&
      (!srcFilter || f.source === srcFilter) &&
      (!hideClosed || f.status === 'open')
  );

  const stats = activeScan?.stats || {};

  return (
    <div className="shell">
      <aside className="sidebar">
        <p className="wordmark">
          review<span>bench</span>
        </p>
        <NewProject onCreated={refreshProjects} />
        <h2>Projects</h2>
        {projects.length === 0 && <p className="muted">No projects yet.</p>}
        {projects.map((p) => (
          <div className="project" key={p.id}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="project-name">{p.name}</span>
              <div>
                <button onClick={() => startScan(p.id)}>Scan</button>
                <button onClick={() => deleteProject(p.id)} style={{ marginLeft: 8 }}>
                  Delete
                </button>
              </div>
            </div>
            <div className="mono muted" style={{ wordBreak: 'break-all' }}>
              {p.repo_url}
            </div>
            {p.scans.map((s) => (
              <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button
                  className={`scan-row ${activeScan?.id === s.id ? 'active' : ''}`}
                  onClick={() => openScan(s)}
                  style={{ flex: 1 }}
                >
                  <span
                    className={`status-dot ${
                      s.status === 'completed'
                        ? 'status-completed'
                        : s.status === 'failed'
                        ? 'status-failed'
                        : 'status-running'
                    }`}
                  />
                  <span className="mono">{s.started_at?.slice(0, 16).replace('T', ' ')}</span>
                  <Spectrum bySeverity={s.stats?.by_severity} />
                </button>
                <button
                  onClick={() => deleteScan(s.id)}
                  style={{ padding: '4px 8px', fontSize: '12px', minWidth: 'auto' }}
                  title="Delete scan"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        ))}
      </aside>

      <main className="main">
        {!activeScan && (
          <div className="empty">
            Add a project and run a scan. Findings from Semgrep and Claude land here, ranked by
            severity.
          </div>
        )}

        {activeScan && (
          <>
            <h2 style={{ fontSize: 20 }}>
              Scan {activeScan.commit_sha ? `@ ${activeScan.commit_sha.slice(0, 8)}` : ''}
            </h2>

            {activeScan.status === 'failed' && (
              <div className="error-box">Scan failed: {activeScan.error}</div>
            )}
            
            {!['completed', 'failed'].includes(activeScan.status) && (
              <>
                <p className="muted">
                  Status: {activeScan.status}… this view refreshes automatically.
                </p>
                {(activeScan.stats?.llm_total_files || activeScan.stats?.files_scanned) && (
                  <div style={{
                    marginTop: 16,
                    padding: 12,
                    border: '1px solid #ddd',
                    borderRadius: 4,
                    backgroundColor: '#f9f9f9'
                  }}>
                    {activeScan.stats?.llm_total_files ? (
                      <>
                        <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 8 }}>
                          AI Review Progress
                        </div>
                        <div style={{
                          width: '100%',
                          height: 20,
                          backgroundColor: '#e0e0e0',
                          borderRadius: 4,
                          overflow: 'hidden',
                          marginBottom: 8
                        }}>
                          <div style={{
                            height: '100%',
                            width: `${activeScan.stats.llm_progress_percent || 0}%`,
                            backgroundColor: '#4CAF50',
                            transition: 'width 0.3s ease',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            color: 'white',
                            fontSize: 12,
                            fontWeight: 500
                          }}>
                            {activeScan.stats.llm_progress_percent > 5 && `${activeScan.stats.llm_progress_percent}%`}
                          </div>
                        </div>
                        <div style={{ fontSize: 12, color: '#666', lineHeight: 1.4 }}>
                          <div>
                            Reviewing file {activeScan.stats.llm_files_reviewed}/{activeScan.stats.llm_total_files}
                          </div>
                          {activeScan.stats.current_file && (
                            <div style={{ color: '#888', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                              Current: {activeScan.stats.current_file}
                            </div>
                          )}
                          {activeScan.stats.estimated_remaining_seconds !== undefined && activeScan.stats.estimated_remaining_seconds > 0 && (
                            <div>
                              Est. time remaining: ~{activeScan.stats.estimated_remaining_seconds}s
                            </div>
                          )}
                        </div>
                      </>
                    ) : (
                      <div style={{ fontSize: 12, color: '#666' }}>
                        Scanning {activeScan.stats?.files_scanned || '?'} files with Semgrep...
                      </div>
                    )}
                  </div>
                )}
              </>
            )}

            {activeScan.status === 'completed' && (
              <>
                <div className="stats">
                  <div className="stat">
                    <span className="n">{stats.findings_total ?? 0}</span>
                    <span className="l">findings</span>
                  </div>
                  <div className="stat">
                    <span className="n">{stats.files_scanned ?? 0}</span>
                    <span className="l">files scanned</span>
                  </div>
                  <div className="stat">
                    <span className="n">{stats.llm_files_reviewed ?? 0}</span>
                    <span className="l">LLM-reviewed</span>
                  </div>
                  <div className="stat">
                    <span className="n">{stats.duration_seconds ?? 0}s</span>
                    <span className="l">duration</span>
                  </div>
                </div>
                {!stats.semgrep_used && (
                  <p className="muted">
                    Semgrep isn't installed, so this scan used LLM review only. Install it with
                    `pip install semgrep` for deterministic coverage.
                  </p>
                )}

                <div className="filters">
                  {SEVERITIES.map((s) => (
                    <button
                      key={s}
                      className={`pill ${sevFilter === s ? 'on' : ''}`}
                      onClick={() => setSevFilter(sevFilter === s ? null : s)}
                    >
                      {s} {stats.by_severity?.[s] || 0}
                    </button>
                  ))}
                  {['semgrep', 'llm'].map((s) => (
                    <button
                      key={s}
                      className={`pill ${srcFilter === s ? 'on' : ''}`}
                      onClick={() => setSrcFilter(srcFilter === s ? null : s)}
                    >
                      {s}
                    </button>
                  ))}
                  <button className={`pill ${hideClosed ? 'on' : ''}`} onClick={() => setHideClosed(!hideClosed)}>
                    open only
                  </button>
                </div>

                {visible.length === 0 && <div className="empty">Nothing matches these filters.</div>}
                {visible.map((f) => (
                  <FindingCard key={f.id} finding={f} onStatus={setStatus} />
                ))}
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}
