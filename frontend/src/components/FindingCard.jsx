import { useState } from 'react';

function Diff({ text }) {
  return (
    <div className="diff">
      {text.split('\n').map((line, i) => {
        const cls = line.startsWith('+') ? 'add' : line.startsWith('-') ? 'del' : 'ctx';
        return (
          <span key={i} className={`ln ${cls}`}>
            {line || ' '}
          </span>
        );
      })}
    </div>
  );
}

export default function FindingCard({ finding, onStatus }) {
  const [open, setOpen] = useState(false);
  const f = finding;
  const dimmed = f.status !== 'open';

  return (
    <article className={`finding ${dimmed ? 'dimmed' : ''}`}>
      <div
        className="finding-head"
        onClick={() => setOpen(!open)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && setOpen(!open)}
      >
        <span className={`sev sev-${f.severity}`}>{f.severity}</span>
        <span className="finding-title">{f.title}</span>
        <span className="loc">
          {f.file_path}:{f.line_start}
          {f.line_end > f.line_start ? `\u2013${f.line_end}` : ''}
        </span>
      </div>

      {open && (
        <div className="finding-body">
          <p style={{ marginTop: 14 }}>
            <span className="badge">{f.source}</span>
            <span className="badge">{f.category}</span>
            {f.confidence != null && (
              <span className="badge">confidence {Math.round(f.confidence * 100)}%</span>
            )}
            {f.rule_id && <span className="badge">{f.rule_id}</span>}
          </p>
          {f.explanation && <p>{f.explanation}</p>}
          {f.suggested_fix && (
            <>
              <p className="muted" style={{ marginBottom: 4 }}>
                Suggested change
              </p>
              <Diff text={f.suggested_fix} />
            </>
          )}
          <div className="actions">
            {f.status !== 'dismissed' && (
              <button onClick={() => onStatus(f.id, 'dismissed')}>Dismiss</button>
            )}
            {f.status !== 'fixed' && (
              <button onClick={() => onStatus(f.id, 'fixed')}>Mark fixed</button>
            )}
            {f.status !== 'open' && (
              <button onClick={() => onStatus(f.id, 'open')}>Reopen</button>
            )}
          </div>
        </div>
      )}
    </article>
  );
}
