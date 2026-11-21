import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, fmtDate, inr } from '../api.js';
import { useAuth } from '../auth.jsx';
import Tabs from '../components/ui/Tabs.jsx';
import { useToast } from '../components/ui/Toast.jsx';

const TABS = [
  { value: 'overview', label: 'System' },
  { value: 'warranties', label: 'Warranties' },
  { value: 'service', label: 'Service' },
  { value: 'profile', label: 'Profile' }
];
const TICKET_TONE = { new: '', diagnosed: '', repair: 'pill--warn', awaiting: 'pill--warn', closed: 'pill--ok', cancel: '' };

/* ------------------------------------------------------------- overview */
function Tracker({ steps }) {
  const current = steps.findIndex((s) => !s.done);
  return (
    <ol className="track" aria-label="Progress">
      {steps.map((s, i) => (
        <li key={s.label} className={s.done ? 'is-done' : i === current ? 'is-current' : ''}>
          <span className="track__dot" aria-hidden="true">{s.done ? '✓' : i + 1}</span>
          <span className="track__label">{s.label}</span>
          {s.date && <span className="track__date">{fmtDate(s.date)}</span>}
        </li>
      ))}
    </ol>
  );
}

function Overview({ data }) {
  const { enquiries, orders } = data;
  if (!enquiries.length && !orders.length) {
    return (
      <div className="card card--alt empty-state">
        <h3>No solar system on your account yet.</h3>
        <p className="muted">Book a free roof survey and your enquiry, quote and installation will show up here.</p>
        <div className="actions">
          <Link to="/quote" className="btn btn--primary">Book a free survey</Link>
          <Link to="/estimate" className="link">Estimate my savings</Link>
        </div>
      </div>
    );
  }
  return (
    <div className="stack">
      {orders.map((o) => (
        <article key={o.id} className="card card--outline order">
          <header className="order__head">
            <div>
              <h3>{o.kw ? `${o.kw} kW rooftop solar` : 'Solar system'}</h3>
              <p className="muted small">{o.quote_pending ? 'Quotation' : 'Order'} {o.name} · {fmtDate(o.date)}</p>
            </div>
            <span className={`pill ${o.quote_pending ? 'pill--warn' : o.steps[o.steps.length - 1].done ? 'pill--ok' : ''}`}>
              {o.quote_pending ? 'Waiting for your approval' : o.steps[o.steps.length - 1].done ? 'Installed' : 'In progress'}
            </span>
          </header>
          {o.quote_pending ? (
            <p className="muted">Your quotation is ready. Review the price, components and subsidy, then accept it online to confirm your order.</p>
          ) : (
            <>
              <Tracker steps={o.steps} />
              <p className="muted small">Installation checklist: {o.checklist_done} of {o.checklist_total} done</p>
            </>
          )}
          <div className="kv">
            <div><span className="muted">Total</span><strong>{inr(o.total)}</strong></div>
            <div><span className="muted">Paid</span><strong className="good">{inr(o.paid)}</strong></div>
            <div><span className="muted">Balance</span><strong>{inr(o.due)}</strong></div>
            {o.subsidy && <div><span className="muted">Subsidy</span><strong>{o.subsidy.state}</strong></div>}
          </div>
          <div className="actions actions--left">
            {o.quote_pending && <a className="btn btn--primary btn--sm" href={o.review_url} target="_blank" rel="noreferrer">Review &amp; accept quote</a>}
            <a className="btn btn--secondary btn--sm" href={o.pdf_url} target="_blank" rel="noreferrer">Download PDF</a>
          </div>
        </article>
      ))}
      {enquiries.map((e) => (
        <article key={e.id} className="card card--outline order">
          <header className="order__head">
            <div>
              <h3>{e.kw ? `${e.kw} kW enquiry` : 'Solar enquiry'}</h3>
              <p className="muted small">Received {fmtDate(e.created)}</p>
            </div>
            <span className="pill">{e.stage}</span>
          </header>
          <Tracker steps={[
            { label: 'Enquiry received', done: true },
            { label: 'Roof survey', done: !!e.survey && /done|approved/i.test(e.survey.state), date: e.survey?.date },
            { label: 'Quotation', done: false },
          ]} />
          <p className="muted small">
            {e.survey
              ? `Survey: ${e.survey.state}${e.survey.technician ? ` · ${e.survey.technician}` : ''}`
              : 'An advisor will call you within two working hours to book your free roof survey.'}
          </p>
        </article>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------ warranties */
function Warranties({ data, onReport }) {
  if (!data.warranties.length) {
    return <div className="card card--alt empty-state"><h3>No warranties yet.</h3><p className="muted">Every panel, inverter and battery is registered here by serial number on the day it is installed.</p></div>;
  }
  return (
    <ul className="card card--outline wlist">
      {data.warranties.map((w) => (
        <li key={w.id}>
          <div className="wlist__main">
            <strong>{w.product}</strong>
            <span className="muted small">Serial <code>{w.serial}</code> · valid until {fmtDate(w.end)}</span>
          </div>
          <span className={`pill ${w.active ? 'pill--ok' : ''}`}>{w.active ? `Active · ${Math.round(w.days_left / 365 * 10) / 10} yr left` : 'Expired'}</span>
          <button type="button" className="link link--btn" onClick={() => onReport(w.id)}>Report a problem</button>
        </li>
      ))}
    </ul>
  );
}

/* --------------------------------------------------------------- service */
function TicketCard({ t, reload }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [reopen, setReopen] = useState(false);
  const [note, setNote] = useState('');
  const act = async (fn, okMsg) => {
    setBusy(true);
    try {
      const r = await fn();
      if (!r?.ok) throw new Error(r?.error || 'Please try again.');
      toast(okMsg);
      await reload();
    } catch (err) { toast(err.message, 'error'); } finally { setBusy(false); }
  };
  return (
    <article className="card card--outline ticket">
      <header className="order__head">
        <div>
          <h3>{t.name}{t.product ? ` · ${t.product}` : ''}</h3>
          <p className="muted small">Raised {fmtDate(t.reported, true)}{t.technician ? ` · Technician: ${t.technician}` : ''}</p>
        </div>
        <span className={`pill ${TICKET_TONE[t.stage] || ''}`}>{t.stage_label}</span>
      </header>
      <p>{t.description}</p>
      {t.fault_code && <p className="muted small">Error code: {t.fault_code}</p>}
      {t.resolution && <p className="ticket__fix"><strong>What we did:</strong> {t.resolution}</p>}
      <p className="muted small">{t.under_warranty ? 'Covered by warranty: no charge.' : t.charge ? `Charge: ${inr(t.charge)}` : 'Out of warranty: we’ll tell you the cost before any paid work.'}</p>
      {t.can_confirm && !reopen && (
        <div className="confirm">
          <p><strong>Is everything working now?</strong></p>
          <div className="actions actions--left">
            <button type="button" className="btn btn--primary btn--sm" disabled={busy} onClick={() => act(() => api.confirmFix(t.id), 'Thanks! Request closed.')}>Yes, it works</button>
            <button type="button" className="btn btn--secondary btn--sm" disabled={busy} onClick={() => setReopen(true)}>Still not working</button>
          </div>
        </div>
      )}
      {reopen && (
        <div className="confirm">
          <label className="label" htmlFor={`n-${t.id}`}>What’s still wrong?</label>
          <textarea id={`n-${t.id}`} className="textarea" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="actions actions--left">
            <button type="button" className="btn btn--primary btn--sm" disabled={busy} onClick={() => act(() => api.reopenTicket(t.id, note), 'We’ve reopened your request.')}>Send to technician</button>
            <button type="button" className="link link--btn" onClick={() => setReopen(false)}>Cancel</button>
          </div>
        </div>
      )}
    </article>
  );
}

function Service({ data, reload, preselect }) {
  const toast = useToast();
  const [f, setF] = useState({ warranty_id: preselect || '', fault_code: '', description: '' });
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (preselect) setF((s) => ({ ...s, warranty_id: preselect })); }, [preselect]);
  const open = data.tickets.filter((t) => !['closed', 'cancel'].includes(t.stage));
  const past = data.tickets.filter((t) => ['closed', 'cancel'].includes(t.stage));

  const submit = async (e) => {
    e.preventDefault();
    setErr('');
    if (f.description.trim().length < 10) { setErr('Please describe the problem in a few words (at least 10 characters).'); return; }
    setBusy(true);
    try {
      const r = await api.myComplaint({ ...f, warranty_id: f.warranty_id ? Number(f.warranty_id) : null });
      if (!r?.ok) { setErr(r?.error || 'Please try again.'); return; }
      toast(`Request ${r.name} raised. We’ll assign a technician shortly.`);
      setF({ warranty_id: '', fault_code: '', description: '' });
      await reload();
    } catch (ex) { setErr(ex.message); } finally { setBusy(false); }
  };

  return (
    <div className="side-grid">
      <div className="stack">
        {!data.tickets.length && <div className="card card--alt empty-state"><h3>No service requests.</h3><p className="muted">If anything stops working, tell us here. Warranty repairs are free.</p></div>}
        {open.map((t) => <TicketCard key={t.id} t={t} reload={reload} />)}
        {past.length > 0 && <h3 className="subhead">Past requests</h3>}
        {past.map((t) => <TicketCard key={t.id} t={t} reload={reload} />)}
      </div>
      <form className="card card--alt form sticky" onSubmit={submit} noValidate id="complaint">
        <h3>Report a problem</h3>
        {err && <div className="form-error" role="alert">{err}</div>}
        <div className="field">
          <label className="label" htmlFor="c-eq">Which equipment?</label>
          <select id="c-eq" className="select" value={f.warranty_id} onChange={(e) => setF({ ...f, warranty_id: e.target.value })}>
            <option value="">Not sure / whole system</option>
            {data.warranties.map((w) => <option key={w.id} value={w.id}>{w.product} ({w.serial})</option>)}
          </select>
        </div>
        <div className="field">
          <label className="label" htmlFor="c-code">Error code on the inverter <span className="form-hint">(optional)</span></label>
          <input id="c-code" className="input" placeholder="e.g. E021" value={f.fault_code} onChange={(e) => setF({ ...f, fault_code: e.target.value })} />
        </div>
        <div className="field">
          <label className="label" htmlFor="c-desc">What’s wrong?</label>
          <textarea id="c-desc" className="textarea" rows={4} placeholder="e.g. Inverter shows a red light since yesterday and nothing is generated." value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
        </div>
        <button className="btn btn--primary btn--block" disabled={busy}>{busy ? 'Sending…' : 'Send request'}</button>
      </form>
    </div>
  );
}

/* --------------------------------------------------------------- profile */
function Profile({ data, reload }) {
  const toast = useToast();
  const { refresh } = useAuth();
  const c = data.customer;
  const [p, setP] = useState({ name: c.name || '', phone: c.phone || '', street: c.street || '', city: c.city || '' });
  const [pw, setPw] = useState({ old: '', next: '', confirm: '' });
  const [pErr, setPErr] = useState('');
  const [pwErr, setPwErr] = useState('');
  const [busy, setBusy] = useState('');

  const save = async (e) => {
    e.preventDefault();
    setPErr('');
    if (!p.name.trim()) { setPErr('Please enter your name.'); return; }
    setBusy('p');
    try {
      const r = await api.myProfile(p);
      if (!r?.ok) { setPErr(r?.error); return; }
      toast('Details saved.');
      await Promise.all([reload(), refresh()]);
    } catch (ex) { setPErr(ex.message); } finally { setBusy(''); }
  };
  const change = async (e) => {
    e.preventDefault();
    setPwErr('');
    if (pw.next.length < 8) { setPwErr('Use at least 8 characters for the new password.'); return; }
    if (pw.next !== pw.confirm) { setPwErr('The two new passwords don’t match.'); return; }
    setBusy('pw');
    try {
      const r = await api.myPassword(pw.old, pw.next);
      if (!r?.ok) { setPwErr(r?.error); return; }
      toast('Password changed.');
      setPw({ old: '', next: '', confirm: '' });
    } catch (ex) { setPwErr(ex.message); } finally { setBusy(''); }
  };

  return (
    <div className="grid grid--2 align-start">
      <form className="card card--alt form" onSubmit={save} noValidate>
        <h3>Your details</h3>
        {pErr && <div className="form-error" role="alert">{pErr}</div>}
        <div className="field"><label className="label" htmlFor="p-name">Full name</label><input id="p-name" className="input" value={p.name} onChange={(e) => setP({ ...p, name: e.target.value })} /></div>
        <div className="field"><label className="label" htmlFor="p-email">Email</label><input id="p-email" className="input" value={c.email || ''} disabled /><span className="form-hint">Your sign-in email. Call us to change it.</span></div>
        <div className="field"><label className="label" htmlFor="p-phone">Phone</label><input id="p-phone" className="input" type="tel" value={p.phone} onChange={(e) => setP({ ...p, phone: e.target.value })} /></div>
        <div className="field"><label className="label" htmlFor="p-street">Address</label><input id="p-street" className="input" value={p.street} onChange={(e) => setP({ ...p, street: e.target.value })} /></div>
        <div className="field"><label className="label" htmlFor="p-city">City</label><input id="p-city" className="input" value={p.city} onChange={(e) => setP({ ...p, city: e.target.value })} /></div>
        <button className="btn btn--primary" disabled={busy === 'p'}>{busy === 'p' ? 'Saving…' : 'Save details'}</button>
      </form>
      <form className="card card--alt form" onSubmit={change} noValidate>
        <h3>Change password</h3>
        {pwErr && <div className="form-error" role="alert">{pwErr}</div>}
        <div className="field"><label className="label" htmlFor="pw-old">Current password</label><input id="pw-old" className="input" type="password" autoComplete="current-password" value={pw.old} onChange={(e) => setPw({ ...pw, old: e.target.value })} /></div>
        <div className="field"><label className="label" htmlFor="pw-new">New password</label><input id="pw-new" className="input" type="password" autoComplete="new-password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} /></div>
        <div className="field"><label className="label" htmlFor="pw-confirm">Confirm new password</label><input id="pw-confirm" className="input" type="password" autoComplete="new-password" value={pw.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} /></div>
        <button className="btn btn--primary" disabled={busy === 'pw' || !pw.old}>{busy === 'pw' ? 'Saving…' : 'Change password'}</button>
        <p className="form-hint">Forgot it? <Link to="/forgot-password" className="auth__small">Reset by email</Link></p>
      </form>
    </div>
  );
}

/* ------------------------------------------------------------------ page */
export default function Account() {
  const { me } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = TABS.some((t) => t.value === params.get('tab')) ? params.get('tab') : 'overview';
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [preselect, setPreselect] = useState('');

  const load = useCallback(async () => {
    try {
      setError('');
      setData(await api.myOverview());
    } catch (err) {
      setError(err.message || 'We couldn’t load your account.');
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const go = (value) => setParams(value === 'overview' ? {} : { tab: value }, { replace: true });
  const report = (warrantyId) => { setPreselect(String(warrantyId)); go('service'); };
  const openTickets = data?.tickets.filter((t) => !['closed', 'cancel'].includes(t.stage)).length || 0;
  const waiting = data?.tickets.filter((t) => t.can_confirm).length || 0;

  return (
    <>
      <section className="page-head wrap account-head">
        <span className="eyebrow">My account</span>
        <h1 className="headline">Hi, {(data?.customer.name || me?.name || '').split(' ')[0]}.</h1>
        <p className="lead">
          {!data ? 'Loading your account…'
            : waiting ? `${waiting} repair${waiting > 1 ? 's are' : ' is'} waiting for your confirmation.`
            : data.orders.length ? `${data.orders.length} system${data.orders.length > 1 ? 's' : ''} · ${data.warranties.filter((w) => w.active).length} active warranties · ${openTickets} open request${openTickets === 1 ? '' : 's'}`
            : data.enquiries.length ? 'Your enquiry is with our team. Here’s where it stands.'
            : 'Your solar journey starts with a free roof survey.'}
        </p>
      </section>
      <section className="wrap" style={{ paddingBottom: 'clamp(72px, 10vw, 120px)' }}>
        <div className="account-tabs"><Tabs label="Account sections" items={TABS} value={tab} onChange={go} /></div>
        {error && (
          <div className="card card--alt empty-state">
            <h3>Something went wrong.</h3><p className="muted">{error}</p>
            <button type="button" className="btn btn--primary" onClick={load}>Try again</button>
          </div>
        )}
        {!data && !error && <div className="skeleton" aria-busy="true"><div /><div /><div /></div>}
        {data && tab === 'overview' && <Overview data={data} />}
        {data && tab === 'warranties' && <Warranties data={data} onReport={report} />}
        {data && tab === 'service' && <Service data={data} reload={load} preselect={preselect} />}
        {data && tab === 'profile' && <Profile data={data} reload={load} />}
      </section>
    </>
  );
}
