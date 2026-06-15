const json = (r) => {
  if (!r.ok) throw new Error(`API ${r.status}`);
  return r.json();
};

export const api = {
  projects: () => fetch('/api/projects').then(json),
  createProject: (name, repo_url) =>
    fetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, repo_url }),
    }).then(json),
  deleteProject: (projectId) =>
    fetch(`/api/projects/${projectId}`, { method: 'DELETE' }).then(json),
  startScan: (projectId) =>
    fetch(`/api/projects/${projectId}/scans`, { method: 'POST' }).then(json),
  scan: (scanId) => fetch(`/api/scans/${scanId}`).then(json),
  deleteScan: (scanId) =>
    fetch(`/api/scans/${scanId}`, { method: 'DELETE' }).then(json),
  findings: (scanId, filters = {}) => {
    const qs = new URLSearchParams(
      Object.entries(filters).filter(([, v]) => v)
    ).toString();
    return fetch(`/api/scans/${scanId}/findings${qs ? `?${qs}` : ''}`).then(json);
  },
  setStatus: (findingId, status) =>
    fetch(`/api/findings/${findingId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    }).then(json),
};
