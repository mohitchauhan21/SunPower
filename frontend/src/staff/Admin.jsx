import { useState } from 'react';
import { fmtDate, get, inr, patch, post, put } from '../api.js';
import { ROLE_LABELS } from '../auth.jsx';
import Tabs from '../components/ui/Tabs.jsx';
import { Chips, ErrorBox, F, KV, Loading, PageHead, Pill, Section, Table, useAction, useLoad } from './ui.jsx';

const PERIODS = [{ value: 'week', label: 'Week' }, { value: 'month', label: 'Month' }, { value: 'year', label: 'Year' }];

export function Reports() {
  const [tab, setTab] = useState('pay');
  const [period, setPeriod] = useState('month');
  const [status, setStatus] = useState('unpaid');
  const pay = useLoad(() => get('/api/staff/reports/technicians', { period }), [period]);
  const inv = useLoad(() => get('/api/staff/reports/invoices', { status }), [status]);
  const totals = (pay.data?.rows || []).reduce((a, r) => ({ hours: a.hours + r.hours, pay: a.pay + r.pay, jobs: a.jobs + r.jobs }), { hours: 0, pay: 0, jobs: 0 });
  const due = (inv.data?.rows || []).reduce((a, r) => a + (r.amount_total - r.amount_paid), 0);
  return (
    <>
      <PageHead eyebrow="Director" title="Reports">
        <Chips value={tab} onChange={setTab} options={[{ value: 'pay', label: 'Technician hours & pay' }, { value: 'inv', label: 'Invoices' }]} />
        <a className="btn btn--secondary btn--sm" href={`/print/report?period=${period}`} target="_blank" rel="noreferrer">Printable report</a>
      </PageHead>
      {tab === 'pay' ? (
        <>
          <div className="ws-toolbar"><Tabs label="Period" value={period} onChange={setPeriod} items={PERIODS} /><span className="muted small">{pay.data?.period_label}</span></div>
          {pay.error ? <ErrorBox error={pay.error} onRetry={pay.reload} /> : !pay.data ? <Loading /> : (
            <>
              <div className="kpis kpis--3">
                <div className="kpi"><div className="kpi__label">Hours on site</div><div className="kpi__value">{totals.hours.toFixed(1)}</div></div>
                <div className="kpi"><div className="kpi__label">Crew pay due</div><div className="kpi__value">{inr(totals.pay)}</div></div>
                <div className="kpi"><div className="kpi__label">Jobs worked</div><div className="kpi__value">{totals.jobs}</div></div>
              </div>
              <Table rows={pay.data.rows} empty="No hours logged in this period."
                columns={[{ key: 'name', label: 'Technician' }, { key: 'hourly_rate', label: 'Rate', num: true, render: (r) => `${inr(r.hourly_rate)}/h` },
                  { key: 'jobs', label: 'Jobs', num: true }, { key: 'hours', label: 'Hours', num: true, render: (r) => r.hours.toFixed(1) },
                  { key: 'pay', label: 'Pay', num: true, render: (r) => <strong>{inr(r.pay)}</strong> }]} />
            </>
          )}
        </>
      ) : (
        <>
          <div className="ws-toolbar">
            <Chips value={status} onChange={setStatus} options={[{ value: 'unpaid', label: 'Unpaid' }, { value: 'paid', label: 'Paid' }, { value: '', label: 'All' }]} />
            {status === 'unpaid' && inv.data && <span className="muted small">Outstanding: <strong>{inr(due)}</strong></span>}
          </div>
          {inv.error ? <ErrorBox error={inv.error} onRetry={inv.reload} /> : !inv.data ? <Loading /> : (
            <Table rows={inv.data.rows} empty="No invoices."
              columns={[{ key: 'ref', label: 'Invoice' }, { key: 'date', label: 'Date', render: (i) => fmtDate(i.date) }, { key: 'customer', label: 'Customer' },
                { key: 'order_ref', label: 'Order', render: (i) => i.order_ref || '—' }, { key: 'kind', label: 'Type' },
                { key: 'amount_total', label: 'Total', num: true, render: (i) => inr(i.amount_total) },
                { key: 'amount_paid', label: 'Paid', num: true, render: (i) => inr(i.amount_paid) },
                { key: 'state', label: 'Status', render: (i) => <Pill state={i.state}>{i.state === 'posted' ? 'Unpaid' : i.state}</Pill> }]} />
          )}
        </>
      )}
    </>
  );
}

