import { useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { api, del, fmtDate, fmtLocal, get, inr, patch, post, put } from '../api.js';
import { useAuth } from '../auth.jsx';
import {
  Chips, DeleteButton, ErrorBox, F, KV, Loading, Notes, PageHead, Pill, Search, Section, Table, fromLocalInput, toLocalInput,
  useAction, useCan, useLoad
} from './ui.jsx';

const SYSTEM = [{ value: 'on_grid', label: 'On-Grid' }, { value: 'off_grid', label: 'Off-Grid (battery)' }];
const GRID = [{ value: 'unknown', label: 'To check' }, { value: 'yes', label: 'Suitable' }, { value: 'no', label: 'Not suitable' }];
const CHANNEL = [{ value: 'call', label: 'Phone call' }, { value: 'whatsapp', label: 'WhatsApp' }, { value: 'walkin', label: 'Walk-in' }, { value: 'referral', label: 'Referral' }, { value: 'web', label: 'Website' }];
const DIRS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'].map((d) => ({ value: d, label: d }));
const ROOF = [{ value: '', label: '—' }, { value: 'rcc', label: 'RCC / concrete' }, { value: 'metal', label: 'Metal sheet' }, { value: 'tile', label: 'Tiles' }, { value: 'ground', label: 'Ground mount' }];
const SHADE = [{ value: 'none', label: 'No shade' }, { value: 'partial', label: 'Partial' }, { value: 'heavy', label: 'Heavy' }];
const sysLabel = (t) => (t === 'off_grid' ? 'Off-Grid' : 'On-Grid');

function useParam(key, def = '') {
  const [params, setParams] = useSearchParams();
  const value = params.get(key) ?? def;
  const set = (v) => { const p = new URLSearchParams(params); if (v) p.set(key, v); else p.delete(key); setParams(p, { replace: true }); };
  return [value, set];
}

/* =============================================================== enquiries */
export function Enquiries() {
  const [stage, setStage] = useParam('stage');
  const [q, setQ] = useParam('q');
  const [adding, setAdding] = useState(false);
  const { data, error, reload } = useLoad(() => get('/api/staff/leads', { stage, q }), [stage, q]);
  const counts = data?.counts || {};
  return (
    <>
      <PageHead eyebrow="Sales" title="Enquiries" sub="Call new enquiries within two hours, screen the roof, bill and grid, then book a survey.">
        <Search value={q} onChange={setQ} placeholder="Name, phone, city, ref" />
        <button type="button" className="btn btn--primary btn--sm" onClick={() => setAdding(!adding)}>{adding ? 'Close' : 'Log call / WhatsApp'}</button>
      </PageHead>
      {adding && <NewEnquiry onDone={() => { setAdding(false); reload(); }} />}
      <Chips value={stage} onChange={setStage} options={[{ value: '', label: 'All' },
        ...(data?.stages || []).map((s) => ({ value: s.value, label: s.label, count: counts[s.value] || 0 }))]} />
      {error ? <ErrorBox error={error} onRetry={reload} /> : !data ? <Loading /> : (
        <Table rows={data.rows} rowLink={(l) => `/app/enquiries/${l.id}`} empty="No enquiries match."
          columns={[
            { key: 'ref', label: 'Ref' }, { key: 'contact_name', label: 'Customer' }, { key: 'phone', label: 'Phone' },
            { key: 'city', label: 'City' },
            { key: 'requested_kw', label: 'Size', render: (l) => (l.requested_kw ? `${l.requested_kw} kW ${sysLabel(l.system_type)}` : '—') },
            { key: 'channel', label: 'Via' },
            { key: 'salesperson', label: 'Owner' },
            { key: 'created_at', label: 'Received', render: (l) => fmtDate(l.created_at, true) },
            { key: 'stage', label: 'Stage', render: (l) => <Pill state={l.stage}>{l.stage_label}</Pill> }
          ]} />
      )}
    </>
  );
}

function NewEnquiry({ onDone }) {
  const navigate = useNavigate();
  const { busy, run } = useAction();
  const [raw, setRaw] = useState('');
  const [f, setF] = useState({ channel: 'whatsapp', contact_name: '', phone: '', email: '', street: '', city: '',
    requested_kw: '', system_type: 'on_grid', subsidy_requested: true, monthly_bill: '', notes: '' });
  const set = (k) => (v) => setF((s) => ({ ...s, [k]: v }));
  const fill = async () => {
    const r = await run('ai', () => api.parseLead(raw), 'Filled in by AI. Please check before saving.');
    if (!r) return;
    setF((s) => ({ ...s, contact_name: r.name || s.contact_name, phone: r.phone || s.phone, email: r.email || s.email,
      street: r.street || s.street, city: r.city || s.city, requested_kw: r.system_kw || s.requested_kw,
      system_type: r.system_type || s.system_type, subsidy_requested: r.subsidy ?? s.subsidy_requested,
      monthly_bill: r.monthly_bill || s.monthly_bill, notes: [r.summary, raw].filter(Boolean).join('\n\n') }));
  };
  const save = async (e) => {
    e.preventDefault();
    const r = await run('save', () => post('/api/staff/leads', { ...f, requested_kw: f.requested_kw || 0, monthly_bill: f.monthly_bill || 0 }), 'Enquiry created.');
    if (r) { onDone(); navigate(`/app/enquiries/${r.id}`); }
  };
  return (
    <Section title="Log a WhatsApp message or call" className="ws-card--accent">
      <div className="field">
        <label className="label" htmlFor="raw">Paste the message or type call notes <span className="form-hint">(optional)</span></label>
        <textarea id="raw" className="textarea" rows={2} value={raw} onChange={(e) => setRaw(e.target.value)} placeholder="Namaste, mera naam Suresh hai, Jaipur se, 3 kW chahiye…" />
        <div><button type="button" className="btn btn--secondary btn--sm" disabled={!raw.trim() || busy === 'ai'} onClick={fill}>{busy === 'ai' ? 'Reading…' : '✨ Fill with AI'}</button></div>
      </div>
      <form className="ws-form" onSubmit={save}>
        <F label="Channel" type="select" value={f.channel} onChange={set('channel')} options={CHANNEL} />
        <F label="Customer name" value={f.contact_name} onChange={set('contact_name')} required />
        <F label="Phone" type="tel" value={f.phone} onChange={set('phone')} required />
        <F label="Email" type="email" value={f.email} onChange={set('email')} />
        <F label="Address" value={f.street} onChange={set('street')} />
        <F label="City" value={f.city} onChange={set('city')} />
        <F label="Requested kW" type="number" min="0" step="0.5" value={f.requested_kw} onChange={set('requested_kw')} />
        <F label="System" type="select" value={f.system_type} onChange={set('system_type')} options={SYSTEM} />
        <F label="Monthly bill (₹)" type="number" min="0" value={f.monthly_bill} onChange={set('monthly_bill')} />
        <F label="Wants the PM Surya Ghar subsidy" type="checkbox" value={f.subsidy_requested} onChange={set('subsidy_requested')} />
        <F label="Notes" type="textarea" full value={f.notes} onChange={set('notes')} />
        <div className="field--full"><button className="btn btn--primary" disabled={busy === 'save' || !f.contact_name || !f.phone}>Create enquiry</button></div>
      </form>
    </Section>
  );
}

export function Enquiry() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { busy, run } = useAction();
  const { data: l, error, reload, setData } = useLoad(() => get(`/api/staff/leads/${id}`), [id]);
  const techs = useLoad(() => get('/api/staff/people', { role: 'technician' }), []);
  const [survey, setSurvey] = useState({ technician_id: '', survey_date: '' });
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!l) return <Loading />;
  const set = (k) => (v) => setData({ ...l, [k]: v });
  const save = () => run('save', () => patch(`/api/staff/leads/${id}`, {
    contact_name: l.contact_name, phone: l.phone, email: l.email, street: l.street, city: l.city, requested_kw: l.requested_kw || 0,
    system_type: l.system_type, subsidy_requested: l.subsidy_requested ? 1 : 0, monthly_bill: l.monthly_bill || 0,
    monthly_units: l.monthly_units || 0, roof_area_sqft: l.roof_area_sqft || 0, grid_suitable: l.grid_suitable,
    discom: l.discom, consumer_no: l.consumer_no, notes: l.notes, next_action: l.next_action }), 'Saved.').then((r) => r && reload());
  const ro = !l.can_edit;
  return (
    <>
      <PageHead back={{ to: '/app/enquiries', label: 'Enquiries' }} eyebrow={`${l.ref} · via ${l.channel}`} title={l.contact_name}
                sub={`Received ${fmtDate(l.created_at, true)} · Owner ${l.salesperson || '—'}`}>
        <Pill state={l.stage}>{l.stage_label}</Pill>
        {l.phone && <a className="btn btn--secondary btn--sm" href={`tel:${l.phone}`}>Call</a>}
        {l.can_edit && l.has_approved_survey && !l.orders.some((o) => o.state !== 'cancel') && (
          <button className="btn btn--primary btn--sm" disabled={!!busy} onClick={async () => {
            const r = await run('quote', () => post(`/api/staff/leads/${id}/quote`), 'Quotation prepared.');
            if (r) navigate(`/app/orders/${r.id}`);
          }}>Prepare quotation</button>
        )}
        {l.can_edit && !['won', 'lost'].includes(l.stage) && (
          <button className="btn btn--secondary btn--sm" disabled={!!busy} onClick={() => {
            const reason = window.prompt('Why was this enquiry lost?');
            if (reason !== null) run('lost', () => post(`/api/staff/leads/${id}/lost`, { reason }), 'Marked lost.').then(reload);
          }}>Mark lost</button>
        )}
        {l.can_delete && !l.orders.some((o) => o.state === 'sale') && <DeleteButton url={`/api/staff/leads/${id}`} what="this enquiry" after="/app/enquiries" />}
      </PageHead>
      {l.next_action && <div className="ws-banner">Next: {l.next_action}{l.next_action_due ? ` · due ${fmtDate(l.next_action_due)}` : ''}</div>}
      <div className="side-grid">
        <div className="stack">
          <Section title="Customer & requirement" actions={!ro && <button className="btn btn--primary btn--sm" disabled={busy === 'save'} onClick={save}>Save</button>}>
            <div className="ws-form">
              <F label="Name" value={l.contact_name} onChange={set('contact_name')} disabled={ro} />
              <F label="Phone" value={l.phone} onChange={set('phone')} disabled={ro} />
              <F label="Email" value={l.email} onChange={set('email')} disabled={ro} />
              <F label="City" value={l.city} onChange={set('city')} disabled={ro} />
              <F label="Address" full value={l.street} onChange={set('street')} disabled={ro} />
              <F label="Requested kW" type="number" value={l.requested_kw} onChange={set('requested_kw')} disabled={ro} />
              <F label="System" type="select" value={l.system_type} onChange={set('system_type')} options={SYSTEM} disabled={ro} />
              <F label="Wants subsidy" type="checkbox" value={l.subsidy_requested} onChange={set('subsidy_requested')} disabled={ro} />
            </div>
          </Section>
          <Section title="Phone screening">
            <p className="muted small">Shadow-free roof area, bill or units and a suitable grid connection are needed before a survey. Suggested size from the bill: <strong>{l.recommended_kw || '—'} kW</strong>.</p>
            <div className="ws-form">
              <F label="Shadow-free roof (sq ft)" type="number" value={l.roof_area_sqft} onChange={set('roof_area_sqft')} disabled={ro} />
              <F label="Monthly bill (₹)" type="number" value={l.monthly_bill} onChange={set('monthly_bill')} disabled={ro} />
              <F label="Monthly units (kWh)" type="number" value={l.monthly_units} onChange={set('monthly_units')} disabled={ro} />
              <F label="Grid connection" type="select" value={l.grid_suitable} onChange={set('grid_suitable')} options={GRID} disabled={ro} />
              <F label="Electricity board (DISCOM)" value={l.discom} onChange={set('discom')} disabled={ro} />
              <F label="Consumer no." value={l.consumer_no} onChange={set('consumer_no')} disabled={ro} />
              <F label="Notes" type="textarea" full value={l.notes} onChange={set('notes')} disabled={ro} />
            </div>
            {!l.screening_ok && <p className="ws-warn">Screening incomplete. Save roof area, bill and “Suitable” grid to book a survey.</p>}
          </Section>
        </div>
        <div className="stack">
          <Section title="Roof surveys">
            <ul className="list">
              {l.surveys.map((s) => (
                <li key={s.id}><Link to={`/app/surveys/${s.id}`}><strong>{s.ref}</strong> · {s.technician || 'Unassigned'}</Link> <Pill state={s.state}>{s.state_label}</Pill>
                  <div className="muted">{s.survey_date ? fmtLocal(s.survey_date) : 'No date'} · {s.recommended_kw || '—'} kW</div></li>
              ))}
              {!l.surveys.length && <li className="muted">No survey yet.</li>}
            </ul>
            {l.can_edit && (!l.surveys.length || l.surveys.every((s) => s.state === 'rejected')) && (
              <div className="ws-form ws-form--tight">
                <F label="Technician" type="select" value={survey.technician_id} onChange={(v) => setSurvey({ ...survey, technician_id: v })}
                   options={[{ value: '', label: 'Choose…' }, ...(techs.data || []).map((t) => ({ value: t.id, label: t.name }))]} />
                <F label="Visit" type="datetime-local" value={survey.survey_date} onChange={(v) => setSurvey({ ...survey, survey_date: v })} />
                <div className="field--full">
                  <button className="btn btn--primary btn--sm" disabled={!l.screening_ok || !survey.technician_id || busy === 'survey'}
                    onClick={() => run('survey', () => post(`/api/staff/leads/${id}/survey`, { technician_id: Number(survey.technician_id), survey_date: fromLocalInput(survey.survey_date) }), 'Survey booked.').then((r) => r && reload())}>
                    Book roof survey</button>
                </div>
              </div>
            )}
          </Section>
          <Section title="Quotations">
            <ul className="list">
              {l.orders.map((o) => (
                <li key={o.id}><Link to={`/app/orders/${o.id}`}><strong>{o.ref}</strong> · {o.kw} kW · {inr(o.amount_total)}</Link> <Pill state={o.state}>{o.state_label}</Pill></li>
              ))}
              {!l.orders.length && <li className="muted">{l.has_approved_survey ? 'Survey approved: ready to quote.' : 'A quote can be made once the survey is approved.'}</li>}
            </ul>
          </Section>
          <Notes model="lead" id={l.id} notes={l.notes_log} reload={reload} />
        </div>
      </div>
    </>
  );
}

