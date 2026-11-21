import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, fmtDate, inr, num, post } from '../api.js';
import { useAuth } from '../auth.jsx';
import Tabs from '../components/ui/Tabs.jsx';
import { ErrorBox, Loading, PageHead, Pill, Section, Table, useAction, useLoad } from './ui.jsx';

const PERIODS = [
  { value: 'today', label: 'Today' }, { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' }, { value: 'year', label: 'Year' }
];
const MODEL_PATH = { lead: 'enquiries', survey: 'surveys', order: 'orders', delivery: 'dispatch', job: 'jobs', ticket: 'service', subsidy: 'subsidy' };

function Bars({ months }) {
  const max = Math.max(...months.map((m) => m.sales), 1);
  return (
    <div className="bars" role="img" aria-label="Sales in the last six months">
      {months.map((m) => (
        <div key={m.label} className="bars__col" title={`${m.label}: ${inr(m.sales)} · ${m.installs} installs`}>
          <span className="bars__val">{m.sales ? inr(m.sales / 100000).replace('₹', '₹') + 'L' : ''}</span>
          <div className="bars__bar" style={{ height: `${Math.max((m.sales / max) * 100, 2)}%` }} />
          <span className="bars__lbl">{m.label}</span>
        </div>
      ))}
    </div>
  );
}

function Director() {
  const [period, setPeriod] = useState('month');
  const [email, setEmail] = useState('');
  const { busy, run } = useAction();
  const { data, error, loading, reload } = useLoad(() => api.dashboard(period), [period]);
  const k = data?.kpi || {};
  const KPIS = [
    { label: 'New enquiries', value: num(k.leads_new), to: '/app/enquiries' },
    { label: 'Orders won', value: num(k.orders_won), sub: `${num(k.kw_sold)} kW · ${inr(k.orders_value)}`, to: '/app/orders?state=sale' },
    { label: 'Job profit', value: inr(k.profit), sub: k.loss_jobs ? `${k.loss_jobs} loss-making` : 'No loss-making jobs', tone: (k.profit || 0) < 0 ? 'bad' : '' },
    { label: 'Collected', value: inr(k.collected), sub: `Invoiced ${inr(k.invoiced)}`, to: '/app/reports' },
    { label: 'Installations done', value: num(k.installs_done), sub: `${num(k.installs_pending)} to do`, to: '/app/jobs' },
    { label: 'Open repairs', value: num(k.tickets_open), sub: `${num(k.tickets_overdue)} open over 3 days`, tone: k.tickets_overdue ? 'bad' : '', to: '/app/service?stage=open' },
    { label: 'Subsidies pending', value: num(k.subsidy_pending), sub: `${inr(k.subsidy_amount)} expected`, to: '/app/subsidy' },
    { label: 'Receivables', value: inr(k.receivable), sub: `Stock ${inr(k.stock_value)}`, to: '/app/reports' }
  ];
  const share = async (e) => {
    e.preventDefault();
    if (await run('share', () => post('/api/staff/reports/share', { email, period }), `Report sent to ${email}.`)) setEmail('');
  };
  return (
    <>
      <PageHead eyebrow="Director dashboard" title="How the business is doing" sub={data?.period_label}>
        <Tabs label="Period" value={period} onChange={setPeriod} items={PERIODS} />
        <a className="btn btn--secondary btn--sm" href={`/print/report?period=${period}`} target="_blank" rel="noreferrer">Print report</a>
      </PageHead>
      {error && <ErrorBox error={error} onRetry={reload} />}
      <div className="kpis" style={{ opacity: loading ? 0.5 : 1 }}>
        {KPIS.map((x) => {
          const inner = (<><div className="kpi__label">{x.label}</div><div className={`kpi__value ${x.tone || ''}`}>{data ? x.value : '—'}</div>{x.sub && data && <div className="kpi__sub">{x.sub}</div>}</>);
          return x.to ? <Link key={x.label} to={x.to} className="kpi kpi--link">{inner}</Link> : <div key={x.label} className="kpi">{inner}</div>;
        })}
      </div>
      <div className="side-grid">
        <div className="stack">
          {data?.months && <Section title="Sales, last six months"><Bars months={data.months} /></Section>}
          <Table
            rows={data?.jobs || []}
            rowLink={(j) => `/app/orders/${j.id}`}
            empty={loading ? 'Loading…' : 'No jobs in this period.'}
            columns={[
              { key: 'name', label: 'Order' }, { key: 'customer', label: 'Customer' },
              { key: 'kw', label: 'System', render: (j) => `${j.kw} kW ${j.type}` },
              { key: 'revenue', label: 'Revenue', num: true, render: (j) => inr(j.revenue) },
              { key: 'material', label: 'Material', num: true, render: (j) => inr(j.material) },
              { key: 'labour', label: 'Labour', num: true, render: (j) => inr(j.labour) },
              { key: 'profit', label: 'Profit', num: true, render: (j) => <strong className={j.profit < 0 ? 'bad' : 'good'}>{inr(j.profit)}</strong> },
              { key: 'margin', label: 'Margin', num: true, render: (j) => `${(j.margin || 0).toFixed(1)}%` },
              { key: 'stage', label: 'Stage', render: (j) => <Pill state={/Completed/.test(j.stage) ? 'done' : 'in_progress'}>{j.stage}</Pill> }
            ]}
          />
        </div>
        <div className="stack">
          <Section title="Unfinished for customers">
            <ul className="list">
              {(data?.unfinished || []).map((u) => (
                <li key={u.id}><Link to={`/app/orders/${u.id}`}><strong>{u.name}</strong> · {u.customer}</Link><div className="muted">Pending: {u.pending}</div></li>
              ))}
              {data && !data.unfinished.length && <li className="muted">Nothing pending.</li>}
            </ul>
          </Section>
          <Section title="Open repairs">
            <ul className="list">
              {(data?.tickets || []).map((t) => (
                <li key={t.id}>
                  <Link to={`/app/service/${t.id}`}><strong>{t.name}</strong> · {t.customer}</Link>{' '}
                  <Pill state={t.warranty ? 'done' : 'waiting'}>{t.warranty ? 'Warranty' : 'Billable'}</Pill>
                  <div className="muted">{t.product || 'Equipment not set'} · {t.stage} · {t.days}d</div>
                </li>
              ))}
              {data && !data.tickets.length && <li className="muted">No open repairs.</li>}
            </ul>
          </Section>
          <Section title="Email this report">
            <form className="ws-note-form" onSubmit={share}>
              <input className="input" type="email" placeholder="investor@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
              <button className="btn btn--secondary btn--sm" disabled={busy || !email}>Send</button>
            </form>
          </Section>
        </div>
      </div>
    </>
  );
}

function Team() {
  const { me } = useAuth();
  const { data, error, reload } = useLoad(() => api.summary(), []);
  return (
    <>
      <PageHead eyebrow="Today" title={`Good to see you, ${me.name.split(' ')[0]}.`} sub="Here’s what needs your attention." />
      {error && <ErrorBox error={error} onRetry={reload} />}
      {!data && !error && <Loading />}
      {data && (
        <div className="side-grid">
          <div className="todo">
            {data.items.map((i) => (
              <Link key={i.label} to={i.path} className={`todo__item ${i.count ? `todo__item--${i.tone || 'info'}` : 'is-zero'}`}>
                <span className="todo__n">{i.count}</span>
                <span className="todo__label">{i.label}</span>
                <span className="todo__go" aria-hidden="true">›</span>
              </Link>
            ))}
          </div>
          <Section title="Recent activity">
            <ol className="ws-timeline">
              {data.activity.map((n, idx) => (
                <li key={idx}>
                  <Link to={`/app/${MODEL_PATH[n.model]}/${n.res_id}`}>{n.body}</Link>
                  <span className="muted small">{n.author || 'System'} · {fmtDate(n.created_at, true)}</span>
                </li>
              ))}
              {!data.activity.length && <li className="muted small">Nothing yet.</li>}
            </ol>
          </Section>
        </div>
      )}
    </>
  );
}

export default function Overview() {
  const { me } = useAuth();
  return me.role === 'director' ? <Director /> : <Team />;
}