export function Settings() {
  const [tab, setTab] = useState('company');
  return (
    <>
      <PageHead eyebrow="Director" title="Settings">
        <Chips value={tab} onChange={setTab} options={[{ value: 'company', label: 'Company & money' }, { value: 'users', label: 'Staff accounts' },
          { value: 'prices', label: 'Prices & warranty' }, { value: 'connect', label: 'Email, payments & sign-in' }]} />
      </PageHead>
      {tab === 'users' ? <Users /> : tab === 'prices' ? <Prices /> : <Company connect={tab === 'connect'} />}
    </>
  );
}

function Company({ connect }) {
  const { busy, run } = useAction();
  const { data: s, error, reload, setData } = useLoad(() => get('/api/staff/settings'), []);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!s) return <Loading />;
  const set = (k) => (v) => setData({ ...s, [k]: v });
  const save = (e) => { e.preventDefault(); run('save', () => put('/api/staff/settings', s), 'Settings saved.').then((r) => r && reload()); };
  const secret = (k, label) => <F label={label} type="password" value={s[k] || ''} onChange={set(k)} placeholder={s[`${k}_set`] ? '•••••••• (saved – type to replace)' : 'Not set'} autoComplete="new-password" />;
  if (!connect) {
    return (
      <form className="ws-card" onSubmit={save}>
        <div className="ws-form">
          <F label="Company name" value={s.company_name} onChange={set('company_name')} />
          <F label="GSTIN" value={s.company_gstin} onChange={set('company_gstin')} />
          <F label="Phone" value={s.company_phone} onChange={set('company_phone')} />
          <F label="Email" value={s.company_email} onChange={set('company_email')} />
          <F label="Address" full value={s.company_address} onChange={set('company_address')} />
          <F label="Advance before dispatch (%)" type="number" min="0" max="100" value={s.advance_pct} onChange={set('advance_pct')} hint="Kits can’t leave the warehouse until this share is paid." />
          <F label="Quote valid for (days)" type="number" min="1" value={s.quote_valid_days} onChange={set('quote_valid_days')} />
          <F label="Service labour rate (₹/h)" type="number" min="0" value={s.labour_rate} onChange={set('labour_rate')} />
          <F label="Website address" value={s.frontend_url} onChange={set('frontend_url')} hint="Used in emailed links." />
          <F label="Text on every quotation" type="textarea" full value={s.quote_note} onChange={set('quote_note')} />
        </div>
        <button className="btn btn--primary" disabled={busy === 'save'}>Save settings</button>
      </form>
    );
  }
  return (
    <form className="stack" onSubmit={save}>
      <Section title="Outgoing email" actions={<Pill state={s.smtp_enabled === '1' ? 'active' : ''}>{s.smtp_enabled === '1' ? 'On' : 'Off'}</Pill>}>
        <p className="muted small">Emails (quotes, account links, certificates) wait in a queue until this is switched on. With Gmail, use an app password.</p>
        <div className="ws-form">
          <F label="Send emails" type="checkbox" value={s.smtp_enabled === '1'} onChange={(v) => set('smtp_enabled')(v ? '1' : '0')} />
          <F label="SMTP server" value={s.smtp_host} onChange={set('smtp_host')} />
          <F label="Port" value={s.smtp_port} onChange={set('smtp_port')} />
          <F label="Username" value={s.smtp_user} onChange={set('smtp_user')} />
          {secret('smtp_password', 'Password / app password')}
          <F label="From address" value={s.smtp_from} onChange={set('smtp_from')} />
        </div>
        <KV items={[['Queued', s.mail.queued || 0], ['Sent', s.mail.sent || 0], ['Failed', s.mail.failed || 0], s.smtp_last_error && ['Last error', s.smtp_last_error]]} />
        <button type="button" className="btn btn--secondary btn--sm" disabled={busy === 'mail'} onClick={() => run('mail', () => post('/api/staff/settings/send-mail'), (r) => `Sent ${r.sent}, failed ${r.failed}.`).then(reload)}>Send queued emails now</button>
      </Section>
      <Section title="Online payments">
        <div className="ws-form">
          <F label="Razorpay key id" value={s.razorpay_key_id} onChange={set('razorpay_key_id')} />
          {secret('razorpay_key_secret', 'Razorpay key secret')}
          <F label="Test payments (for demos)" type="checkbox" value={s.test_payments === '1'} onChange={(v) => set('test_payments')(v ? '1' : '0')} hint="Customers can pay with a test card. Turn off when Razorpay is live." />
        </div>
      </Section>
      <Section title="Sign in with Google">
        <div className="ws-form">
          <F label="Client id" value={s.google_client_id} onChange={set('google_client_id')} />
          {secret('google_client_secret', 'Client secret')}
        </div>
        <p className="form-hint">Authorised redirect URI: <code>{s.google_redirect_uri}</code></p>
      </Section>
      <Section title="AI service"><F label="AI service address" value={s.ai_url} onChange={set('ai_url')} /></Section>
      <div><button className="btn btn--primary" disabled={busy === 'save'}>Save</button></div>
    </form>
  );
}