/* ================================================================= surveys */
export function Surveys() {
  const { me } = useAuth();
  const [state, setState] = useParam('state');
  const [q, setQ] = useParam('q');
  const { data, error, reload } = useLoad(() => get('/api/staff/surveys', { state, q }), [state, q]);
  return (
    <>
      <PageHead eyebrow={me.role === 'technician' ? 'My visits' : 'Sales'} title="Roof surveys" sub="Visit, measure, then Sales approves the recommended size.">
        <Search value={q} onChange={setQ} placeholder="Customer, ref, city" />
      </PageHead>
      <Chips value={state} onChange={setState} options={[{ value: '', label: 'All' }, ...(data?.states || [])]} />
      {error ? <ErrorBox error={error} onRetry={reload} /> : !data ? <Loading /> : (
        <Table rows={data.rows} rowLink={(s) => `/app/surveys/${s.id}`} empty="No surveys."
          columns={[
            { key: 'ref', label: 'Ref' }, { key: 'contact_name', label: 'Customer' }, { key: 'city', label: 'City' },
            { key: 'technician', label: 'Surveyor' },
            { key: 'survey_date', label: 'Visit', render: (s) => (s.survey_date ? fmtLocal(s.survey_date) : '—') },
            { key: 'recommended_kw', label: 'kW', num: true },
            { key: 'state', label: 'Status', render: (s) => <Pill state={s.state}>{s.state_label}</Pill> }
          ]} />
      )}
    </>
  );
}

