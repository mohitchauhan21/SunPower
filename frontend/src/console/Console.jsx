import { useCallback, useEffect, useState } from 'react';
import { api, inr, num } from '../api.js';
import Tabs from '../components/ui/Tabs.jsx';
import { useToast } from '../components/ui/Toast.jsx';

const PERIODS = [
  { value: 'today', label: 'Today' },
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
  { value: 'year', label: 'Year' }
];
const ENGINE = 'http://localhost:8069';

const stageTone = (s = '') => (/completed|closed/i.test(s) ? 'pill--ok' : /awaiting|dispatched|confirmed/i.test(s) ? 'pill--warn' : '');

function Login({ onDone }) {
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const res = await api.login(login, password);
      if (!res?.uid) throw new Error('Incorrect login or password.');
      onDone(res);
    } catch (err) {
      setError(/access denied|wrong login/i.test(err.message) ? 'Incorrect login or password.' : err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="wrap login">
      <h1 className="headline">Staff console</h1>
      <p className="lead">Sign in with your SunPower account.</p>
      <form className="form" onSubmit={submit}>
        {error && <div className="form-error" role="alert">{error}</div>}
        <div className="field"><label className="label" htmlFor="c-login">Email or login</label><input id="c-login" className="input" required autoComplete="username" value={login} onChange={(e) => setLogin(e.target.value)} /></div>
        <div className="field"><label className="label" htmlFor="c-pass">Password</label><input id="c-pass" className="input" type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
        <button className="btn btn--primary btn--block" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </section>
  );
}

