import { useEffect, useState } from 'react';
import { useAuth } from '../auth.jsx';
import { api } from '../api.js';
import Tabs from '../components/ui/Tabs.jsx';
import Switch from '../components/ui/Switch.jsx';
import { useToast } from '../components/ui/Toast.jsx';
import EnquirySuccess from '../components/EnquirySuccess.jsx';

const SIZES = ['1', '2', '3', '4', '5'];
const EMPTY = {
  name: '', phone: '', email: '', city: 'Ahmedabad', street: '',
  system_kw: '3', system_type: 'on_grid', monthly_bill: '', roof_area: '', subsidy: true, notes: ''
};

export default function Quote() {
  const toast = useToast();
  const [f, setF] = useState(EMPTY);
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(null);
  const { me } = useAuth();

  // Signed-in customer: start with their name and email
  useEffect(() => {
    if (me?.role === 'customer') setF((s) => ({ ...s, name: s.name || me.name || '', email: s.email || me.login || '' }));
  }, [me]);

  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));
  const put = (k, v) => setF((s) => ({ ...s, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    setSending(true);
    try {
      const res = await api.submitEnquiry(f);
      if (!res?.ok) throw new Error(res?.error || 'Request failed');
      setDone({ ...res, phone: f.phone });
      toast('Quote request sent. We’ll call you shortly.');
    } catch (err) {
      toast(err.message || 'We couldn’t send your request. Please call +91 79 4000 5000.', 'error');
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      <section className="page-head wrap">
        <span className="eyebrow">Free quote</span>
        <h1 className="headline">Let’s size your system.</h1>
        <p className="lead">Tell us a little about your home. We’ll call within two working hours to book your free roof survey.</p>
      </section>

      <section className="wrap wrap--narrow" style={{ paddingBottom: 'clamp(72px, 10vw, 120px)' }}>
        <div className="card card--alt">
          {done ? (
            <EnquirySuccess result={done} onReset={() => { setDone(null); setF(EMPTY); }} />
          ) : (
            <form className="form" onSubmit={submit}>
              <div className="field">
                <span className="label">System size</span>
                <div className="choices" role="radiogroup" aria-label="System size">
                  {[...SIZES, ''].map((s) => (
                    <button
                      key={s || 'unsure'}
                      type="button"
                      role="radio"
                      aria-checked={f.system_kw === s}
                      className={`choice${f.system_kw === s ? ' is-active' : ''}`}
                      onClick={() => put('system_kw', s)}
                    >
                      <div className="choice__main">{s ? `${s} kW` : 'Not sure'}</div>
                      <div className="choice__sub">{s ? `~${s * 120} units` : 'Advise me'}</div>
                    </button>
                  ))}
                </div>
              </div>

              <div className="field">
                <span className="label">System type</span>
                <div>
                  <Tabs
                    label="System type"
                    value={f.system_type}
                    onChange={(v) => put('system_type', v)}
                    items={[{ value: 'on_grid', label: 'On-Grid' }, { value: 'off_grid', label: 'Battery backup' }]}
                  />
                </div>
                <span className="form-hint">
                  {f.system_type === 'on_grid' ? 'Uses net metering. Eligible for the PM Surya Ghar subsidy.' : 'Keeps power on during outages with batteries.'}
                </span>
              </div>

              <div className="form-row">
                <div className="field"><label className="label" htmlFor="q-bill">Monthly bill (₹)</label><input id="q-bill" className="input" type="number" min="0" inputMode="numeric" placeholder="3,500" value={f.monthly_bill} onChange={set('monthly_bill')} /></div>
                <div className="field"><label className="label" htmlFor="q-roof">Shadow-free roof area (sq ft)</label><input id="q-roof" className="input" type="number" min="0" inputMode="numeric" placeholder="400" value={f.roof_area} onChange={set('roof_area')} /></div>
              </div>

              <div style={{ borderTop: '1px solid var(--line)', paddingTop: 20 }} className="form-row">
                <div className="field"><label className="label" htmlFor="q-name">Full name</label><input id="q-name" className="input" required autoComplete="name" value={f.name} onChange={set('name')} /></div>
                <div className="field"><label className="label" htmlFor="q-phone">Phone</label><input id="q-phone" className="input" type="tel" required autoComplete="tel" value={f.phone} onChange={set('phone')} /></div>
                <div className="field"><label className="label" htmlFor="q-email">Email <span className="form-hint">(optional)</span></label><input id="q-email" className="input" type="email" autoComplete="email" value={f.email} onChange={set('email')} /></div>
                <div className="field"><label className="label" htmlFor="q-city">City</label><input id="q-city" className="input" autoComplete="address-level2" value={f.city} onChange={set('city')} /></div>
                <div className="field field--full"><label className="label" htmlFor="q-street">Address <span className="form-hint">(optional)</span></label><input id="q-street" className="input" autoComplete="street-address" value={f.street} onChange={set('street')} /></div>
                <div className="field field--full"><label className="label" htmlFor="q-notes">Anything else? <span className="form-hint">(optional)</span></label><textarea id="q-notes" className="textarea" rows={2} value={f.notes} onChange={set('notes')} /></div>
              </div>

              <Switch checked={f.subsidy} onChange={(v) => put('subsidy', v)}>Apply for the PM Surya Ghar subsidy (up to ₹78,000)</Switch>

              <button type="submit" className="btn btn--primary btn--block" disabled={sending}>
                {sending ? 'Sending…' : 'Request my free quote'}
              </button>
            </form>
          )}
        </div>
      </section>
    </>
  );
}