export function Survey() {
  const { id } = useParams();
  const { busy, run } = useAction();
  const { data: s, error, reload, setData } = useLoad(() => get(`/api/staff/surveys/${id}`), [id]);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!s) return <Loading />;
  const open = s.can_edit && !['approved', 'rejected'].includes(s.state);
  const set = (k) => (v) => setData({ ...s, [k]: v });
  const fields = ['roof_type', 'roof_direction', 'roof_tilt', 'usable_area_sqft', 'shading', 'cable_distance_m', 'earthing_possible',
    'latitude', 'longitude', 'recommended_kw', 'notes'];
  const save = () => run('save', () => patch(`/api/staff/surveys/${id}`, {
    ...Object.fromEntries(fields.map((k) => [k, s[k] === '' ? null : s[k]])), earthing_possible: s.earthing_possible ? 1 : 0,
    survey_date: s.survey_date }), 'Saved.');
  const act = (a, msg, body) => run(a, async () => { if (open) await save(); return post(`/api/staff/surveys/${id}/${a}`, body); }, msg).then((r) => r && reload());
  return (
    <>
      <PageHead back={{ to: '/app/surveys', label: 'Surveys' }} eyebrow={`${s.ref} · enquiry ${s.lead_ref}`} title={s.contact_name}
                sub={`${[s.street, s.city].filter(Boolean).join(', ') || 'No address'} · ${s.survey_date ? fmtLocal(s.survey_date) : 'No date'} · ${s.technician || 'No surveyor'}`}>
        <Pill state={s.state}>{s.state_label}</Pill>
        {s.phone && <a className="btn btn--secondary btn--sm" href={`tel:${s.phone}`}>Call</a>}
        {open && s.state === 'scheduled' && <button className="btn btn--primary btn--sm" disabled={!!busy} onClick={() => act('done', 'Marked visited.')}>Mark visited</button>}
        {s.can_approve && s.state === 'done' && <button className="btn btn--primary btn--sm" disabled={!!busy} onClick={() => act('approve', 'Survey approved.')}>Approve</button>}
        {s.can_approve && ['scheduled', 'done'].includes(s.state) && <button className="btn btn--secondary btn--sm" disabled={!!busy} onClick={() => { const reason = window.prompt('Reason for rejecting?'); if (reason !== null) act('reject', 'Survey rejected.', { reason }); }}>Reject</button>}
        {s.can_approve && ['approved', 'rejected'].includes(s.state) && <button className="btn btn--secondary btn--sm" disabled={!!busy} onClick={() => act('reset', 'Survey reopened.')}>Reopen</button>}
        {s.can_delete && <DeleteButton url={`/api/staff/surveys/${id}`} what="this survey" after="/app/surveys" />}
      </PageHead>
      <div className="side-grid">
        <Section title="Roof measurements" actions={open && <button className="btn btn--primary btn--sm" disabled={busy === 'save'} onClick={save}>Save</button>}>
          <div className="ws-form">
            <F label="Roof type" type="select" value={s.roof_type || ''} onChange={set('roof_type')} options={ROOF} disabled={!open} />
            <F label="Roof facing" type="select" value={s.roof_direction || ''} onChange={set('roof_direction')} options={[{ value: '', label: '—' }, ...DIRS]} disabled={!open} />
            <F label="Tilt (°)" type="number" value={s.roof_tilt} onChange={set('roof_tilt')} disabled={!open} />
            <F label="Shadow-free area (sq ft)" type="number" value={s.usable_area_sqft} onChange={set('usable_area_sqft')} disabled={!open} hint={`Fits about ${((s.usable_area_sqft || 0) / 100).toFixed(1)} kW`} />
            <F label="Shading" type="select" value={s.shading || 'none'} onChange={set('shading')} options={SHADE} disabled={!open} />
            <F label="Cable to meter (m)" type="number" value={s.cable_distance_m} onChange={set('cable_distance_m')} disabled={!open} />
            <F label="Latitude" type="number" step="0.000001" value={s.latitude} onChange={set('latitude')} disabled={!open} />
            <F label="Longitude" type="number" step="0.000001" value={s.longitude} onChange={set('longitude')} disabled={!open} />
            <F label="Earthing pit possible" type="checkbox" value={s.earthing_possible} onChange={set('earthing_possible')} disabled={!open} />
            <F label="Recommended kW" type="number" step="0.5" value={s.recommended_kw} onChange={set('recommended_kw')} disabled={!open} />
            <F label="Notes" type="textarea" full value={s.notes} onChange={set('notes')} disabled={!open} />
          </div>
          {s.rejection_reason && <p className="ws-warn">Rejected: {s.rejection_reason}</p>}
        </Section>
        <div className="stack">
          <Section title="Requirement"><KV items={[['Requested', `${s.requested_kw || '—'} kW ${sysLabel(s.system_type)}`], ['Max that fits', `${s.max_kw_fit} kW`], ['Phone', s.phone]]} /></Section>
          <Notes model="survey" id={s.id} notes={s.notes_log} reload={reload} />
        </div>
      </div>
    </>
  );
}

