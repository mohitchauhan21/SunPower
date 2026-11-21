import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { api, del, fmtDate, fmtLocal, get, inr, patch, post, upload } from '../api.js';
import { useAuth } from '../auth.jsx';
import {
  Chips, DeleteButton, ErrorBox, F, KV, Loading, Notes, PageHead, Pill, Search, Section, Table, fromLocalInput, toLocalInput,
  useAction, useCan, useLoad
} from './ui.jsx';

function useParam(key, def = '') {
  const [params, setParams] = useSearchParams();
  const value = params.get(key) ?? def;
  const set = (v) => { const p = new URLSearchParams(params); if (v) p.set(key, v); else p.delete(key); setParams(p, { replace: true }); };
  return [value, set];
}

/* ================================================================ dispatch */
export function Deliveries() {
  const [state, setState] = useParam('state');
  const [q, setQ] = useParam('q');
  const { data, error, reload } = useLoad(() => get('/api/staff/deliveries', { state, q }), [state, q]);
  const c = data?.counts || {};
  return (
    <>
      <PageHead eyebrow="Warehouse" title="Dispatch" sub="Kits go out only after the advance is paid. Scanning serials starts each warranty.">
        <Search value={q} onChange={setQ} placeholder="Customer or ref" />
      </PageHead>
      <Chips value={state} onChange={setState} options={[{ value: '', label: 'All' }, { value: 'ready', label: 'Ready', count: c.ready || 0 },
        { value: 'waiting', label: 'Waiting for advance', count: c.waiting || 0 }, { value: 'done', label: 'Dispatched', count: c.done || 0 }]} />
      {error ? <ErrorBox error={error} onRetry={reload} /> : !data ? <Loading /> : (
        <Table rows={data.rows} rowLink={(d) => `/app/dispatch/${d.id}`} empty="Nothing to dispatch."
          columns={[{ key: 'ref', label: 'Delivery' }, { key: 'order_ref', label: 'Order' }, { key: 'customer', label: 'Customer' },
            { key: 'city', label: 'City' }, { key: 'kw', label: 'kW', num: true },
            { key: 'date_done', label: 'Dispatched', render: (d) => fmtDate(d.date_done) || '—' },
            { key: 'state', label: 'Status', render: (d) => <Pill state={d.state}>{d.state_label}</Pill> }]} />
      )}
    </>
  );
}

