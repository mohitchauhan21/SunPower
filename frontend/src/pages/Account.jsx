import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, fmtDate, inr } from '../api.js';
import { useAuth } from '../auth.jsx';
import Tabs from '../components/ui/Tabs.jsx';
import SecuritySettings from '../components/SecuritySettings.jsx';
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

function Overview({ data, reload }) {
  const toast = useToast();
  const { enquiries, orders } = data;
  if (!enquiries.length && !orders.length) {
    return (
      <div className="card card--alt empty-state">
        <h3>No solar system on your account yet.</h3>
        <p className="muted">Book a free roof survey and your enquiry, quote and installation will show up here.</p>
        <div className="actions">
          <Link to="/book-survey" className="btn btn--primary">Book a free survey</Link>
          <Link to="/estimate" className="link">Estimate my savings</Link>
        </div>
      </div>
    );
  }
  return (
    <div className="stack">
      <div className="add-system">
        <div><strong>Want solar on another roof?</strong><span className="muted small"> Add a second system and we’ll book a free survey.</span></div>
        <Link to="/book-survey" className="btn btn--secondary btn--sm">+ Add another system</Link>
      </div>
      {/* Orders and enquiries in one list, newest first (order date / enquiry received; both UTC "YYYY-MM-DD HH:MM:SS") */}
      {[...orders.map((o) => ({ kind: 'order', when: o.date || '', o })), ...enquiries.map((e) => ({ kind: 'enquiry', when: e.created || '', e }))]
        .sort((x, y) => y.when.localeCompare(x.when))
        .map(({ kind, o, e }) => (kind === 'order' ? (
        <article key={`o${o.id}`} className="card card--outline order">
          <header className="order__head">
            <div>
              <h3>{o.kw ? `${o.kw} kW rooftop solar` : 'Solar system'}</h3>
              <p className="muted small">{o.project ? `Project ${o.project} · ` : ''}{o.quote_pending ? 'Quotation' : 'Order'} {o.name} · {fmtDate(o.date)}</p>
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
            {o.quote_pending && <Link className="btn btn--primary btn--sm" to={o.review_url}>Review &amp; accept quote</Link>}
            {!o.quote_pending && o.due > 0.5 && <Link className="btn btn--primary btn--sm" to={o.review_url}>{o.advance_due > 0 ? 'Pay advance' : 'Pay balance'}</Link>}
            {o.certificate_url && <a className="btn btn--secondary btn--sm" href={o.certificate_url} target="_blank" rel="noreferrer">Installation certificate</a>}
            <a className="btn btn--secondary btn--sm" href={o.pdf_url} target="_blank" rel="noreferrer">{o.quote_pending ? 'Quotation PDF' : 'Order PDF'}</a>
          </div>
          {o.invoices?.length > 0 && (
            <div className="invoices">
              <span className="muted small">Invoices</span>
              <ul>
                {o.invoices.map((i) => (
                  <li key={i.id}>
                    <a href={i.url} target="_blank" rel="noreferrer">{i.kind} {i.ref}</a>
                    <span className="muted small">{fmtDate(i.date)}</span>
                    <strong>{inr(i.total)}</strong>
                    <span className={`pill ${i.paid + 0.5 >= i.total ? 'pill--ok' : 'pill--warn'}`}>{i.paid + 0.5 >= i.total ? 'Paid' : `${inr(i.total - i.paid)} due`}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </article>
      ) : (
        <article key={`e${e.id}`} className="card card--outline order">
          <header className="order__head">
            <div>
              <strong className="order__ref">Enquiry {e.name}</strong>
              <h3>{e.kw ? `${e.kw} kW enquiry` : 'Solar enquiry'}</h3>
              <p className="muted small">Project {e.project || e.name} · received {fmtDate(e.created)}</p>
            </div>
            <span className={`pill ${e.closed ? '' : 'pill--warn'}`}>{e.status || e.stage}</span>
          </header>
          <Tracker steps={e.steps || [
            { label: 'Enquiry received', done: true },
            { label: 'Quotation', done: false },
          ]} />
          <p className="small"><strong>Next:</strong> <span className="muted">{e.next}</span></p>
          {e.survey?.technician && <p className="muted small">Surveyor: {e.survey.technician}</p>}
          <div className="actions actions--left">
            <button type="button" className="link--btn row-del" onClick={async () => {
              if (!window.confirm('Cancel this enquiry? We won’t contact you about it again.')) return;
              try {
                const r = await api.cancelEnquiry(e.id);
                if (!r?.ok) throw new Error(r?.error || 'Please try again.');
                toast('Enquiry cancelled.');
                reload();
              } catch (err) { toast(err.message, 'error'); }
            }}>Cancel this enquiry</button>
          </div>
        </article>
      )))}
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
      {t.can_cancel && (
        <div className="actions actions--left">
          <button type="button" className="link--btn row-del" disabled={busy}
                  onClick={() => window.confirm('Cancel this request?') && act(() => api.cancelTicket(t.id), 'Request cancelled.')}>Cancel this request</button>
        </div>
      )}
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
  const [pErr, setPErr] = useState('');
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
      <div className="stack">
        <SecuritySettings />
      </div>
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
        {data && tab === 'overview' && <Overview data={data} reload={load} />}
        {data && tab === 'warranties' && <Warranties data={data} onReport={report} />}
        {data && tab === 'service' && <Service data={data} reload={load} preselect={preselect} />}
        {data && tab === 'profile' && <Profile data={data} reload={load} />}
      </section>
    </>
  );
}