/* ================================================================== orders */
export function Orders() {
  const [state, setState] = useParam('state');
  const [q, setQ] = useParam('q');
  const { data, error, reload } = useLoad(() => get('/api/staff/orders', { state, q }), [state, q]);
  const c = data?.counts || {};
  return (
    <>
      <PageHead eyebrow="Sales" title="Quotes & orders" sub="Send quotes, take the advance, and follow each job to completion.">
        <Search value={q} onChange={setQ} placeholder="Customer or ref" />
      </PageHead>
      <Chips value={state} onChange={setState} options={[{ value: '', label: 'All' }, { value: 'draft', label: 'Draft', count: c.draft || 0 },
        { value: 'sent', label: 'Sent', count: c.sent || 0 }, { value: 'sale', label: 'Confirmed', count: c.sale || 0 }, { value: 'cancel', label: 'Cancelled', count: c.cancel || 0 }]} />
      {error ? <ErrorBox error={error} onRetry={reload} /> : !data ? <Loading /> : (
        <Table rows={data.rows} rowLink={(o) => `/app/orders/${o.id}`} empty="No orders."
          columns={[
            { key: 'ref', label: 'Order' }, { key: 'customer', label: 'Customer' },
            { key: 'kw', label: 'System', render: (o) => `${o.kw} kW ${sysLabel(o.system_type)}` },
            { key: 'amount_total', label: 'Total', num: true, render: (o) => inr(o.amount_total) },
            { key: 'paid', label: 'Paid', num: true, render: (o) => inr(o.paid) },
            { key: 'date_order', label: 'Date', render: (o) => fmtDate(o.date_order) },
            { key: 'salesperson', label: 'Owner' },
            { key: 'state', label: 'Status', render: (o) => <Pill state={o.state}>{o.state_label}</Pill> }
          ]} />
      )}
    </>
  );
}

