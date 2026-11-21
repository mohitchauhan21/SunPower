// Shared building blocks for the staff workspace (/app).
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { del, fmtDate, patch, post } from '../api.js';
import { useAuth } from '../auth.jsx';
import { useToast } from '../components/ui/Toast.jsx';

/** What the signed-in person may do in a module: { read, write, del } (from me.modules). */
export function useCan(key) {
  const { me } = useAuth();
  const m = (me?.modules || []).find((x) => x.key === key);
  return { read: !!m, write: m?.level === 'rw', own: m?.level === 'own', del: !!m?.delete };
}

/** Red "Delete" button: asks to confirm, deletes, then goes to `after` (or calls onDone). */
export function DeleteButton({ url, what, after, onDone, label = 'Delete', small = true }) {
  const navigate = useNavigate();
  const { busy, run } = useAction();
  const go = async () => {
    if (!window.confirm(`Delete ${what}? This can’t be undone.`)) return;
    const r = await run('del', () => del(url), `Deleted ${what}.`);
    if (!r) return;
    if (onDone) onDone();
    if (after) navigate(after, { replace: true });
  };
  return <button type="button" className={`btn btn--danger${small ? ' btn--sm' : ''}`} disabled={!!busy} onClick={go}>{label}</button>;
}

/** Load data from the server; reload() re-fetches. */
export function useLoad(fn, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fnRef.current());
      setError('');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { reload(); }, [reload]);
  return { data, error, loading, reload, setData };
}

/** Run an action with a busy flag, a success toast and an error toast. */
export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState('');
  const run = useCallback(async (key, fn, okMsg) => {
    setBusy(key);
    try {
      const r = await fn();
      if (okMsg) toast(typeof okMsg === 'function' ? okMsg(r) : okMsg);
      return r ?? true;
    } catch (err) {
      toast(err.message, 'error');
      return null;
    } finally {
      setBusy('');
    }
  }, [toast]);
  return { busy, run };
}

export function PageHead({ eyebrow, title, sub, back, children }) {
  return (
    <header className="ws-head">
      <div>
        {back && <Link to={back.to} className="ws-back">‹ {back.label}</Link>}
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h1 className="ws-title">{title}</h1>
        {sub && <p className="muted ws-sub">{sub}</p>}
      </div>
      {children && <div className="ws-head__actions">{children}</div>}
    </header>
  );
}

const TONES = {
  ok: ['approved', 'done', 'sale', 'paid', 'closed', 'disbursed', 'won', 'active', 'in_stock'],
  warn: ['scheduled', 'sent', 'ready', 'in_progress', 'repair', 'awaiting', 'diagnosed', 'applied', 'inspection', 'contacted', 'survey', 'quoted', 'posted', 'waiting'],
  bad: ['rejected', 'cancel', 'lost', 'expired', 'failed'],
};
export function Pill({ state, children }) {
  const tone = Object.keys(TONES).find((k) => TONES[k].includes(state));
  return <span className={`pill ${tone ? `pill--${tone}` : ''}`}>{children || state}</span>;
}

export function Loading() {
  return <div className="skeleton" aria-busy="true"><div /><div /><div /></div>;
}

export function ErrorBox({ error, onRetry }) {
  return (
    <div className="card card--alt empty-state">
      <h3>Something went wrong.</h3>
      <p className="muted">{error}</p>
      {onRetry && <button type="button" className="btn btn--primary btn--sm" onClick={onRetry}>Try again</button>}
    </div>
  );
}