export default function Console() {
  const toast = useToast();
  const [session, setSession] = useState(undefined); // undefined = checking
  const [period, setPeriod] = useState('month');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');

  useEffect(() => {
    api.session().then((s) => setSession(s?.uid ? s : null)).catch(() => setSession(null));
  }, []);

  const load = useCallback(async (p) => {
    setLoading(true);
    setError('');
    try {
      setData(await api.dashboard(p));
    } catch (err) {
      setError(/access|allowed/i.test(err.message)
        ? 'Your account doesn’t have access to the director dashboard.'
        : 'Couldn’t load the dashboard. Is the SunPower engine running?');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (session) load(period); }, [session, period, load]);

  const logout = async () => {
    await api.logout().catch(() => {});
    setSession(null);
    setData(null);
    toast('Signed out.');
  };

  if (session === undefined) return <p className="empty" style={{ padding: '160px 0' }}>Loading…</p>;
  if (!session) return <Login onDone={setSession} />;

  const k = data?.kpi || {};
  const q = query.trim().toLowerCase();
  const jobs = (data?.jobs || []).filter((j) => !q || `${j.name} ${j.customer} ${j.stage}`.toLowerCase().includes(q));

  const KPIS = [
    { label: 'New enquiries', value: num(k.leads_new) },
    { label: 'Orders won', value: num(k.orders_won), sub: `${num(k.kw_sold)} kW · ${inr(k.orders_value)}` },
    { label: 'Job profit', value: inr(k.profit), sub: k.loss_jobs ? `${k.loss_jobs} loss-making` : 'No loss-making jobs', tone: (k.profit || 0) < 0 ? 'bad' : '' },
    { label: 'Collected', value: inr(k.collected), sub: `Invoiced ${inr(k.invoiced)}` },
    { label: 'Installations done', value: num(k.installs_done), sub: `${num(k.installs_pending)} pending` },
    { label: 'Open repairs', value: num(k.tickets_open), sub: `${num(k.tickets_overdue)} open over 3 days`, tone: k.tickets_overdue ? 'bad' : '' },
    { label: 'Subsidies pending', value: num(k.subsidy_pending), sub: `${inr(k.subsidy_amount)} expected` },
    { label: 'Receivables', value: inr(k.receivable), sub: `Stock ${inr(k.stock_value)}` }
  ];

  return (
    <div className="wrap" style={{ paddingBottom: 'clamp(72px, 10vw, 120px)' }}>
      <div className="console-top">
        <div>
          <span className="eyebrow">Director dashboard</span>
          <h1 className="headline" style={{ fontSize: 'clamp(32px, 4vw, 44px)' }}>Good to see you, {session.name?.split(' ')[0] || 'there'}.</h1>
          <p className="muted" style={{ marginTop: 6 }}>{data?.period_label || ' '}</p>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <Tabs label="Period" value={period} onChange={setPeriod} items={PERIODS} />
          <a className="btn btn--secondary btn--sm" href={`${ENGINE}/odoo/action-sunpower_solar.action_solar_dashboard`}>Open in Odoo</a>
          <button className="btn btn--secondary btn--sm" onClick={logout}>Sign out</button>
        </div>
      </div>

      {error && <div className="form-error" role="alert" style={{ marginBottom: 20 }}>{error}</div>}

      <div className="kpis" style={{ opacity: loading ? 0.5 : 1, transition: 'opacity .2s' }}>
        {KPIS.map((x) => (
          <div className="kpi" key={x.label}>
            <div className="kpi__label">{x.label}</div>
            <div className={`kpi__value ${x.tone || ''}`}>{data ? x.value : '—'}</div>
            {x.sub && data && <div className="kpi__sub">{x.sub}</div>}
          </div>
        ))}
      </div>

      <div className="side-grid">
        <div className="table-card">
          <div className="table-card__head">
            <div>
              <h3>Profit by job</h3>
              <span className="muted small">Worst first · {jobs.length} of {data?.jobs?.length || 0}</span>
            </div>
            <input className="input search" type="search" placeholder="Search" aria-label="Search jobs" value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr><th>Order</th><th>Customer</th><th>System</th><th className="num">Revenue</th><th className="num">Material</th><th className="num">Labour</th><th className="num">Profit</th><th className="num">Margin</th><th>Stage</th></tr>
              </thead>
              <tbody>
                {jobs.length ? jobs.map((j) => (
                  <tr key={j.id}>
                    <td><a href={`${ENGINE}/odoo/sale.order/${j.id}`} style={{ fontWeight: 500 }}>{j.name}</a></td>
                    <td>{j.customer}</td>
                    <td>{j.kw} kW <span className="muted">{j.type}</span></td>
                    <td className="num">{inr(j.revenue)}</td>
                    <td className="num muted">{inr(j.material)}</td>
                    <td className="num muted">{inr(j.labour)}</td>
                    <td className={`num ${j.profit < 0 ? 'bad' : 'good'}`} style={{ fontWeight: 600 }}>{inr(j.profit)}</td>
                    <td className="num">{(j.margin || 0).toFixed(1)}%</td>
                    <td><span className={`pill ${stageTone(j.stage)}`}>{j.stage || '—'}</span></td>
                  </tr>
                )) : (
                  <tr><td colSpan={9} className="empty">{loading ? 'Loading…' : 'No jobs in this period.'}</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div style={{ display: 'grid', gap: 20 }}>
          <div className="table-card">
            <div className="table-card__head"><h3>Unfinished for customers</h3></div>
            <ul className="list">
              {(data?.unfinished || []).map((u) => (
                <li key={u.id}><a href={`${ENGINE}/odoo/sale.order/${u.id}`}><strong style={{ fontWeight: 500 }}>{u.name}</strong> · {u.customer}</a><div className="muted">Pending: {u.pending}</div></li>
              ))}
              {data && !data.unfinished?.length && <li className="empty">Nothing pending.</li>}
            </ul>
          </div>
          <div className="table-card">
            <div className="table-card__head"><h3>Open repairs</h3></div>
            <ul className="list">
              {(data?.tickets || []).map((t) => (
                <li key={t.id}>
                  <a href={`${ENGINE}/odoo/solar.service.ticket/${t.id}`}><strong style={{ fontWeight: 500 }}>{t.name}</strong> · {t.customer}</a>{' '}
                  <span className={`pill ${t.warranty ? 'pill--ok' : 'pill--warn'}`}>{t.warranty ? 'Warranty' : 'Billable'}</span>
                  <div className="muted">{t.product || 'Equipment not set'} · {t.stage} · {t.days}d</div>
                </li>
              ))}
              {data && !data.tickets?.length && <li className="empty">No open repairs.</li>}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