export function Order() {
  const { id } = useParams();
  const { me } = useAuth();
  const { busy, run } = useAction();
  const { data: o, error, reload, setData } = useLoad(() => get(`/api/staff/orders/${id}`), [id]);
  const [pay, setPay] = useState({ amount: '', method: 'upi', reference: '' });
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!o) return <Loading />;
  const draft = o.state === 'draft' && o.can_edit;
  const act = (a, msg, body) => run(a, () => post(`/api/staff/orders/${id}/${a}`, body), msg).then((r) => r && reload());
  const setLine = (lid, k, v) => setData({ ...o, lines: o.lines.map((l) => (l.id === lid ? { ...l, [k]: v } : l)) });
  const saveLines = () => run('lines', () => put(`/api/staff/orders/${id}/lines`, { lines: o.lines.map((l) => ({ id: l.id, qty: l.qty, discount: l.discount })) }), 'Quotation updated.').then((r) => r && reload());
  const f = o.financials;
  return (
    <>
      <PageHead back={{ to: '/app/orders', label: 'Quotes & orders' }} eyebrow={`${o.state === 'sale' ? 'Order' : 'Quotation'} ${o.ref}`}
                title={o.customer} sub={`${o.kw} kW ${sysLabel(o.system_type)} · ${fmtDate(o.date_order)} · Owner ${o.salesperson || '—'}`}>
        <Pill state={o.state}>{o.state_label}</Pill>
        <a className="btn btn--secondary btn--sm" href={o.print_url} target="_blank" rel="noreferrer">PDF</a>
        {o.can_edit && ['draft', 'sent'].includes(o.state) && <button className="btn btn--secondary btn--sm" disabled={!!busy} onClick={() => act('send', 'Quotation sent to the customer.')}>{o.state === 'sent' ? 'Resend' : 'Send to customer'}</button>}
        {o.can_edit && ['draft', 'sent'].includes(o.state) && <button className="btn btn--primary btn--sm" disabled={!!busy} onClick={() => act('confirm', 'Order confirmed.')}>Confirm order</button>}
        {o.can_edit && o.state !== 'cancel' && <button className="btn btn--secondary btn--sm" disabled={!!busy} onClick={() => window.confirm('Cancel this order?') && act('cancel', 'Order cancelled.')}>Cancel</button>}
        {o.can_delete && o.state !== 'sale' && <DeleteButton url={`/api/staff/orders/${id}`} what="this quotation" after="/app/orders" />}
      </PageHead>
      <div className="side-grid">
        <div className="stack">
          <Section title="Lines" actions={draft && <button className="btn btn--primary btn--sm" disabled={busy === 'lines'} onClick={saveLines}>Save lines</button>}>
            <div className="table-scroll">
              <table className="table">
                <thead><tr><th>Description</th><th className="num">Qty</th><th className="num">Unit price</th><th className="num">Disc. %</th><th className="num">GST</th><th className="num">Amount</th>{draft && <th />}</tr></thead>
                <tbody>
                  {o.lines.map((l) => (
                    <tr key={l.id}>
                      <td>{l.description}</td>
                      <td className="num">{draft ? <input className="input input--xs" type="number" min="1" value={l.qty} onChange={(e) => setLine(l.id, 'qty', e.target.value)} /> : l.qty}</td>
                      <td className="num">{inr(l.price_unit)}</td>
                      <td className="num">{draft ? <input className="input input--xs" type="number" min="0" max={me.role === 'director' ? 100 : 10} value={l.discount} onChange={(e) => setLine(l.id, 'discount', e.target.value)} /> : l.discount || '—'}</td>
                      <td className="num">{l.tax_rate}%</td>
                      <td className="num">{inr(l.subtotal)}</td>
                      {draft && <td><button type="button" className="link--btn row-del" aria-label={`Remove ${l.description}`} disabled={o.lines.length <= 1 || !!busy}
                        onClick={() => window.confirm(`Remove ${l.description}?`) && run('rm', () => del(`/api/staff/orders/${id}/lines/${l.id}`), 'Line removed.').then((r) => r && reload())}>Remove</button></td>}
                    </tr>
                  ))}
                  <tr className="tot"><td colSpan={5} className="num">Subtotal</td><td className="num">{inr(o.amount_untaxed)}</td>{draft && <td />}</tr>
                  <tr className="tot"><td colSpan={5} className="num">GST</td><td className="num">{inr(o.amount_tax)}</td>{draft && <td />}</tr>
                  <tr className="tot tot--grand"><td colSpan={5} className="num">Total</td><td className="num">{inr(o.amount_total)}</td>{draft && <td />}</tr>
                </tbody>
              </table>
            </div>
            {draft && <AddLine onAdd={(product_id, qty) => act('add-line', 'Line added.', { product_id: Number(product_id), qty: Number(qty) || 1 })} />}
            {draft && me.role !== 'director' && <p className="form-hint">Discounts above 10% need the Director.</p>}
          </Section>
          <Section title="Payments & invoices">
            <KV items={[['Paid', <strong className="good" key="p">{inr(o.paid)}</strong>], [`Advance (${o.advance_pct}%)`, inr(o.advance_needed)],
              ['Advance still due', o.advance_due ? <strong className="bad" key="d">{inr(o.advance_due)}</strong> : 'Paid'], ['Balance', inr(o.amount_total - o.paid)]]} />
            {o.payments.length > 0 && (
              <ul className="list">{o.payments.map((p) => <li key={p.id}>{p.ref} · {inr(p.amount)} · {p.method} · {fmtDate(p.date)} <Pill state={p.state}>{p.state}</Pill>
                {o.can_money && p.state === 'done' && <> <button type="button" className="link--btn row-del" disabled={!!busy} onClick={() => {
                  const reason = window.prompt(`Void payment ${p.ref} of ${inr(p.amount)}? Give a reason (e.g. cheque bounced):`);
                  if (reason) run('void', () => post(`/api/staff/payments/${p.id}/void`, { reason }), 'Payment voided.').then((r) => r && reload());
                }}>Void</button></>}</li>)}</ul>
            )}
            {o.invoices.length > 0 && (
              <ul className="list">{o.invoices.map((i) => <li key={i.id}>{i.ref} · {i.kind} · {inr(i.amount_total)} · paid {inr(i.amount_paid)} <Pill state={i.state}>{i.state}</Pill>
                {o.can_money && i.state !== 'cancel' && i.amount_paid < 0.5 && <> <button type="button" className="link--btn row-del" disabled={!!busy} onClick={() => {
                  const reason = window.prompt(`Cancel invoice ${i.ref}? Give a reason:`);
                  if (reason) run('inv', () => post(`/api/staff/invoices/${i.id}/cancel`, { reason }), 'Invoice cancelled.').then((r) => r && reload());
                }}>Cancel</button></>}</li>)}</ul>
            )}
            {o.can_edit && ['sales', 'director'].includes(me.role) && o.state !== 'cancel' && o.paid + 0.5 < o.amount_total && (
              <form className="ws-form ws-form--tight" onSubmit={(e) => { e.preventDefault(); act('payment', 'Payment recorded.', { ...pay, amount: Number(pay.amount) }).then(() => setPay({ amount: '', method: 'upi', reference: '' })); }}>
                <F label="Amount received (₹)" type="number" min="1" value={pay.amount} onChange={(v) => setPay({ ...pay, amount: v })} hint={o.advance_due ? `Advance due: ${inr(o.advance_due)}` : ''} />
                <F label="Method" type="select" value={pay.method} onChange={(v) => setPay({ ...pay, method: v })} options={['upi', 'bank', 'cash', 'cheque'].map((m) => ({ value: m, label: m.toUpperCase() }))} />
                <F label="Reference" value={pay.reference} onChange={(v) => setPay({ ...pay, reference: v })} />
                <div className="field--full actions actions--left">
                  <button className="btn btn--primary btn--sm" disabled={!pay.amount || busy === 'payment'}>Record payment</button>
                  {o.state === 'sale' && <button type="button" className="btn btn--secondary btn--sm" disabled={!!busy} onClick={() => act('final-invoice', 'Final invoice issued.')}>Issue final invoice</button>}
                </div>
              </form>
            )}
          </Section>
          {f && (
            <Section title="Job profitability">
              <KV items={[['Contract value', inr(f.revenue)], ['Material', inr(f.material)], ['Labour', `${inr(f.labour)} · ${f.hours} h`],
                ['Warranty repairs', inr(f.repair)], ['Profit', <strong key="p" className={f.profit < 0 ? 'bad' : 'good'}>{inr(f.profit)}</strong>],
                ['Margin', `${f.margin}%`], ['Stage', f.stage_label], ['Pending', f.pending.join(', ') || 'Nothing']]} />
            </Section>
          )}
        </div>
        <div className="stack">
          <Section title="Customer"><KV items={[['Name', o.customer], ['Phone', o.customer_phone], ['Email', o.customer_email], ['Address', [o.customer_street, o.customer_city].filter(Boolean).join(', ')]]} /></Section>
          <Section title="Generation estimate" actions={o.can_edit && <button className="btn btn--secondary btn--sm" disabled={busy === 'estimate'} onClick={() => act('estimate', 'Estimate updated.')}>{busy === 'estimate' ? 'Asking PVGIS…' : 'Compute with PVGIS'}</button>}>
            <KV items={[['Generation', o.est_kwh_year ? `${Math.round(o.est_kwh_year).toLocaleString('en-IN')} kWh/yr` : null],
              ['Savings', o.est_savings_year ? `${inr(o.est_savings_year)}/yr` : null], ['Payback', o.est_payback_years ? `${o.est_payback_years} yrs` : null],
              ['Subsidy (if eligible)', inr(o.subsidy_expected)], ['Source', o.est_source]]} />
          </Section>
          <Section title="Linked">
            <ul className="list">
              {o.deliveries.map((d) => <li key={`d${d.id}`}><Link to={`/app/dispatch/${d.id}`}>Delivery {d.ref}</Link> <Pill state={d.state}>{d.state}</Pill></li>)}
              {o.jobs.map((j) => <li key={`j${j.id}`}><Link to={`/app/jobs/${j.id}`}>Installation {j.ref}</Link> <Pill state={j.state}>{j.state}</Pill> <span className="muted small">{fmtLocal(j.scheduled_at)}</span></li>)}
              {o.subsidy && <li><Link to={`/app/subsidy/${o.subsidy.id}`}>Subsidy {o.subsidy.ref}</Link> <Pill state={o.subsidy.state}>{o.subsidy.state}</Pill></li>}
              {o.tickets.map((t) => <li key={`t${t.id}`}><Link to={`/app/service/${t.id}`}>Request {t.ref}</Link> <Pill state={t.stage}>{t.stage}</Pill></li>)}
              {o.warranties > 0 && <li><Link to={`/app/warranties?q=${o.ref}`}>{o.warranties} warranties</Link></li>}
              {!o.deliveries.length && !o.jobs.length && <li className="muted">Delivery and installation are created when the order is confirmed.</li>}
            </ul>
          </Section>
          <Notes model="order" id={o.id} notes={o.notes} reload={reload} />
        </div>
      </div>
    </>
  );
}