/** Data table. columns: [{key, label, render?, num?}] ; onRow(row) makes rows clickable links. */
export function Table({ columns, rows, rowLink, empty = 'Nothing here yet.' }) {
  return (
    <div className="table-card">
      <div className="table-scroll">
        <table className="table">
          <thead><tr>{columns.map((c) => <th key={c.key} className={c.num ? 'num' : ''}>{c.label}</th>)}</tr></thead>
          <tbody>
            {rows.length ? rows.map((r) => (
              <tr key={r.id ?? JSON.stringify(r)} className={rowLink ? 'is-link' : ''}>
                {columns.map((c, i) => {
                  const v = c.render ? c.render(r) : r[c.key];
                  return (
                    <td key={c.key} className={c.num ? 'num' : ''}>
                      {rowLink && i === 0 ? <Link to={rowLink(r)} className="row-link">{v}</Link> : v}
                    </td>
                  );
                })}
              </tr>
            )) : <tr><td colSpan={columns.length} className="empty">{empty}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Search({ value, onChange, placeholder = 'Search' }) {
  const [v, setV] = useState(value || '');
  useEffect(() => { const t = setTimeout(() => v !== value && onChange(v), 300); return () => clearTimeout(t); }, [v]); // eslint-disable-line
  return <input className="input search" type="search" placeholder={placeholder} aria-label={placeholder} value={v} onChange={(e) => setV(e.target.value)} />;
}

/** Filter chips: options [{value,label,count?}] */
export function Chips({ options, value, onChange }) {
  return (
    <div className="chips" role="tablist">
      {options.map((o) => (
        <button key={o.value} type="button" role="tab" aria-selected={value === o.value}
                className={`chip${value === o.value ? ' is-active' : ''}`} onClick={() => onChange(o.value)}>
          {o.label}{o.count != null && <span className="chip__n">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Section({ title, actions, children, className = '' }) {
  return (
    <section className={`ws-card ${className}`}>
      {(title || actions) && <div className="ws-card__head"><h3>{title}</h3>{actions}</div>}
      {children}
    </section>
  );
}

export function KV({ items }) {
  return (
    <dl className="ws-kv">
      {items.filter(Boolean).map(([k, v]) => (
        <div key={k}><dt>{k}</dt><dd>{v === null || v === undefined || v === '' ? '—' : v}</dd></div>
      ))}
    </dl>
  );
}

/** Labelled input. type: text|number|date|datetime-local|select|textarea|checkbox */
export function F({ label, value, onChange, type = 'text', options, disabled, hint, full, ...rest }) {
  const id = useRef('f' + Math.random().toString(36).slice(2, 8)).current;
  if (type === 'checkbox') {
    return (
      <label className={`ws-check${full ? ' field--full' : ''}`}>
        <input type="checkbox" checked={!!value} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
        <span>{label}</span>
      </label>
    );
  }
  const common = { id, className: type === 'select' ? 'select' : type === 'textarea' ? 'textarea' : 'input', disabled,
    value: value ?? '', ...rest };
  return (
    <div className={`field${full ? ' field--full' : ''}`}>
      <label className="label" htmlFor={id}>{label}</label>
      {type === 'select' ? (
        <select {...common} onChange={(e) => onChange(e.target.value)}>
          {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      ) : type === 'textarea' ? (
        <textarea {...common} rows={rest.rows || 3} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input {...common} type={type} onChange={(e) => onChange(type === 'number' ? (e.target.value === '' ? '' : Number(e.target.value)) : e.target.value)} />
      )}
      {hint && <span className="form-hint">{hint}</span>}
    </div>
  );
}

/** Timeline of notes + a box to add one. */
export function Notes({ model, id, notes, reload }) {
  const [text, setText] = useState('');
  const { busy, run } = useAction();
  const { me } = useAuth();
  const editNote = async (n) => {
    const body = window.prompt('Edit note', n.body);
    if (body === null || body.trim() === n.body) return;
    if (await run('note', () => patch(`/api/staff/notes/${n.id}`, { body }), 'Note updated.')) reload();
  };
  const removeNote = async (n) => {
    if (!window.confirm('Delete this note?')) return;
    if (await run('note', () => del(`/api/staff/notes/${n.id}`), 'Note deleted.')) reload();
  };
  const add = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    if (await run('note', () => post('/api/staff/notes', { model, res_id: id, body: text }), 'Note added.')) {
      setText('');
      reload();
    }
  };
  return (
    <Section title="Activity">
      <form className="ws-note-form" onSubmit={add}>
        <input className="input" placeholder="Add a note for the team…" value={text} onChange={(e) => setText(e.target.value)} />
        <button className="btn btn--secondary btn--sm" disabled={busy || !text.trim()}>Add</button>
      </form>
      <ol className="ws-timeline">
        {(notes || []).map((n) => {
          // Typed notes can be edited by their author and deleted by their author or the Director.
          const mine = n.kind === 'note' && n.author_id === me?.id;
          const canDel = n.kind === 'note' && (mine || me?.role === 'director');
          return (
            <li key={n.id} className={n.kind === 'note' ? 'is-note' : ''}>
              <p>{n.body}</p>
              <span className="muted small">
                {n.author || 'System'} · {fmtDate(n.created_at, true)}
                {mine && <> · <button type="button" className="link--btn note-act" onClick={() => editNote(n)}>Edit</button></>}
                {canDel && <> · <button type="button" className="link--btn note-act" onClick={() => removeNote(n)}>Delete</button></>}
              </span>
            </li>
          );
        })}
        {!notes?.length && <li className="muted small">No activity yet.</li>}
      </ol>
    </Section>
  );
}

export const toLocalInput = (v) => {
  if (!v) return '';
  const d = new Date(String(v).replace(' ', 'T'));
  if (Number.isNaN(d.getTime())) return '';
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
};
export const fromLocalInput = (v) => (v ? v.replace('T', ' ') + ':00' : null);