function Users() {
  const { busy, run } = useAction();
  const { data, error, reload } = useLoad(() => get('/api/staff/users'), []);
  const [f, setF] = useState({ name: '', email: '', phone: '', role: 'sales', hourly_rate: '' });
  const [link, setLink] = useState('');
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading />;
  const roles = data.roles.map((r) => ({ value: r, label: ROLE_LABELS[r] || r }));
  const add = async (e) => {
    e.preventDefault();
    const r = await run('add', () => post('/api/staff/users', { ...f, hourly_rate: Number(f.hourly_rate) || 0 }), 'Account created. An email with a link to set the password is queued.');
    if (r) { setLink(r.link); setF({ name: '', email: '', phone: '', role: 'sales', hourly_rate: '' }); reload(); }
  };
  const change = (id, vals, msg) => run(`u${id}`, () => patch(`/api/staff/users/${id}`, vals), msg).then((r) => r && reload());
  const [edit, setEdit] = useState(null);   // the account being edited: {id, name, email, phone, hourly_rate, role}
  const saveEdit = async (e) => {
    e.preventDefault();
    const r = await run('edit', () => patch(`/api/staff/users/${edit.id}`, { name: edit.name, email: edit.email, phone: edit.phone,
      ...(edit.role === 'technician' ? { hourly_rate: Number(edit.hourly_rate) || 0 } : {}) }), 'Account updated.');
    if (r) { setEdit(null); reload(); }
  };
  return (
    <div className="stack">
      <Section title="Add a staff member" className="ws-card--accent">
        <form className="ws-form" onSubmit={add}>
          <F label="Name" value={f.name} onChange={(v) => setF({ ...f, name: v })} />
          <F label="Email (their login)" type="email" value={f.email} onChange={(v) => setF({ ...f, email: v })} />
          <F label="Phone" value={f.phone} onChange={(v) => setF({ ...f, phone: v })} />
          <F label="Role" type="select" value={f.role} onChange={(v) => setF({ ...f, role: v })} options={roles} />
          {f.role === 'technician' && <F label="Hourly rate (₹)" type="number" value={f.hourly_rate} onChange={(v) => setF({ ...f, hourly_rate: v })} />}
          <div className="field--full"><button className="btn btn--primary btn--sm" disabled={busy === 'add' || !f.name || !f.email}>Create account</button></div>
        </form>
        {link && <p className="form-hint">If email isn’t set up yet, send them this link to choose a password: <code className="breakall">{link}</code></p>}
      </Section>
      {edit && (
        <Section title={`Edit ${edit.name}`} className="ws-card--accent" actions={<button className="link link--btn" onClick={() => setEdit(null)}>Close</button>}>
          <form className="ws-form" onSubmit={saveEdit}>
            <F label="Name" value={edit.name} onChange={(v) => setEdit({ ...edit, name: v })} />
            <F label="Email (their login)" type="email" value={edit.email} onChange={(v) => setEdit({ ...edit, email: v })} />
            <F label="Phone" value={edit.phone || ''} onChange={(v) => setEdit({ ...edit, phone: v })} />
            {edit.role === 'technician' && <F label="Hourly rate (₹)" type="number" value={edit.hourly_rate} onChange={(v) => setEdit({ ...edit, hourly_rate: v })} />}
            <div className="field--full"><button className="btn btn--primary btn--sm" disabled={busy === 'edit'}>Save changes</button></div>
          </form>
        </Section>
      )}
      <Table rows={data.rows} empty="No staff."
        columns={[{ key: 'name', label: 'Name', render: (u) => <><strong>{u.name}</strong><div className="muted small">{u.email}</div>
          <button className="link link--btn small" onClick={() => setEdit({ ...u })}>Edit</button></> },
          { key: 'role', label: 'Role', render: (u) => (
            <select className="select select--sm" value={u.role} disabled={busy === `u${u.id}`} onChange={(e) => change(u.id, { role: e.target.value }, 'Role changed.')} aria-label={`Role of ${u.name}`}>
              {roles.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>) },
          { key: 'hourly_rate', label: 'Rate', num: true, render: (u) => (u.role === 'technician' ? `${inr(u.hourly_rate)}/h` : '—') },
          { key: 'last_login', label: 'Last sign-in', render: (u) => (u.last_login ? fmtDate(u.last_login, true) : u.has_password ? 'Never' : 'Invite pending') },
          { key: 'active', label: 'Access', render: (u) => (
            <button className="link link--btn" disabled={busy === `u${u.id}`} onClick={() => change(u.id, { active: !u.active }, u.active ? 'Access removed.' : 'Access restored.')}>
              {u.active ? 'Active · remove' : 'Removed · restore'}</button>) }]} />
    </div>
  );
}

function Prices() {
  const { busy, run } = useAction();
  const { data, error, reload, setData } = useLoad(() => get('/api/staff/products'), []);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading />;
  const set = (id, k, v) => setData({ rows: data.rows.map((p) => (p.id === id ? { ...p, [k]: v, dirty: true } : p)) });
  const save = (p) => run(`p${p.id}`, () => patch(`/api/staff/products/${p.id}`, { price: p.price, cost: p.cost, warranty_months: p.warranty_months, min_qty: p.min_qty, tax_rate: p.tax_rate }), `${p.name} updated.`).then((r) => r && reload());
  const cell = (p, k, w = 90) => <input className="input input--xs" style={{ width: w }} type="number" min="0" value={p[k] ?? ''} onChange={(e) => set(p.id, k, e.target.value)} aria-label={`${k} of ${p.name}`} />;
  return (
    <Table rows={data.rows} empty="No products."
      columns={[{ key: 'name', label: 'Item', render: (p) => <><strong>{p.name}</strong><div className="muted small">{p.code}{p.is_kit ? ' · package' : ''}</div></> },
        { key: 'price', label: 'Price (₹)', render: (p) => cell(p, 'price', 110) }, { key: 'cost', label: 'Cost (₹)', render: (p) => cell(p, 'cost', 110) },
        { key: 'tax_rate', label: 'GST %', render: (p) => cell(p, 'tax_rate', 64) }, { key: 'warranty_months', label: 'Warranty (months)', render: (p) => cell(p, 'warranty_months', 74) },
        { key: 'min_qty', label: 'Min stock', render: (p) => (p.is_kit || p.is_service ? '—' : cell(p, 'min_qty', 74)) },
        { key: 'act', label: '', render: (p) => p.dirty && <button className="btn btn--primary btn--sm" disabled={busy === `p${p.id}`} onClick={() => save(p)}>Save</button> }]} />
  );
}