/** Draft quotation: add any active product as an extra line. */
function AddLine({ onAdd }) {
  const products = useLoad(() => get('/api/staff/products').catch(() => ({ rows: [] })), []);
  const [pid, setPid] = useState('');
  const [qty, setQty] = useState(1);
  const rows = products.data?.rows || [];
  return (
    <div className="ws-form ws-form--tight">
      <F label="Add a line" type="select" value={pid} onChange={setPid}
         options={[{ value: '', label: 'Choose a product…' }, ...rows.map((p) => ({ value: String(p.id), label: `${p.name} (${inr(p.price)})` }))]} />
      <F label="Quantity" type="number" min="1" value={qty} onChange={setQty} />
      <div className="field--full"><button type="button" className="btn btn--secondary btn--sm" disabled={!pid} onClick={() => { onAdd(pid, qty); setPid(''); setQty(1); }}>Add line</button></div>
    </div>
  );
}

/** Create or edit a customer (name, phone, email, address). */
function CustomerForm({ initial = {}, onSave, onCancel, saveLabel = 'Save', lockEmail }) {
  const [f, setF] = useState({ name: '', phone: '', email: '', street: '', city: '', ...initial });
  const set = (k) => (v) => setF((s) => ({ ...s, [k]: v }));
  return (
    <form className="ws-form" onSubmit={(e) => { e.preventDefault(); onSave(f); }}>
      <F label="Name" value={f.name} onChange={set('name')} required />
      <F label="Phone" type="tel" value={f.phone} onChange={set('phone')} required />
      <F label="Email" type="email" value={f.email} onChange={set('email')} disabled={lockEmail} hint={lockEmail ? 'They sign in with this email, so it can’t be changed here.' : ''} />
      <F label="City" value={f.city} onChange={set('city')} />
      <F label="Address" full value={f.street} onChange={set('street')} />
      <div className="field--full actions actions--left">
        <button className="btn btn--primary btn--sm" disabled={!f.name || !f.phone}>{saveLabel}</button>
        {onCancel && <button type="button" className="btn btn--secondary btn--sm" onClick={onCancel}>Cancel</button>}
      </div>
    </form>
  );
}

