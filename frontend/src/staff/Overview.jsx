import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, fmtDate, fmtLocal, inr, num, post } from '../api.js';
import { useAuth } from '../auth.jsx';
import Tabs from '../components/ui/Tabs.jsx';
import SecuritySettings from '../components/SecuritySettings.jsx';
import { ErrorBox, KV, Loading, PageHead, Pill, Section, Table, useAction, useLoad } from './ui.jsx';

const greeting = () => {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
};
const TAG_TONE = { Call: 'warn', Approve: 'warn', 'Send quote': 'warn', 'Follow up': '', Advance: 'bad', Invoice: '', Dispatch: 'ok',
  'Advance due': '', Reorder: 'bad', 'On site': 'warn', Today: 'ok', Upcoming: '', Visit: '', Urgent: 'bad', Confirm: 'warn' };

/* ================================================================== Today */
export default function Today() {
  const { me } = useAuth();
  const { data, error, reload } = useLoad(() => api.today(), []);
  const day = new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' });
  const todo = data ? data.groups.reduce((n, g) => n + g.count, 0) : 0;
  return (
    <>
      <PageHead eyebrow={day} title={`${greeting()}, ${me.name.split(' ')[0]}.`}
                sub={!data ? 'Getting your day ready…' : data.all_clear ? 'All clear: nothing needs you right now.' : `${todo} thing${todo === 1 ? '' : 's'} need${todo === 1 ? 's' : ''} you. Start at the top.`}>
        {me.role === 'director' && <Link to="/app/insights" className="btn btn--secondary btn--sm">Trends & history →</Link>}
      </PageHead>
      {error && <ErrorBox error={error} onRetry={reload} />}
      {!data && !error && <Loading />}
      {data && (
        <>
          <div className={`today-stats today-stats--${data.stats.length}`}>
            {data.stats.map((s, i) => (
              <div key={s.label} className="today-stat" style={{ animationDelay: `${i * 60}ms` }}>
                <div className="today-stat__value">{s.value}</div>
                <div className="today-stat__label">{s.label}</div>
              </div>
            ))}
          </div>
          <div className="today-groups">
            {data.groups.map((g, i) => (
              <section key={g.key} className={`today-card${g.count ? '' : ' is-clear'}`} style={{ animationDelay: `${120 + i * 70}ms` }}>
                <header className="today-card__head">
                  <div>
                    <h2>{g.title}</h2>
                    <p className="muted small">{g.hint}</p>
                  </div>
                  <span className={`today-count${g.count ? '' : ' is-zero'}`}>{g.count}</span>
                </header>
                {g.count ? (
                  <ul className="today-list">
                    {g.items.map((it, k) => (
                      <li key={k}>
                        <Link to={it.path} className="today-item">
                          <span className="today-item__main">
                            <strong>{it.title}</strong>
                            <span className="muted small">{it.sub}{it.when && it.path.includes('/jobs/') ? ` · ${fmtLocal(it.when)}` : it.when && it.path.includes('/surveys/') ? ` · ${fmtLocal(it.when)}` : ''}</span>
                          </span>
                          {it.tag && <span className={`pill ${it.tone ? `pill--${it.tone}` : TAG_TONE[it.tag] ? `pill--${TAG_TONE[it.tag]}` : ''}`}>{it.tag}</span>}
                          <span className="today-item__go" aria-hidden="true">›</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : <p className="today-clear">✓ Nothing waiting here.</p>}
                {g.count > g.items.length && <Link to={g.path} className="link today-more">See all {g.count}</Link>}
              </section>
            ))}
          </div>
        </>
      )}
    </>
  );
}

/* ============================================================== Insights */
const PERIODS = [{ value: 'week', label: 'This week' }, { value: 'month', label: 'This month' }, { value: 'year', label: 'This year' }];

function Bars({ months }) {
  const max = Math.max(...months.map((m) => m.sales), 1);
  return (
    <div className="bars" role="img" aria-label="Sales in the last six months">
      {months.map((m, i) => (
        <div key={m.label} className="bars__col" title={`${m.label}: ${inr(m.sales)} · ${m.installs} installs`}>
          <span className="bars__val">{m.sales ? `₹${(m.sales / 100000).toFixed(1)}L` : ''}</span>
          <div className="bars__bar" style={{ height: `${Math.max((m.sales / max) * 100, 2)}%`, animationDelay: `${i * 60}ms` }} />
          <span className="bars__lbl">{m.label}</span>
        </div>
      ))}
    </div>
  );
}

/** Director: how the business did over a period. Kept apart from Today on purpose. */
export function Insights() {
  const [period, setPeriod] = useState('month');
  const [email, setEmail] = useState('');
  const [all, setAll] = useState(false);
  const { busy, run } = useAction();
  const { data, error, loading, reload } = useLoad(() => api.dashboard(period), [period]);
  const k = data?.kpi || {};
  const KPIS = [
    { label: 'Sales', value: inr(k.orders_value), sub: `${num(k.orders_won)} orders · ${num(k.kw_sold)} kW` },
    { label: 'Profit', value: inr(k.profit), sub: k.loss_jobs ? `${k.loss_jobs} job${k.loss_jobs > 1 ? 's' : ''} lost money` : 'Every job made money', tone: (k.profit || 0) < 0 ? 'bad' : 'good' },
    { label: 'Cash collected', value: inr(k.collected), sub: `${inr(k.receivable)} still owed to you` },
    { label: 'Installations', value: num(k.installs_done), sub: `${num(k.installs_pending)} still to do` }
  ];
  const jobs = data?.jobs || [];
  const share = async (e) => {
    e.preventDefault();
    if (await run('share', () => post('/api/staff/reports/share', { email, period }), `Report sent to ${email}.`)) setEmail('');
  };
  return (
    <>
      <PageHead eyebrow="Insights" title="How the business is doing" sub={data?.period_label}>
        <Tabs label="Period" value={period} onChange={setPeriod} items={PERIODS} />
        <a className="btn btn--secondary btn--sm" href={`/print/report?period=${period}`} target="_blank" rel="noreferrer">Print</a>
      </PageHead>
      {error && <ErrorBox error={error} onRetry={reload} />}
      <div className="today-stats today-stats--4" style={{ opacity: loading ? 0.5 : 1 }}>
        {KPIS.map((x, i) => (
          <div key={x.label} className="today-stat" style={{ animationDelay: `${i * 60}ms` }}>
            <div className={`today-stat__value ${x.tone || ''}`}>{data ? x.value : '—'}</div>
            <div className="today-stat__label">{x.label}</div>
            {data && <div className="muted small">{x.sub}</div>}
          </div>
        ))}
      </div>
      <div className="side-grid">
        <div className="stack">
          {data?.months && <Section title="Sales, last six months"><Bars months={data.months} /></Section>}
          <Section title={all ? 'Profit by job' : 'Jobs that need a look'} actions={jobs.length > 5 && <button className="link link--btn" onClick={() => setAll(!all)}>{all ? 'Show fewer' : `Show all ${jobs.length}`}</button>}>
            <p className="muted small" style={{ marginTop: -6 }}>{all ? 'Lowest profit first.' : 'The five least profitable jobs in this period.'}</p>
            <Table rows={all ? jobs : jobs.slice(0, 5)} rowLink={(j) => `/app/orders/${j.id}`} empty={loading ? 'Loading…' : 'No jobs in this period.'}
              columns={[
                { key: 'name', label: 'Order' }, { key: 'customer', label: 'Customer' },
                { key: 'revenue', label: 'Revenue', num: true, render: (j) => inr(j.revenue) },
                { key: 'profit', label: 'Profit', num: true, render: (j) => <strong className={j.profit < 0 ? 'bad' : 'good'}>{inr(j.profit)}</strong> },
                { key: 'margin', label: 'Margin', num: true, render: (j) => `${(j.margin || 0).toFixed(1)}%` }
              ]} />
          </Section>
        </div>
        <div className="stack">
          <Section title="At a glance">
            <KV items={[['Open repairs', num(k.tickets_open)], ['Subsidy expected', inr(k.subsidy_amount)], ['Stock value', inr(k.stock_value)], ['Enquiries', num(k.leads_new)]]} />
          </Section>
          <Section title="Email this report">
            <form className="ws-note-form" onSubmit={share}>
              <input className="input" type="email" placeholder="investor@example.com" value={email} onChange={(e) => setEmail(e.target.value)} aria-label="Email address" />
              <button className="btn btn--secondary btn--sm" disabled={busy || !email}>Send</button>
            </form>
          </Section>
        </div>
      </div>
    </>
  );
}

/* ======================================================= staff My account */
export function StaffMe() {
  const { me } = useAuth();
  return (
    <>
      <PageHead eyebrow="My account" title={me.name} sub={`${me.login} · ${me.role}`} />
      <div className="grid grid--2 align-start"><SecuritySettings className="ws-card form" /></div>
      <p className="muted small" style={{ marginTop: 16 }}>Name, email or role changes are made by the Director in Business → Settings → Staff accounts. Signed in since {fmtDate(new Date().toISOString().slice(0, 10))}.</p>
    </>
  );
}
