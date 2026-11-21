import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, inr, num } from '../api.js';
import { estimateLocal, RULES } from '../solar.js';
import { DEFAULT_STATE, saveState, savedState, useSubsidyTable } from '../subsidy.js';
import Tabs from '../components/ui/Tabs.jsx';
import ElasticSlider from '../components/ui/ElasticSlider.jsx';
import Switch from '../components/ui/Switch.jsx';
import { useToast } from '../components/ui/Toast.jsx';
import EnquirySuccess from '../components/EnquirySuccess.jsx';

const RANGE = { units: { min: 60, max: 900, step: 10 }, bill: { min: 500, max: 8000, step: 100 } };

export default function Estimate() {
  const [params] = useSearchParams();
  const toast = useToast();
  const [mode, setMode] = useState(params.get('bill') ? 'bill' : 'units');
  const [units, setUnits] = useState(Number(params.get('units')) || 360);
  const [bill, setBill] = useState(Number(params.get('bill')) || 2800);
  const table = useSubsidyTable();
  const [state, setState] = useState(() => params.get('state') || savedState());
  const [topup, setTopup] = useState(false);
  const [custom, setCustom] = useState(false);
  const [c, setC] = useState({ kw: '', costPerKw: String(RULES.costPerKw), tariff: String(RULES.tariff) });
  const [est, setEst] = useState(() => estimateLocal(units, 0, { state }));
  const [scanning, setScanning] = useState(false);
  const [scanMsg, setScanMsg] = useState('');
  const fileRef = useRef(null);

  const [form, setForm] = useState({ name: '', phone: '', email: '', street: '', city: 'Ahmedabad', subsidy: true });
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(null);

  const value = mode === 'units' ? units : bill;
  const setValue = mode === 'units' ? setUnits : setBill;

  const stateRow = table?.states.find((x) => x.name === state);
  const customOpts = custom ? {
    kw: Number(c.kw) || undefined, costPerKw: Number(c.costPerKw) || undefined, tariff: Number(c.tariff) || undefined
  } : {};
  const customErr = custom && (
    (c.kw && !(Number(c.kw) >= 0.5 && Number(c.kw) <= 100) && 'System size must be between 0.5 and 100 kW.') ||
    (c.costPerKw && !(Number(c.costPerKw) >= 10000 && Number(c.costPerKw) <= 500000) && 'Price per kW must be between ₹10,000 and ₹5,00,000.') ||
    (c.tariff && !(Number(c.tariff) >= 1 && Number(c.tariff) <= 50) && 'Electricity rate must be between ₹1 and ₹50 per unit.'));

  const pickState = (name) => { setState(name); saveState(name); setTopup(false); };

  // Instant local figures, then the server's authoritative estimate (debounced).
  useEffect(() => {
    if (customErr) return undefined;
    const u = mode === 'units' ? units : 0;
    const b = mode === 'bill' ? bill : 0;
    setEst(estimateLocal(u, b, { state, topup, table, ...customOpts }));
    const t = setTimeout(() => {
      api.estimate({ units: u, bill: b, state, topup, kw: customOpts.kw, cost_per_kw: customOpts.costPerKw, tariff: customOpts.tariff })
        .then((r) => r && r.kw && setEst(r)).catch(() => {});
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, units, bill, state, topup, table, custom, c.kw, c.costPerKw, c.tariff]);

  const onBill = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setScanning(true);
    setScanMsg('Reading your bill. This can take up to a minute…');
    try {
      const data = await api.parseBill(file);
      if (data.monthly_units_kwh) {
        setMode('units');
        setUnits(Math.round(data.monthly_units_kwh));
      } else if (data.bill_amount) {
        setMode('bill');
        setBill(Math.round(data.bill_amount));
      } else {
        throw new Error('No usage found on the bill');
      }
      setScanMsg(`Filled in from your bill${data.discom ? ` (${data.discom})` : ''}. Please check the numbers.`);
    } catch {
      setScanMsg('We couldn’t read that bill automatically. Please enter your usage above.');
    } finally {
      setScanning(false);
    }
  };

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    if (!est) return;
    setSending(true);
    try {
      const res = await api.submitEnquiry({
        ...form,
        system_kw: est.kw,
        system_type: 'on_grid',
        monthly_bill: mode === 'bill' ? bill : Math.round(est.units * 8),
        notes: `Website estimate (${est.state}): ${est.units} units/month → ${est.kw} kW On-Grid, subsidy ${inr(est.subsidy)}` +
          (custom ? `, custom price ${inr(est.cost_per_kw)}/kW at ₹${est.tariff}/unit` : '')
      });
      if (!res?.ok) throw new Error(res?.error || 'Request failed');
      setDone({ ...res, phone: form.phone });
      toast('Survey request sent. We’ll call you shortly.');
    } catch (err) {
      toast(err.message || 'We couldn’t send your request. Please call +91 79 4000 5000.', 'error');
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      <section className="page-head wrap">
        <span className="eyebrow">Savings estimate</span>
        <h1 className="headline">What will solar save you?</h1>
        <p className="lead">Move the slider to match your usage. Your system size, savings and subsidy update instantly.</p>
      </section>

      <section className="wrap est">
        {/* INPUT */}
        <div className="card card--alt">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <h2 className="title" style={{ fontSize: 21 }}>Your usage</h2>
            <Tabs
              label="Usage input"
              value={mode}
              onChange={setMode}
              items={[{ value: 'units', label: 'Units' }, { value: 'bill', label: 'Bill' }]}
            />
          </div>

          <div className="est__big tabular">
            {mode === 'units' ? num(units) : inr(bill)}
            <small>{mode === 'units' ? 'kWh / month' : 'per month'}</small>
          </div>

          <ElasticSlider
            {...RANGE[mode]}
            value={value}
            onChange={setValue}
            label={mode === 'units' ? 'Monthly units' : 'Monthly bill'}
            format={(v) => (mode === 'units' ? `${v} kWh` : inr(v))}
          />

          <div className="field" style={{ marginTop: 12 }}>
            <label className="label" htmlFor="usage">{mode === 'units' ? 'Or type your monthly units' : 'Or type your monthly bill (₹)'}</label>
            <input
              id="usage"
              className="input"
              type="number"
              min="0"
              inputMode="numeric"
              value={value || ''}
              onChange={(e) => setValue(Math.max(0, Number(e.target.value) || 0))}
            />
            {mode === 'bill' && <span className="form-hint">We assume ₹8 per unit when only the bill is known.</span>}
          </div>

          <div className="upload">
            <div>
              <div style={{ fontWeight: 500 }}>Have your electricity bill?</div>
              <div className="form-hint">Upload a photo and we’ll fill this in for you.</div>
            </div>
            <input ref={fileRef} type="file" accept="image/*" onChange={onBill} />
            <button type="button" className="btn btn--secondary btn--sm" disabled={scanning} onClick={() => fileRef.current?.click()}>
              {scanning ? 'Reading…' : 'Upload bill'}
            </button>
          </div>
          {scanMsg && <p className="status" role="status">{scanMsg}</p>}

          <div className="field" style={{ marginTop: 20 }}>
            <label className="label" htmlFor="state">Your state</label>
            <select id="state" className="select" value={state} onChange={(e) => pickState(e.target.value)}>
              {(table?.states || [{ name: DEFAULT_STATE }]).map((s) => <option key={s.name} value={s.name}>{s.name}</option>)}
            </select>
            <span className="form-hint">
              {stateRow?.category === 'special'
                ? 'Special-category state: 10% higher central subsidy (up to ₹85,800).'
                : 'Central subsidy: ₹30,000/kW for 2 kW + ₹18,000 for the 3rd kW (up to ₹78,000).'}
            </span>
          </div>
          {stateRow?.topup && (
            <div className="est__topup">
              <Switch checked={topup} onChange={setTopup}>Add the reported {state} top-up</Switch>
              <span className="form-hint">{stateRow.note}. Not yet confirmed officially, so check with your DISCOM before relying on it.</span>
            </div>
          )}

          <div className="est__custom">
            <Switch checked={custom} onChange={setCustom}>Custom price calculation</Switch>
            {custom && (
              <>
                <div className="form-row">
                  <div className="field">
                    <label className="label" htmlFor="c-kw">System size (kW)</label>
                    <input id="c-kw" className="input" type="number" min="0.5" max="100" step="0.5" inputMode="decimal"
                           placeholder={`${est?.kw || 3} (recommended)`} value={c.kw} onChange={(e) => setC({ ...c, kw: e.target.value })} />
                  </div>
                  <div className="field">
                    <label className="label" htmlFor="c-price">Price per kW (₹)</label>
                    <input id="c-price" className="input" type="number" min="10000" step="1000" inputMode="numeric"
                           value={c.costPerKw} onChange={(e) => setC({ ...c, costPerKw: e.target.value })} />
                  </div>
                  <div className="field field--full">
                    <label className="label" htmlFor="c-tariff">Your electricity rate (₹ per unit)</label>
                    <input id="c-tariff" className="input" type="number" min="1" max="50" step="0.5" inputMode="decimal"
                           value={c.tariff} onChange={(e) => setC({ ...c, tariff: e.target.value })} />
                  </div>
                </div>
                {customErr
                  ? <p className="field-error" role="alert">{customErr}</p>
                  : <span className="form-hint">Use a price from another quote, or your own tariff, to compare. The subsidy still follows the rules for {state} (capped at 3 kW).</span>}
                <button type="button" className="link link--btn" style={{ justifySelf: 'start' }}
                        onClick={() => setC({ kw: '', costPerKw: String(RULES.costPerKw), tariff: String(RULES.tariff) })}>Reset to SunPower prices</button>
              </>
            )}
          </div>
        </div>

        {/* RESULT */}
        <div className="card card--outline est__result" aria-live="polite">
          {est ? (
            <>
              <span className="label">{custom && c.kw ? 'Your system' : 'Recommended system'}</span>
              <div className="est__kw tabular" style={{ marginTop: 8 }}>{est.kw}<span>kW On-Grid</span></div>
              {custom && <span className="pill pill--warn" style={{ marginTop: 6 }}>Custom calculation</span>}
              <p className="muted small" style={{ marginTop: 10 }}>
                {est.units ? `Based on ${num(est.units)} units a month. ` : ''}Needs about {num(est.roof_sqft)} sq ft of shadow-free roof.
              </p>
              <div className="metrics">
                <div className="metric"><div className="metric__label">Monthly saving</div><div className="metric__value good tabular">{inr(est.monthly_saving)}</div></div>
                <div className="metric"><div className="metric__label">Yearly saving</div><div className="metric__value tabular">{inr(est.yearly_saving)}</div></div>
                <div className="metric"><div className="metric__label">Generation</div><div className="metric__value tabular">{num(est.generation)} <span className="small muted">units/mo</span></div></div>
                <div className="metric"><div className="metric__label">Payback</div><div className="metric__value tabular">{est.payback_years} <span className="small muted">years</span></div></div>
              </div>
              <div className="rows tabular">
                <div><span className="muted">{custom ? `System price (${est.kw} kW × ${inr(est.cost_per_kw)})` : 'Indicative system price'}</span><span>{inr(est.cost)}</span></div>
                <div><span className="muted">PM Surya Ghar subsidy · {est.state}</span><span className="good">− {inr(est.subsidy_central ?? est.subsidy)}</span></div>
                {est.subsidy_topup > 0 && <div><span className="muted">{est.state} top-up (reported)</span><span className="good">− {inr(est.subsidy_topup)}</span></div>}
                <div className="total"><span>You pay, approximately</span><span>{inr(est.net_cost)}</span></div>
              </div>
            </>
          ) : (
            <p className="empty">Enter your monthly usage to see your estimate.</p>
          )}
        </div>
      </section>

      {/* BOOK SURVEY */}
      <section className="section">
        <div className="wrap wrap--narrow">
          <div className="card card--alt">
            {done ? (
              <EnquirySuccess result={done} onReset={() => setDone(null)} resetLabel="Recalculate" />
            ) : (
              <form className="form" onSubmit={submit}>
                <div>
                  <h2 className="title">Book your free site survey.</h2>
                  <p className="muted" style={{ marginTop: 8 }}>
                    For your {est ? `${est.kw} kW` : ''} system. An advisor will call you within two working hours.
                  </p>
                </div>
                <div className="form-row">
                  <div className="field"><label className="label" htmlFor="e-name">Full name</label><input id="e-name" className="input" required value={form.name} onChange={set('name')} autoComplete="name" /></div>
                  <div className="field"><label className="label" htmlFor="e-phone">Phone</label><input id="e-phone" className="input" type="tel" required value={form.phone} onChange={set('phone')} autoComplete="tel" /></div>
                  <div className="field"><label className="label" htmlFor="e-email">Email <span className="form-hint">(optional)</span></label><input id="e-email" className="input" type="email" value={form.email} onChange={set('email')} autoComplete="email" /></div>
                  <div className="field"><label className="label" htmlFor="e-city">City</label><input id="e-city" className="input" value={form.city} onChange={set('city')} autoComplete="address-level2" /></div>
                  <div className="field field--full"><label className="label" htmlFor="e-street">Address <span className="form-hint">(optional)</span></label><input id="e-street" className="input" value={form.street} onChange={set('street')} autoComplete="street-address" /></div>
                </div>
                <Switch checked={form.subsidy} onChange={(v) => setForm((f) => ({ ...f, subsidy: v }))}>Apply for the PM Surya Ghar subsidy</Switch>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                  <span className="form-hint">Prefer more options? <Link to="/quote" className="link">Request a full quote</Link></span>
                  <button type="submit" className="btn btn--primary" disabled={sending || !est}>{sending ? 'Sending…' : 'Book free survey'}</button>
                </div>
              </form>
            )}
          </div>
        </div>
      </section>
    </>
  );
}