/* =============================================================== customers */
export function Customers() {
  const [q, setQ] = useParam('q');
  const { data, error, reload } = useLoad(() => get('/api/staff/customers', { q }), [q]);
  const can = useCan('customers');
  const [adding, setAdding] = useState(false);
  const navigate = useNavigate();
  const { run } = useAction();
  const create = async (f) => {
    const r = await run('c', () => post('/api/staff/customers', f), 'Customer added.');
    if (r) navigate(`/app/customers/${r.id}`);
  };
  return (
    <>
      <PageHead eyebrow="Customers" title="Find a customer" sub="Search by name, phone, email or the serial number of their equipment.">
        <Search value={q} onChange={setQ} placeholder="Name, phone, email or serial" />
        {can.write && <button type="button" className="btn btn--primary btn--sm" onClick={() => setAdding(!adding)}>{adding ? 'Close' : 'New customer'}</button>}
      </PageHead>
      {adding && <Section title="New customer" className="ws-card--accent"><CustomerForm onSave={create} saveLabel="Add customer" onCancel={() => setAdding(false)} /></Section>}
      {error ? <ErrorBox error={error} onRetry={reload} /> : !data ? <Loading /> : (
        <Table rows={data.rows} rowLink={(c) => `/app/customers/${c.id}`} empty="No customers match."
          columns={[{ key: 'name', label: 'Name' }, { key: 'phone', label: 'Phone' }, { key: 'email', label: 'Email' }, { key: 'city', label: 'City' },
            { key: 'orders', label: 'Systems', num: true }, { key: 'open_tickets', label: 'Open requests', num: true }]} />
      )}
    </>
  );
}

export function Customer() {
  const { id } = useParams();
  const { data: c, error, reload } = useLoad(() => get(`/api/staff/customers/${id}`), [id]);
  const [editing, setEditing] = useState(false);
  const { run } = useAction();
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!c) return <Loading />;
  const today = new Date().toISOString().slice(0, 10);
  const save = async (f) => {
    const body = { name: f.name, phone: f.phone, street: f.street, city: f.city, ...(c.has_login ? {} : { email: f.email }) };
    if (await run('save', () => patch(`/api/staff/customers/${id}`, body), 'Customer updated.')) { setEditing(false); reload(); }
  };
  return (
    <>
      <PageHead back={{ to: '/app/customers', label: 'Customers' }} eyebrow="Customer" title={c.name}
                sub={[c.phone, c.email, [c.street, c.city].filter(Boolean).join(', ')].filter(Boolean).join(' · ')}>
        <Pill state={c.has_login ? 'active' : ''}>{c.has_login ? 'Has website login' : 'No login yet'}</Pill>
        {c.phone && <a className="btn btn--secondary btn--sm" href={`tel:${c.phone}`}>Call</a>}
        {c.can_edit && <button type="button" className="btn btn--secondary btn--sm" onClick={() => setEditing(!editing)}>{editing ? 'Close' : 'Edit'}</button>}
        {c.can_delete && !c.orders.length && !c.tickets.length && !c.leads.length && !c.warranties.length &&
          <DeleteButton url={`/api/staff/customers/${id}`} what="this customer" after="/app/customers" />}
      </PageHead>
      {editing && (
        <Section title="Edit customer" className="ws-card--accent">
          <CustomerForm initial={{ name: c.name || '', phone: c.phone || '', email: c.email || '', street: c.street || '', city: c.city || '' }}
                        onSave={save} onCancel={() => setEditing(false)} lockEmail={c.has_login} />
        </Section>
      )}
      <div className="side-grid">
        <div className="stack">
          <Section title="Orders"><ul className="list">{c.orders.map((o) => <li key={o.id}><Link to={`/app/orders/${o.id}`}><strong>{o.ref}</strong> · {o.kw} kW · {inr(o.amount_total)}</Link> <Pill state={o.state}>{o.state_label}</Pill></li>)}{!c.orders.length && <li className="muted">No orders.</li>}</ul></Section>
          <Section title="Service requests"><ul className="list">{c.tickets.map((t) => <li key={t.id}><Link to={`/app/service/${t.id}`}><strong>{t.ref}</strong> · {t.description}</Link> <Pill state={t.stage}>{t.stage_label}</Pill></li>)}{!c.tickets.length && <li className="muted">No requests.</li>}</ul></Section>
        </div>
        <Section title="Warranties">
          <ul className="list">{c.warranties.map((w) => <li key={w.id}><strong>{w.product}</strong> <code>{w.serial}</code> <Pill state={w.end_date >= today ? 'active' : 'expired'}>until {fmtDate(w.end_date)}</Pill></li>)}{!c.warranties.length && <li className="muted">No warranties yet.</li>}</ul>
        </Section>
      </div>
    </>
  );
}