export function Delivery() {
  const { id } = useParams();
  const { busy, run } = useAction();
  const { data: d, error, reload } = useLoad(() => get(`/api/staff/deliveries/${id}`), [id]);
  const [scan, setScan] = useState({});
  const [override, setOverride] = useState(false);
  useEffect(() => {
    if (!d || d.state === 'done') return;
    // pre-fill with the oldest serials in stock; the user can change them
    const init = {};
    d.lines.forEach((l) => {
      if (l.tracking === 'serial') init[l.id] = (l.available || []).slice(0, l.qty).join('\n');
      if (l.tracking === 'lot') init[l.id] = (l.available || [])[0] || '';
    });
    setScan(init);
  }, [d]);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!d) return <Loading />;
  const open = d.state !== 'done' && d.can_edit;
  const validate = () => {
    const serials = Object.fromEntries(Object.entries(scan).map(([k, v]) => [k, v.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean)]));
    run('go', () => post(`/api/staff/deliveries/${id}/validate`, { serials, override }), (r) => `Dispatched. ${r.warranties} warranties started.`).then((r) => r && reload());
  };
  return (
    <>
      <PageHead back={{ to: '/app/dispatch', label: 'Dispatch' }} eyebrow={`${d.ref} · order ${d.order_ref}`} title={d.customer}
                sub={[d.street, d.city, d.phone].filter(Boolean).join(' · ')}>
        <Pill state={d.state}>{d.state_label}</Pill>
        {open && <button className="btn btn--primary btn--sm" disabled={busy === 'go' || (d.advance_due > 0 && !override)} onClick={validate}>Dispatch kit</button>}
      </PageHead>
      {d.advance_due > 0 && d.state !== 'done' && (
        <div className="ws-banner ws-banner--bad">
          Advance not paid: {inr(d.advance_due)} still due ({inr(d.paid)} of {inr(d.advance_needed)} received). The kit can’t leave yet.
          {d.can_override && <label className="ws-check" style={{ marginTop: 8 }}><input type="checkbox" checked={override} onChange={(e) => setOverride(e.target.checked)} /><span>Director override: dispatch anyway</span></label>}
        </div>
      )}
      <div className="side-grid">
        <Section title="Packing list">
          <div className="table-scroll">
            <table className="table">
              <thead><tr><th>Item</th><th className="num">Qty</th><th className="num">In stock</th><th>Serial / batch</th></tr></thead>
              <tbody>
                {d.lines.map((l) => (
                  <tr key={l.id}>
                    <td><strong>{l.name}</strong><div className="muted small">{l.code}{l.warranty_months ? ` · ${l.warranty_months / 12} yr warranty` : ''}</div></td>
                    <td className="num">{l.qty}</td>
                    <td className={`num ${l.qty_on_hand < l.qty && open ? 'bad' : ''}`}>{l.qty_on_hand}</td>
                    <td>
                      {l.tracking === 'none' ? <span className="muted">—</span>
                        : d.state === 'done' ? <code className="serials">{l.serials.join(', ')}</code>
                        : l.tracking === 'serial'
                          ? <textarea className="textarea textarea--mono" rows={Math.min(Math.max(l.qty, 1), 4)} value={scan[l.id] || ''} disabled={!open}
                                      onChange={(e) => setScan({ ...scan, [l.id]: e.target.value })} aria-label={`Serials for ${l.name}`} placeholder="One serial per line" />
                          : <input className="input input--mono" value={scan[l.id] || ''} disabled={!open} onChange={(e) => setScan({ ...scan, [l.id]: e.target.value })} aria-label={`Batch for ${l.name}`} placeholder="Batch / lot no." />}
                      {l.tracking === 'serial' && open && <div className="form-hint">{(scan[l.id] || '').split(/[\n,]+/).filter((s) => s.trim()).length} of {l.qty} scanned</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
        <div className="stack">
          <Section title="Order"><KV items={[['Order', <Link key="o" to={`/app/orders/${d.order_id}`}>{d.order_ref}</Link>], ['Order total', inr(d.amount_total)], ['Paid so far', inr(d.paid)], ['Dispatched', fmtDate(d.date_done, true)]]} /></Section>
          <Notes model="delivery" id={d.id} notes={d.notes} reload={reload} />
        </div>
      </div>
    </>
  );
}

/* =================================================================== stock */
export function Stock() {
  const { me } = useAuth();
  const [q, setQ] = useParam('q');
  const [tab, setTab] = useParam('tab', 'items');
  const { data, error, reload } = useLoad(() => (tab === 'serials' ? get('/api/staff/serials', { q }) : get('/api/staff/products', { q })), [q, tab]);
  const [receiving, setReceiving] = useState(null);
  const [adding, setAdding] = useState(false);
  const { run } = useAction();
  const can = useCan('stock');
  const canWrite = can.write;
  const retire = (p) => window.confirm(`Retire ${p.name}? It disappears from lists and new quotes; old orders keep it.`) &&
    run('r', () => del(`/api/staff/products/${p.id}`), `${p.name} retired.`).then((r) => r && reload());
  const rows = (data?.rows || []).filter((r) => tab === 'serials' || (!r.is_kit && !r.is_service));
  return (
    <>
      <PageHead eyebrow="Warehouse" title="Stock" sub="Components on hand, receiving new stock and every serial number.">
        <Search value={q} onChange={setQ} placeholder={tab === 'serials' ? 'Serial or customer' : 'Item or code'} />
        {me.role === 'director' && <button type="button" className="btn btn--primary btn--sm" onClick={() => setAdding(!adding)}>{adding ? 'Close' : 'New product'}</button>}
      </PageHead>
      {adding && <NewProduct onDone={() => { setAdding(false); reload(); }} />}
      <Chips value={tab} onChange={setTab} options={[{ value: 'items', label: 'Components' }, { value: 'serials', label: 'Serial numbers' }]} />
      {receiving && <Receive product={receiving} onDone={() => { setReceiving(null); reload(); }} />}
      {error ? <ErrorBox error={error} onRetry={reload} /> : !data ? <Loading /> : tab === 'serials' ? (
        <Table rows={rows} empty="No serials match."
          columns={[{ key: 'name', label: 'Serial' }, { key: 'product', label: 'Item' }, { key: 'state', label: 'Status', render: (s) => <Pill state={s.state}>{s.state === 'in_stock' ? 'In stock' : 'Delivered'}</Pill> },
            { key: 'customer', label: 'Installed at', render: (s) => s.customer || '—' }]} />
      ) : (
        <Table rows={rows} empty="No items."
          columns={[{ key: 'code', label: 'Code' }, { key: 'name', label: 'Item' },
            { key: 'tracking', label: 'Tracking', render: (p) => (p.tracking === 'none' ? '—' : p.tracking) },
            { key: 'qty_on_hand', label: 'On hand', num: true, render: (p) => <span className={p.low ? 'bad' : ''}>{p.qty_on_hand}</span> },
            { key: 'min_qty', label: 'Minimum', num: true },
            { key: 'low', label: '', render: (p) => (p.low ? <Pill state="failed">Reorder</Pill> : null) },
            ...(canWrite ? [{ key: 'act', label: '', render: (p) => (
              <span className="row-acts">
                <button className="link link--btn" onClick={() => setReceiving(p)}>Receive</button>
                {can.del && <button className="link--btn row-del" onClick={() => retire(p)}>Retire</button>}
              </span>) }] : [])]} />
      )}
    </>
  );
}

const CATS = [['panel', 'Solar panels'], ['inverter', 'Inverters'], ['battery', 'Batteries'], ['controller', 'Charge controllers'],
  ['bos', 'Balance of system'], ['service', 'Services']].map(([value, label]) => ({ value, label }));

/** Director: add a new component or service to the catalogue. */
function NewProduct({ onDone }) {
  const { busy, run } = useAction();
  const [f, setF] = useState({ code: '', name: '', category: 'bos', tracking: 'none', cost: '', price: '', min_qty: '' });
  const set = (k) => (v) => setF((x) => ({ ...x, [k]: v }));
  const save = (e) => {
    e.preventDefault();
    run('p', () => post('/api/staff/products', f), `${f.name} added.`).then((r) => r && onDone());
  };
  return (
    <Section title="New product" className="ws-card--accent" actions={<button className="link link--btn" onClick={onDone}>Close</button>}>
      <form className="ws-form" onSubmit={save}>
        <F label="Code" value={f.code} onChange={set('code')} placeholder="e.g. WIFI-1" />
        <F label="Name" value={f.name} onChange={set('name')} />
        <F label="Category" type="select" value={f.category} onChange={set('category')} options={CATS} hint="Sets the default warranty and GST." />
        <F label="Tracking" type="select" value={f.tracking} onChange={set('tracking')}
           options={[{ value: 'none', label: 'Not tracked' }, { value: 'serial', label: 'Serial number per unit' }, { value: 'lot', label: 'Batch / lot' }]} />
        <F label="Cost (₹)" type="number" min="0" value={f.cost} onChange={set('cost')} />
        <F label="Selling price (₹)" type="number" min="0" value={f.price} onChange={set('price')} />
        <F label="Minimum stock" type="number" min="0" value={f.min_qty} onChange={set('min_qty')} />
        <div className="field--full"><button className="btn btn--primary btn--sm" disabled={busy || !f.code || !f.name}>Add product</button></div>
      </form>
    </Section>
  );
}

function Receive({ product, onDone }) {
  const { busy, run } = useAction();
  const [qty, setQty] = useState('');
  const [serials, setSerials] = useState('');
  const [note, setNote] = useState('');
  const submit = (e) => {
    e.preventDefault();
    run('r', () => post(`/api/staff/products/${product.id}/receive`, { qty: Number(qty || 0), serials, note }), (r) => `Received ${r.qty} × ${product.name}.`).then((r) => r && onDone());
  };
  return (
    <Section title={`Receive: ${product.name}`} className="ws-card--accent" actions={<button className="link link--btn" onClick={onDone}>Close</button>}>
      <form className="ws-form" onSubmit={submit}>
        {product.tracking === 'serial'
          ? <F label="Serial numbers (one per line)" type="textarea" full value={serials} onChange={setSerials} rows={4} />
          : <F label="Quantity received" type="number" min="1" value={qty} onChange={setQty} />}
        <F label="Note (supplier, invoice no.)" value={note} onChange={setNote} />
        <div className="field--full"><button className="btn btn--primary btn--sm" disabled={busy}>Add to stock</button></div>
      </form>
    </Section>
  );
}

/* ==================================================================== jobs */
export function Jobs() {
  const { me } = useAuth();
  const [state, setState] = useParam('state', me.role === 'technician' ? 'open' : '');
  const [q, setQ] = useParam('q');
  const { data, error, reload } = useLoad(() => get('/api/staff/jobs', { state: state === 'open' ? '' : state, q }), [state, q]);
  const rows = (data?.rows || []).filter((j) => state !== 'open' || j.state !== 'done');
  const tech = me.role === 'technician';
  return (
    <>
      <PageHead eyebrow={tech ? 'My jobs' : 'Operations'} title={tech ? 'Installation jobs' : 'Installations'}
                sub={tech ? 'Your assigned rooftops. Start the job on site, finish the checklist, photos and signature.' : 'The crew schedule for every confirmed order.'}>
        <Search value={q} onChange={setQ} placeholder="Customer, ref, city" />
      </PageHead>
      <Chips value={state} onChange={setState} options={[{ value: 'open', label: 'To do' }, { value: '', label: 'All' },
        { value: 'planned', label: 'Planned' }, { value: 'in_progress', label: 'On site' }, { value: 'done', label: 'Completed' }]} />
      {error ? <ErrorBox error={error} onRetry={reload} /> : !data ? <Loading /> : tech ? (
        <div className="job-cards">
          {rows.map((j) => (
            <Link key={j.id} to={`/app/jobs/${j.id}`} className={`job-card job-card--${j.state}`}>
              <div className="job-card__top"><strong>{j.customer}</strong><Pill state={j.state}>{j.state_label}</Pill></div>
              <div className="job-card__kw">{j.kw_planned} kW</div>
              <div className="muted">{j.city} · {j.ref}</div>
              <div className="job-card__when">{j.state === 'done' ? `Completed ${fmtDate(j.site_end)}` : fmtLocal(j.scheduled_at)}</div>
            </Link>
          ))}
          {!rows.length && <div className="card card--alt empty-state"><h3>No jobs here.</h3><p className="muted">When the office books you on an installation, it shows up here with the customer, address, size and time.</p></div>}
        </div>
      ) : (
        <Table rows={rows} rowLink={(j) => `/app/jobs/${j.id}`} empty="No jobs."
          columns={[{ key: 'ref', label: 'Job' }, { key: 'customer', label: 'Customer' }, { key: 'city', label: 'City' }, { key: 'kw_planned', label: 'kW', num: true },
            { key: 'scheduled_at', label: 'Scheduled', render: (j) => fmtLocal(j.scheduled_at) }, { key: 'crew', label: 'Crew', render: (j) => j.crew || <span className="bad">Not assigned</span> },
            { key: 'state', label: 'Status', render: (j) => <Pill state={j.state}>{j.state_label}</Pill> }]} />
      )}
    </>
  );
}

function SignaturePad({ value, onChange, disabled }) {
  const ref = useRef(null);
  const drawing = useRef(false);
  useEffect(() => {
    const c = ref.current;
    const ctx = c.getContext('2d');
    c.width = c.offsetWidth * 2;
    c.height = c.offsetHeight * 2;
    ctx.scale(2, 2);
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.strokeStyle = '#1d1d1f';
    if (value) { const img = new Image(); img.onload = () => ctx.drawImage(img, 0, 0, c.offsetWidth, c.offsetHeight); img.src = value; }
  }, []); // eslint-disable-line
  const pos = (e) => { const r = ref.current.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  const down = (e) => { if (disabled) return; drawing.current = true; ref.current.setPointerCapture(e.pointerId); const ctx = ref.current.getContext('2d'); ctx.beginPath(); ctx.moveTo(...pos(e)); };
  const move = (e) => { if (!drawing.current) return; const ctx = ref.current.getContext('2d'); ctx.lineTo(...pos(e)); ctx.stroke(); };
  const up = () => { if (!drawing.current) return; drawing.current = false; onChange(ref.current.toDataURL('image/png')); };
  const clear = () => { const c = ref.current; c.getContext('2d').clearRect(0, 0, c.width, c.height); onChange(''); };
  return (
    <div className="sig">
      <canvas ref={ref} className="sig__pad" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerLeave={up} aria-label="Customer signature" />
      {!disabled && <button type="button" className="link link--btn" onClick={clear}>Clear signature</button>}
    </div>
  );
}

export function Job() {
  const { id } = useParams();
  const { busy, run } = useAction();
  const { data: j, error, reload, setData } = useLoad(() => get(`/api/staff/jobs/${id}`), [id]);
  const techs = useLoad(() => get('/api/staff/people', { role: 'technician' }), []);
  const fileRef = useRef(null);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!j) return <Loading />;
  const open = j.can_edit && j.state !== 'done';
  const set = (k) => (v) => setData({ ...j, [k]: v });
  const fields = () => ({
    ...Object.fromEntries(j.checklist.map((c) => [c.field, c.done ? 1 : 0])), kw_confirmed: j.kw_confirmed || null,
    generation_reading_kw: j.generation_reading_kw || null, signed_by: j.signed_by, notes: j.notes,
    ...(j.signature?.startsWith('data:image/') ? { signature: j.signature } : {}),
    ...(j.can_assign ? { scheduled_at: j.scheduled_at, techs: j.techs.map((t) => t.id) } : {})
  });
  const save = (msg = 'Saved.') => run('save', () => patch(`/api/staff/jobs/${id}`, fields()), msg);
  const act = (a, msg) => run(a, async () => { if (open) await patch(`/api/staff/jobs/${id}`, fields()); return post(`/api/staff/jobs/${id}/${a}`); }, msg).then((r) => r && reload());
  // Each tap saves straight away (crews work on a roof, not at a desk)
  const toggle = (field) => {
    const done = !j.checklist.find((c) => c.field === field).done;
    setData((d) => ({ ...d, checklist: d.checklist.map((c) => (c.field === field ? { ...c, done } : c)) }));
    run('', () => patch(`/api/staff/jobs/${id}`, { [field]: done ? 1 : 0 }));
  };
  // Refresh only photos / activity, keeping anything typed but not saved yet
  const refreshParts = () => get(`/api/staff/jobs/${id}`).then((f) => setData((d) => ({ ...d, photos: f.photos, notes_log: f.notes_log }))).catch(() => {});
  const addPhoto = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    let note = '';
    const check = await api.checkPhoto(file).catch(() => null);
    if (check) note = `AI check: ${check.label} (${Math.round(check.confidence * 100)}%)${check.flag ? ' ⚠' : ''}`;
    const form = new FormData();
    form.append('file', file);
    form.append('note', note);
    run('photo', () => upload(`/api/staff/jobs/${id}/photos`, form), check ? `Photo added. ${note}` : 'Photo added.').then((r) => r && refreshParts());
  };
  const done = j.checklist.filter((c) => c.done).length;
  return (
    <>
      <PageHead back={{ to: '/app/jobs', label: 'Jobs' }} eyebrow={`${j.ref} · order ${j.order_ref}`} title={j.customer}
                sub={`${j.kw_planned} kW ${j.system_type === 'off_grid' ? 'Off-Grid' : 'On-Grid'} · ${fmtLocal(j.scheduled_at)}`}>
        <Pill state={j.state}>{j.state_label}</Pill>
        {j.phone && <a className="btn btn--secondary btn--sm" href={`tel:${j.phone}`}>Call customer</a>}
        {j.street && <a className="btn btn--secondary btn--sm" target="_blank" rel="noreferrer" href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent([j.street, j.city].join(', '))}`}>Directions</a>}
        {j.certificate_url && <a className="btn btn--secondary btn--sm" href={j.certificate_url} target="_blank" rel="noreferrer">Certificate</a>}
        {j.can_delete && j.state === 'planned' && <DeleteButton url={`/api/staff/jobs/${id}`} what="this installation job" after="/app/jobs" />}
      </PageHead>
      {!j.dispatched && j.state !== 'done' && <div className="ws-banner ws-banner--bad">The kit hasn’t been dispatched from the warehouse yet. You can start, but you can’t finish until it’s delivered.</div>}
      <div className="side-grid">
        <div className="stack">
          {open && (
            <div className="job-action">
              {j.state === 'planned'
                ? <button className="btn btn--primary btn--block" disabled={!!busy} onClick={() => act('start', 'Job started. Good luck on the roof!')}>▶ Start job on site</button>
                : <button className="btn btn--accent btn--block" disabled={!!busy} onClick={() => act('finish', 'Job completed. Certificate sent to the customer.')}>✔ Finish & hand over</button>}
              <span className="muted small">Checklist {done}/{j.checklist.length} · {j.photos.length} photo{j.photos.length === 1 ? '' : 's'} · {j.signature ? 'signed' : 'not signed'}</span>
            </div>
          )}
          <Section title="Checklist" actions={open && <button className="btn btn--secondary btn--sm" disabled={busy === 'save'} onClick={() => save()}>Save</button>}>
            <ul className="checklist">
              {j.checklist.map((c) => (
                <li key={c.field}>
                  <label className={`checklist__item${c.done ? ' is-done' : ''}`}>
                    <input type="checkbox" checked={c.done} disabled={!open} onChange={() => toggle(c.field)} />
                    <span className="checklist__box" aria-hidden="true">{c.done ? '✓' : ''}</span>
                    <span>{c.label}</span>
                  </label>
                </li>
              ))}
            </ul>
            <div className="ws-form">
              <F label="Installed size (kW)" type="number" step="0.1" value={j.kw_confirmed} onChange={set('kw_confirmed')} disabled={!open} />
              <F label="Live generation at test (kW)" type="number" step="0.01" value={j.generation_reading_kw} onChange={set('generation_reading_kw')} disabled={!open} />
              <F label="Notes" type="textarea" full value={j.notes} onChange={set('notes')} disabled={!open} />
            </div>
          </Section>
          <Section title="Photos of the finished roof" actions={open && (
            <>
              <input ref={fileRef} type="file" accept="image/*" capture="environment" hidden onChange={addPhoto} />
              <button className="btn btn--secondary btn--sm" disabled={busy === 'photo'} onClick={() => fileRef.current.click()}>{busy === 'photo' ? 'Uploading…' : 'Add photo'}</button>
            </>
          )}>
            <div className="photos">
              {j.photos.map((p) => (
                <figure key={p.id}><img src={`/api/staff/attachments/${p.id}`} alt={p.filename} loading="lazy" /><figcaption className="small muted">{p.note || fmtDate(p.created_at, true)}</figcaption></figure>
              ))}
              {!j.photos.length && <p className="muted small">At least one photo is needed to finish. Photos are checked by AI for dust, damage or snow when the AI service is running.</p>}
            </div>
          </Section>
          <Section title="Customer acceptance" actions={open && <button className="btn btn--secondary btn--sm" disabled={busy === 'save'} onClick={() => save('Signature saved.')}>Save</button>}>
            <F label="Signed by (homeowner’s name)" value={j.signed_by} onChange={set('signed_by')} disabled={!open} />
            <SignaturePad value={j.signature} onChange={set('signature')} disabled={!open} />
            {j.signed_on && <p className="muted small">Signed {fmtDate(j.signed_on, true)}</p>}
          </Section>
        </div>
        <div className="stack">
          <Section title="Site"><KV items={[['Customer', j.customer], ['Phone', j.phone ? <a key="p" href={`tel:${j.phone}`}>{j.phone}</a> : null], ['Address', [j.street, j.city].filter(Boolean).join(', ')],
            ['Started', fmtDate(j.site_start, true)], ['Finished', fmtDate(j.site_end, true)]]} /></Section>
          <Section title="Crew & schedule" actions={j.can_assign && j.state !== 'done' && <button className="btn btn--secondary btn--sm" disabled={busy === 'save'} onClick={() => save('Schedule saved.').then((r) => r && reload())}>Save</button>}>
            {j.can_assign && j.state !== 'done' ? (
              <>
                <F label="Scheduled" type="datetime-local" value={toLocalInput(j.scheduled_at)} onChange={(v) => set('scheduled_at')(fromLocalInput(v))} />
                <div className="crew-pick">
                  {(techs.data || []).map((t) => {
                    const on = j.techs.some((x) => x.id === t.id);
                    return <button key={t.id} type="button" className={`chip${on ? ' is-active' : ''}`} onClick={() => set('techs')(on ? j.techs.filter((x) => x.id !== t.id) : [...j.techs, t])}>{t.name}</button>;
                  })}
                </div>
              </>
            ) : <KV items={[['Scheduled', fmtLocal(j.scheduled_at)], ['Crew', j.techs.map((t) => t.name).join(', ') || 'Not assigned']]} />}
          </Section>
          {j.warranties.length > 0 && (
            <Section title="Installed equipment">
              <ul className="list">{j.warranties.map((w, i) => <li key={i}><strong>{w.product}</strong> <code>{w.serial}</code><div className="muted small">Warranty until {fmtDate(w.end_date)}</div></li>)}</ul>
            </Section>
          )}
          <Notes model="job" id={j.id} notes={j.notes_log} reload={refreshParts} />
        </div>
      </div>
    </>
  );
}

/* ================================================================= service */
export function Tickets() {
  const { me } = useAuth();
  const [stage, setStage] = useParam('stage', 'open');
  const [q, setQ] = useParam('q');
  const [adding, setAdding] = useState(false);
  const { data, error, reload } = useLoad(() => get('/api/staff/tickets', { stage, q }), [stage, q]);
  const canCreate = (me.modules || []).find((m) => m.key === 'tickets')?.level === 'rw';
  return (
    <>
      <PageHead eyebrow={me.role === 'technician' ? 'My repairs' : 'Service desk'} title="Service requests" sub="Find the customer by phone or serial; warranty repairs are free, others are invoiced automatically.">
        <Search value={q} onChange={setQ} placeholder="Customer, ref, problem" />
        {canCreate && <button className="btn btn--primary btn--sm" onClick={() => setAdding(!adding)}>{adding ? 'Close' : 'New request'}</button>}
      </PageHead>
      {adding && <NewTicket onDone={() => { setAdding(false); reload(); }} />}
      <Chips value={stage} onChange={setStage} options={[{ value: 'open', label: 'Open' }, { value: '', label: 'All' },
        ...(data?.stages || []).filter((s) => s.value !== 'cancel')]} />
      {error ? <ErrorBox error={error} onRetry={reload} /> : !data ? <Loading /> : (
        <Table rows={data.rows} rowLink={(t) => `/app/service/${t.id}`} empty="No requests."
          columns={[{ key: 'ref', label: 'Request' }, { key: 'customer', label: 'Customer' }, { key: 'product', label: 'Equipment', render: (t) => t.product || '—' },
            { key: 'description', label: 'Problem', render: (t) => <span className="clip">{t.description}</span> },
            { key: 'technician', label: 'Technician', render: (t) => t.technician || <span className="bad">Unassigned</span> },
            { key: 'priority', label: '', render: (t) => (t.priority === '2' ? <Pill state="failed">Urgent</Pill> : t.priority === '1' ? <Pill state="waiting">High</Pill> : null) },
            { key: 'days_open', label: 'Days', num: true }, { key: 'warranty_id', label: 'Cover', render: (t) => (t.warranty_id ? 'Warranty' : 'Billable') },
            { key: 'stage', label: 'Stage', render: (t) => <Pill state={t.stage}>{t.stage_label}</Pill> }]} />
      )}
    </>
  );
}

function NewTicket({ onDone }) {
  const navigate = useNavigate();
  const { busy, run } = useAction();
  const [q, setQ] = useState('');
  const [found, setFound] = useState([]);
  const [f, setF] = useState({ customer_id: '', serial: '', fault_code: '', description: '', channel: 'phone', technician_id: '' });
  const techs = useLoad(() => get('/api/staff/people', { role: 'technician' }), []);
  useEffect(() => {
    if (q.trim().length < 3) { setFound([]); return; }
    const t = setTimeout(() => get('/api/staff/customers', { q }).then((r) => setFound(r.rows.slice(0, 6))).catch(() => {}), 300);
    return () => clearTimeout(t);
  }, [q]);
  const save = async (e) => {
    e.preventDefault();
    const r = await run('s', () => post('/api/staff/tickets', { ...f, customer_id: Number(f.customer_id) || 0, technician_id: Number(f.technician_id) || null }), 'Request created.');
    if (r) { onDone(); navigate(`/app/service/${r.id}`); }
  };
  const chosen = found.find((c) => String(c.id) === String(f.customer_id));
  return (
    <Section title="New service request" className="ws-card--accent">
      <form className="ws-form" onSubmit={save}>
        <div className="field field--full">
          <label className="label" htmlFor="tq">Customer (phone, name or serial)</label>
          <input id="tq" className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Type at least 3 characters" />
          <div className="crew-pick">{found.map((c) => <button key={c.id} type="button" className={`chip${String(c.id) === String(f.customer_id) ? ' is-active' : ''}`} onClick={() => setF({ ...f, customer_id: c.id })}>{c.name} · {c.phone}</button>)}</div>
          {chosen && <span className="form-hint">Selected: {chosen.name}</span>}
        </div>
        <F label="Serial number (if known)" value={f.serial} onChange={(v) => setF({ ...f, serial: v })} hint="Links the request to the warranty automatically." />
        <F label="Error code" value={f.fault_code} onChange={(v) => setF({ ...f, fault_code: v })} />
        <F label="Channel" type="select" value={f.channel} onChange={(v) => setF({ ...f, channel: v })} options={['phone', 'whatsapp', 'website', 'visit'].map((c) => ({ value: c, label: c }))} />
        <F label="Technician" type="select" value={f.technician_id} onChange={(v) => setF({ ...f, technician_id: v })} options={[{ value: '', label: 'Assign later' }, ...(techs.data || []).map((t) => ({ value: t.id, label: t.name }))]} />
        <F label="What’s wrong?" type="textarea" full value={f.description} onChange={(v) => setF({ ...f, description: v })} />
        <div className="field--full"><button className="btn btn--primary btn--sm" disabled={busy || (!f.customer_id && !f.serial) || f.description.trim().length < 10}>Create request</button></div>
      </form>
    </Section>
  );
}

const T_NEXT = { new: [['diagnose', 'Mark diagnosed']], diagnosed: [['repair', 'Start repair'], ['resolve', 'Repair done – ask customer']], repair: [['resolve', 'Repair done – ask customer']], awaiting: [['confirm', 'Customer confirmed'], ['reopen', 'Not fixed – reopen']], closed: [['reopen', 'Reopen']] };
export function Ticket() {
  const { id } = useParams();
  const { me } = useAuth();
  const { busy, run } = useAction();
  const { data: t, error, reload, setData } = useLoad(() => get(`/api/staff/tickets/${id}`), [id]);
  const techs = useLoad(() => get('/api/staff/people', { role: 'technician' }), []);
  const parts = useLoad(() => get('/api/staff/products').catch(() => ({ rows: [] })), []);
  const [addPart, setAddPart] = useState('');
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!t) return <Loading />;
  const open = t.can_edit && !['closed', 'cancel'].includes(t.stage);
  const set = (k) => (v) => setData({ ...t, [k]: v });
  const body = () => ({ resolution: t.resolution, labour_hours: t.labour_hours || 0, fault_code: t.fault_code,
    lines: t.lines.map((l) => ({ product_id: l.product_id, qty: l.qty, new_serial: l.new_serial })),
    ...(t.can_assign ? { technician_id: t.technician_id || null, priority: t.priority } : {}) });
  const save = () => run('save', () => patch(`/api/staff/tickets/${id}`, body()), 'Saved.').then((r) => r && reload());
  const act = (a, msg) => run(a, async () => { if (open) await patch(`/api/staff/tickets/${id}`, body()); return post(`/api/staff/tickets/${id}/${a}`); }, msg).then((r) => r && reload());
  const diagnose = async () => {
    const r = await run('ai', () => api.diagnose({ fault_code: t.fault_code || '', description: t.description || '', inverter_brand: t.product || '' }), 'AI diagnosis ready.');
    if (r) {
      await patch(`/api/staff/tickets/${id}`, { ai_diagnosis: { likely_cause: r.likely_cause, steps: r.steps, needs_site_visit: r.needs_site_visit, likely_parts: r.likely_parts, confidence: r.confidence, source: r.source } });
      reload();
    }
  };
  const ai = t.ai_diagnosis;
  const sellable = (parts.data?.rows || []).filter((p) => !p.is_kit && !p.is_service);
  return (
    <>
      <PageHead back={{ to: '/app/service', label: 'Service' }} eyebrow={`${t.ref} · via ${t.channel || 'phone'} · open ${t.days_open} day${t.days_open === 1 ? '' : 's'}`} title={t.customer}
                sub={[t.product, t.serial && `serial ${t.serial}`, t.order_ref && `order ${t.order_ref}`].filter(Boolean).join(' · ') || 'Equipment not specified'}>
        <Pill state={t.under_warranty ? 'done' : 'waiting'}>{t.under_warranty ? 'Under warranty – free' : 'Out of warranty – billable'}</Pill>
        <Pill state={t.stage}>{t.stage_label}</Pill>
        {t.phone && <a className="btn btn--secondary btn--sm" href={`tel:${t.phone}`}>Call</a>}
        {t.can_edit && (T_NEXT[t.stage] || []).map(([a, label]) => <button key={a} className={`btn btn--sm ${a === 'reopen' ? 'btn--secondary' : 'btn--primary'}`} disabled={!!busy} onClick={() => act(a, `${label}.`)}>{label}</button>)}
        {t.can_delete && !t.invoice && <DeleteButton url={`/api/staff/tickets/${id}`} what="this request" after="/app/service" />}
      </PageHead>
      <div className="side-grid">
        <div className="stack">
          <Section title="Complaint">
            <p>{t.description}</p>
            <div className="ws-form">
              <F label="Error code" value={t.fault_code} onChange={set('fault_code')} disabled={!open} />
              <div className="field" style={{ alignSelf: 'end' }}>
                <button className="btn btn--secondary btn--sm" disabled={busy === 'ai' || !(t.fault_code || t.description)} onClick={diagnose}>{busy === 'ai' ? 'Diagnosing…' : '✨ AI diagnose'}</button>
              </div>
            </div>
          </Section>
          {ai && (
            <Section title="AI diagnosis" className="ws-card--accent">
              <p><strong>Likely cause:</strong> {ai.likely_cause}</p>
              <ol className="steps">{(ai.steps || []).map((s, i) => <li key={i}>{s}</li>)}</ol>
              <p className="muted small">Site visit: {ai.needs_site_visit ? 'yes' : 'no'} · Likely parts: {(ai.likely_parts || []).join(', ') || 'none'} · Confidence {Math.round((ai.confidence || 0) * 100)}% · {ai.source}</p>
            </Section>
          )}
          <Section title="Parts & labour" actions={open && <button className="btn btn--primary btn--sm" disabled={busy === 'save'} onClick={save}>Save</button>}>
            <div className="table-scroll">
              <table className="table">
                <thead><tr><th>Part</th><th className="num">Qty</th><th className="num">Price</th><th>New serial</th><th /></tr></thead>
                <tbody>
                  {t.lines.map((l, i) => (
                    <tr key={i}>
                      <td>{l.product}</td>
                      <td className="num">{open ? <input className="input input--xs" type="number" min="1" value={l.qty} onChange={(e) => setData({ ...t, lines: t.lines.map((x, k) => (k === i ? { ...x, qty: e.target.value } : x)) })} /> : l.qty}</td>
                      <td className="num">{inr(l.price_unit)}</td>
                      <td>{open ? <input className="input input--xs input--mono" value={l.new_serial || ''} onChange={(e) => setData({ ...t, lines: t.lines.map((x, k) => (k === i ? { ...x, new_serial: e.target.value } : x)) })} /> : l.new_serial || '—'}</td>
                      <td>{open && <button className="link link--btn" onClick={() => setData({ ...t, lines: t.lines.filter((_, k) => k !== i) })}>Remove</button>}</td>
                    </tr>
                  ))}
                  {!t.lines.length && <tr><td colSpan={5} className="empty">No parts used.</td></tr>}
                </tbody>
              </table>
            </div>
            {open && (
              <div className="ws-form ws-form--tight">
                <F label="Add a part" type="select" value={addPart} onChange={(v) => {
                  setAddPart('');
                  const p = sellable.find((x) => String(x.id) === v);
                  if (p) setData({ ...t, lines: [...t.lines, { product_id: p.id, product: p.name, qty: 1, price_unit: p.price, new_serial: '' }] });
                }} options={[{ value: '', label: 'Choose a part…' }, ...sellable.map((p) => ({ value: String(p.id), label: `${p.name} (${inr(p.price)})` }))]} />
                <F label="Labour hours" type="number" step="0.25" min="0" value={t.labour_hours} onChange={set('labour_hours')} />
              </div>
            )}
            <KV items={[['Parts', inr(t.parts_price)], ['Labour', `${inr(t.labour)} (${t.labour_hours || 0} h × ${inr(t.labour_rate)})`],
              ['Customer pays', <strong key="c">{t.under_warranty ? 'Nothing (warranty)' : inr(t.customer_charge)}</strong>],
              me.role === 'director' && ['Cost to company', inr(t.repair_cost)],
              t.invoice && ['Invoice', `${t.invoice.ref} · ${inr(t.invoice.amount_total)} incl. GST · ${t.invoice.state === 'paid' ? 'paid' : `${inr(t.invoice.amount_total - t.invoice.amount_paid)} unpaid`}`]]} />
            {t.invoice && t.invoice.state === 'posted' && ['director', 'sales', 'support'].includes(me.role) && (
              <button type="button" className="btn btn--secondary btn--sm" disabled={busy === 'paid'} style={{ marginTop: 10 }}
                      onClick={() => {
                        const due = Math.round((t.invoice.amount_total - t.invoice.amount_paid) * 100) / 100;
                        if (!window.confirm(`Record ${inr(due)} received in cash for ${t.invoice.ref}?`)) return;
                        run('paid', () => post(`/api/staff/invoices/${t.invoice.id}/payment`, { amount: due, method: 'cash' }),
                          'Payment recorded.').then((r) => r && reload());
                      }}>Record payment received</button>
            )}
          </Section>
          <Section title="Resolution" actions={open && <button className="btn btn--primary btn--sm" disabled={busy === 'save'} onClick={save}>Save</button>}>
            <F label="What was repaired or replaced?" type="textarea" value={t.resolution} onChange={set('resolution')} disabled={!open} />
          </Section>
        </div>
        <div className="stack">
          <Section title="Assignment" actions={t.can_assign && open && <button className="btn btn--secondary btn--sm" disabled={busy === 'save'} onClick={save}>Save</button>}>
            {t.can_assign && open ? (
              <div className="ws-form">
                <F label="Technician" type="select" value={t.technician_id || ''} onChange={(v) => set('technician_id')(v ? Number(v) : null)} options={[{ value: '', label: 'Unassigned' }, ...(techs.data || []).map((x) => ({ value: x.id, label: x.name }))]} />
                <F label="Priority" type="select" value={t.priority || '0'} onChange={set('priority')} options={[{ value: '0', label: 'Normal' }, { value: '1', label: 'High' }, { value: '2', label: 'Urgent' }]} />
              </div>
            ) : <KV items={[['Technician', t.technician || 'Unassigned'], ['Priority', { 0: 'Normal', 1: 'High', 2: 'Urgent' }[t.priority || '0']]]} />}
            <KV items={[['Phone', t.phone], ['Address', [t.street, t.city].filter(Boolean).join(', ')], ['Warranty until', fmtDate(t.warranty_end)], ['Reported', fmtDate(t.reported_on, true)]]} />
          </Section>
          <Notes model="ticket" id={t.id} notes={t.notes} reload={reload} />
        </div>
      </div>
    </>
  );
}

/* ============================================================== warranties */
export function Warranties() {
  const [q, setQ] = useParam('q');
  const [status, setStatus] = useParam('status');
  const { data, error, reload } = useLoad(() => get('/api/staff/warranties', { q, status }), [q, status]);
  const { me } = useAuth();
  const { run } = useAction();
  const extend = (w) => {
    const v = window.prompt(`Warranty length for ${w.serial} in months (now ${w.months}):`, String(w.months + 12));
    if (v && Number(v) > 0) run('w', () => patch(`/api/staff/warranties/${w.id}`, { months: Number(v) }), 'Warranty updated.').then((r) => r && reload());
  };
  return (
    <>
      <PageHead eyebrow="Service" title="Warranty register" sub="Every serial with its customer and warranty end date. Search by serial, customer, phone or order.">
        <Search value={q} onChange={setQ} placeholder="Serial, customer, phone, order" />
      </PageHead>
      <Chips value={status} onChange={setStatus} options={[{ value: '', label: 'All' }, { value: 'active', label: 'Under warranty' }, { value: 'expired', label: 'Expired' }]} />
      {error ? <ErrorBox error={error} onRetry={reload} /> : !data ? <Loading /> : (
        <Table rows={data.rows} empty="No warranties match."
          columns={[{ key: 'serial', label: 'Serial', render: (w) => <code>{w.serial}</code> }, { key: 'product', label: 'Equipment' },
            { key: 'customer', label: 'Customer', render: (w) => <Link to={`/app/customers/${w.customer_id}`}>{w.customer}</Link> }, { key: 'phone', label: 'Phone' },
            { key: 'order_ref', label: 'Order' }, { key: 'start_date', label: 'From', render: (w) => fmtDate(w.start_date) },
            { key: 'end_date', label: 'Until', render: (w) => fmtDate(w.end_date) },
            { key: 'active', label: 'Status', render: (w) => <Pill state={w.active ? 'active' : 'expired'}>{w.active ? 'Active' : 'Expired'}</Pill> },
            ...(me.role === 'director' ? [{ key: 'ext', label: '', render: (w) => <button className="link link--btn" onClick={() => extend(w)}>Change</button> }] : [])]} />
      )}
    </>
  );
}