/* ================================================================= subsidy */
export function Subsidies() {
  const [state, setState] = useParam('state');
  const { data, error, reload } = useLoad(() => get('/api/staff/subsidies', { state }), [state]);
  return (
    <>
      <PageHead eyebrow="Sales" title="PM Surya Ghar subsidy" sub="Collect documents, apply on the portal and follow each file until the money arrives." />
      <Chips value={state} onChange={setState} options={[{ value: '', label: 'All' }, ...(data?.states || [])]} />
      {error ? <ErrorBox error={error} onRetry={reload} /> : !data ? <Loading /> : (
        <Table rows={data.rows} rowLink={(s) => `/app/subsidy/${s.id}`} empty="No subsidy files."
          columns={[{ key: 'ref', label: 'File' }, { key: 'customer', label: 'Customer' }, { key: 'order_ref', label: 'Order' }, { key: 'kw', label: 'kW', num: true },
            { key: 'application_no', label: 'Portal no.' }, { key: 'amount_expected', label: 'Expected', num: true, render: (s) => inr(s.amount_expected) },
            { key: 'amount_received', label: 'Received', num: true, render: (s) => inr(s.amount_received) },
            { key: 'state', label: 'Status', render: (s) => <Pill state={s.state}>{s.state_label}</Pill> }]} />
      )}
    </>
  );
}

const SUB_NEXT = { draft: ['apply', 'Mark applied on portal'], applied: ['inspection', 'DISCOM inspection done'], inspection: ['approve', 'Approved'], approved: ['disburse', 'Money received'] };
export function Subsidy() {
  const { id } = useParams();
  const { busy, run } = useAction();
  const { data: s, error, reload, setData } = useLoad(() => get(`/api/staff/subsidies/${id}`), [id]);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!s) return <Loading />;
  const set = (k) => (v) => setData({ ...s, [k]: v });
  const save = () => run('save', () => patch(`/api/staff/subsidies/${id}`, {
    application_no: s.application_no, amount_received: s.amount_received || 0,
    ...Object.fromEntries(['doc_id_proof', 'doc_bill', 'doc_bank', 'doc_photo', 'doc_net_meter'].map((k) => [k, s[k] ? 1 : 0])) }), 'Saved.');
  const act = (a, msg) => run(a, async () => { await save(); return post(`/api/staff/subsidies/${id}/${a}`); }, msg).then((r) => r && reload());
  const next = SUB_NEXT[s.state];
  const ro = !s.can_edit;
  return (
    <>
      <PageHead back={{ to: '/app/subsidy', label: 'Subsidy' }} eyebrow={`${s.ref} · order ${s.order_ref}`} title={s.customer} sub={`${s.kw} kW · ${s.scheme}`}>
        <Pill state={s.state}>{s.state_label}</Pill>
        {!ro && next && <button className="btn btn--primary btn--sm" disabled={!!busy} onClick={() => act(next[0], 'Status updated.')}>{next[1]}</button>}
        {!ro && !['disbursed', 'rejected'].includes(s.state) && <button className="btn btn--secondary btn--sm" disabled={!!busy} onClick={() => window.confirm('Mark this file rejected?') && act('reject', 'Marked rejected.')}>Rejected</button>}
        {s.can_delete && <DeleteButton url={`/api/staff/subsidies/${id}`} what="this subsidy file" after="/app/subsidy" />}
      </PageHead>
      <div className="side-grid">
        <Section title="File" actions={!ro && <button className="btn btn--primary btn--sm" disabled={busy === 'save'} onClick={save}>Save</button>}>
          <div className="ws-form">
            <F label="Portal application no." value={s.application_no} onChange={set('application_no')} disabled={ro} />
            <F label="Amount received (₹)" type="number" value={s.amount_received} onChange={set('amount_received')} disabled={ro} />
            <F label="ID proof" type="checkbox" value={s.doc_id_proof} onChange={set('doc_id_proof')} disabled={ro} />
            <F label="Latest electricity bill" type="checkbox" value={s.doc_bill} onChange={set('doc_bill')} disabled={ro} />
            <F label="Cancelled cheque / bank details" type="checkbox" value={s.doc_bank} onChange={set('doc_bank')} disabled={ro} />
            <F label="Installation photo with customer" type="checkbox" value={s.doc_photo} onChange={set('doc_photo')} disabled={ro} />
            <F label="Net-meter commissioning report" type="checkbox" value={s.doc_net_meter} onChange={set('doc_net_meter')} disabled={ro} />
          </div>
          <KV items={[['Expected', inr(s.amount_expected)], ['DISCOM', s.discom], ['Consumer no.', s.consumer_no], ['Applied', fmtDate(s.applied_on)],
            ['Inspection', fmtDate(s.inspection_on)], ['Disbursed', fmtDate(s.disbursed_on)]]} />
        </Section>
        <Notes model="subsidy" id={s.id} notes={s.notes} reload={reload} />
      </div>
    </>
  );
}
