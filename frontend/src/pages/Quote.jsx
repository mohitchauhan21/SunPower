import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth.jsx';
import { api, inr, num } from '../api.js';
import Tabs from '../components/ui/Tabs.jsx';
import Switch from '../components/ui/Switch.jsx';
import InfoTip from '../components/ui/InfoTip.jsx';
import { useToast } from '../components/ui/Toast.jsx';
import EnquirySuccess from '../components/EnquirySuccess.jsx';
import { estimateLocal } from '../solar.js';
import { saveState, savedState, useSubsidyTable } from '../subsidy.js';
import { clearBookingDraft, clearQuotePrefill, normalizePhone, readBookingDraft, readQuotePrefill, saveBookingDraft } from '../quotePrefill.js';

const TYPES = {
  on_grid: {
    label: 'On-Grid',
    help: 'Connected to the electricity grid with net metering: extra units go to the grid and are credited on your bill. It switches off during a power cut (a safety rule), and it is the type the PM Surya Ghar subsidy covers.'
  },
  off_grid: {
    label: 'Off-Grid',
    help: 'Runs on its own with batteries, so selected appliances keep running in a power cut. Battery size decides what you can run and for how long. Off-grid systems are not covered by the PM Surya Ghar subsidy, and the batteries add to the price.'
  }
};

const SLOTS = [
  { value: 'morning', label: 'Morning', sub: '9am–12pm' },
  { value: 'afternoon', label: 'Afternoon', sub: '12–3pm' },
  { value: 'evening', label: 'Evening', sub: '3–6pm' }
];
const iso = (d) => d.toISOString().slice(0, 10);
const dayOffset = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return iso(d); };

const blank = (state) => ({
  preferred_date: '', preferred_slot: '',
  name: '', phone: '', email: '', state, street: '', system_type: 'on_grid', monthly_bill: '', roof_area: '',
  subsidy: true, notes: ''
});

export default function Quote() {
  const toast = useToast();
  const { me } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const table = useSubsidyTable();
  // Figures carried over from the savings page (only when coming from it)
  const prefill = useMemo(() => (params.get('from') === 'estimate' ? readQuotePrefill() : null), [params]);
  // Back from signing up: the form exactly as the guest left it.
  const draft = useMemo(() => (params.get('resume') ? readBookingDraft() : null), [params]);
  const [f, setF] = useState(() => draft || ({
    ...blank(prefill?.state || savedState()),
    monthly_bill: prefill?.monthly_bill ? String(prefill.monthly_bill) : ''
  }));
  const [locked, setLocked] = useState({});   // personal details that come from the customer's account
  const [errors, setErrors] = useState({});
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(null);
  const sent = useRef(false);

  // Signed-in customer: name, mobile and email come from their account and can't be changed here
  // (the address can: it may be another property).
  useEffect(() => {
    if (me?.role !== 'customer') return;
    api.myOverview().then((o) => {
      const c = o?.customer || {};
      const phone = normalizePhone(c.phone) ? c.phone : '';
      setF((s) => ({ ...s, name: c.name || s.name, email: c.email || s.email, phone: phone || s.phone,
        street: s.street || (draft ? '' : c.street || '') }));
      setLocked({ name: !!c.name, email: !!c.email, phone: !!phone });
    }).catch(() => {});
  }, [me, draft]);

  const set = (k) => (e) => { setF((s) => ({ ...s, [k]: e.target.value })); setErrors((x) => ({ ...x, [k]: '' })); };
  const put = (k, v) => setF((s) => ({ ...s, [k]: v }));

  const offGrid = f.system_type === 'off_grid';
  const bill = Number(f.monthly_bill) || 0;
  // Size: the savings-page size while the bill is unchanged, else what the bill suggests,
  // else none (the advisor recommends one).
  const opts = {
    state: f.state, topup: !offGrid && f.subsidy && prefill?.topup, table, systemType: f.system_type,
    costPerKw: prefill?.custom?.costPerKw, tariff: prefill?.custom?.tariff
  };
  const samePrefill = prefill?.kw && (!f.monthly_bill || bill === Number(prefill.monthly_bill));
  const est = samePrefill ? estimateLocal(prefill.units || 0, 0, { ...opts, kw: prefill.kw })
    : bill > 0 ? estimateLocal(0, bill, opts) : null;
  const subsidyShown = !offGrid && f.subsidy;
  const total = est ? (subsidyShown ? est.net_cost : est.cost) : null;

  const validate = () => {
    const e = {};
    if (f.name.trim().length < 2) e.name = 'Please enter your full name.';
    if (!normalizePhone(f.phone)) e.phone = 'Enter a 10-digit Indian mobile number, e.g. 98765 43210.';
    if (!f.state) e.state = 'Choose your state.';
    if (!f.preferred_date) e.preferred_date = 'Choose the day you’d like the survey.';
    else if (f.preferred_date < dayOffset(1) || f.preferred_date > dayOffset(30)) e.preferred_date = 'Choose a day between tomorrow and 30 days from now.';
    if (!f.preferred_slot) e.preferred_slot = 'Choose a time slot.';
    if (f.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.email.trim())) e.email = 'This email doesn’t look right.';
    if (f.monthly_bill && !(bill >= 100 && bill <= 1000000)) e.monthly_bill = 'Enter your monthly bill in rupees (₹100 or more).';
    if (f.roof_area && !(Number(f.roof_area) >= 20 && Number(f.roof_area) <= 100000)) e.roof_area = 'Enter an area in square feet, or leave it empty.';
    setErrors(e);
    return !Object.keys(e).length;
  };

  const submit = async (e) => {
    e.preventDefault();
    if (sending || sent.current || !validate()) return;
    if (me && !me.authenticated) {   // guest: create the account first, then come back and confirm
      saveBookingDraft(f);
      navigate('/signup?next=' + encodeURIComponent('/book-survey?resume=1'));
      return;
    }
    setSending(true);
    try {
      const res = await api.submitEnquiry({
        ...f,
        name: f.name.trim(),
        phone: normalizePhone(f.phone),
        city: '',
        subsidy: subsidyShown,
        system_kw: est ? est.kw : '',
        estimate: est ? { kw: est.kw, cost: est.cost, subsidy: subsidyShown ? est.subsidy : 0, net_cost: total } : null
      });
      if (!res?.ok) {
        if (res?.field) setErrors({ [res.field]: res.error });
        throw new Error(res?.error || 'Request failed');
      }
      sent.current = true;
      saveState(f.state);
      clearQuotePrefill();
      clearBookingDraft();
      setDone({ ...res, phone: normalizePhone(f.phone) });
      toast('Survey request received. We’ll call you to confirm the booking.');
    } catch (err) {
      toast(err.message || 'We couldn’t send your request. Please call +91 79 4000 5000.', 'error');
    } finally {
      setSending(false);
    }
  };

  const err = (k) => errors[k] && <span className="field-error" role="alert">{errors[k]}</span>;

  return (
    <>
      <section className="page-head wrap">
        <span className="eyebrow">Free roof survey</span>
        <h1 className="headline">Book your free roof survey.</h1>
        <p className="lead">
          A technician measures your roof, checks shade and the right capacity, then prepares your exact quote.
          Pick a day and time; our team calls you to confirm the booking.
          {draft ? ' Welcome! Your details are filled in: check them and press the button to book.' : prefill ? ' We’ve filled in what you entered on the savings page.' : ''}
        </p>
      </section>

      <section className="wrap wrap--narrow" style={{ paddingBottom: 'clamp(72px, 10vw, 120px)' }}>
        <div className="card card--alt">
          {done ? (
            <EnquirySuccess result={done} onReset={() => { sent.current = false; setDone(null); setF(blank(f.state)); }} />
          ) : (
            <form className="form" onSubmit={submit} noValidate>
              {prefill && (
                <div className="prefill-note">
                  From your savings estimate: <strong>{prefill.kw} kW</strong> for about {num(prefill.units)} units a month.{' '}
                  <Link to="/estimate" className="link">Change</Link>
                </div>
              )}

              <div className="field">
                <span className="label">System type</span>
                <div>
                  <Tabs label="System type" value={f.system_type} onChange={(v) => put('system_type', v)}
                        items={Object.entries(TYPES).map(([value, t]) => ({ value, label: t.label }))} />
                </div>
                <span className="form-hint">{TYPES[f.system_type].help}</span>
              </div>

              <div className="field">
                <span className="label">When should the technician visit?</span>
                <div className="form-row">
                  <div className="field">
                    <label className="label" htmlFor="q-day">Preferred day</label>
                    <input id="q-day" className="input" type="date" min={dayOffset(1)} max={dayOffset(30)} value={f.preferred_date}
                           onChange={set('preferred_date')} aria-invalid={!!errors.preferred_date} />
                    {err('preferred_date')}
                  </div>
                  <div className="field">
                    <span className="label" id="q-slot-label">Time slot</span>
                    <div className="choices choices--3" role="radiogroup" aria-labelledby="q-slot-label">
                      {SLOTS.map((sl) => (
                        <button key={sl.value} type="button" role="radio" aria-checked={f.preferred_slot === sl.value}
                                className={`choice${f.preferred_slot === sl.value ? ' is-active' : ''}`}
                                onClick={() => { put('preferred_slot', sl.value); setErrors((x) => ({ ...x, preferred_slot: '' })); }}>
                          <div className="choice__main">{sl.label}</div>
                          <div className="choice__sub">{sl.sub}</div>
                        </button>
                      ))}
                    </div>
                    {err('preferred_slot')}
                  </div>
                </div>
                <span className="form-hint">This is your preference: we’ll call to confirm it, or agree another time with you.</span>
              </div>

              <div className="form-row">
                <div className="field">
                  <label className="label" htmlFor="q-bill">Monthly electricity bill (₹) <span className="form-hint">(optional)</span></label>
                  <input id="q-bill" className="input" type="number" min="0" inputMode="numeric" value={f.monthly_bill}
                         onChange={set('monthly_bill')} aria-invalid={!!errors.monthly_bill} />
                  {err('monthly_bill') || <span className="form-hint">Your usual monthly bill, not the yearly total.</span>}
                </div>
                <div className="field">
                  <label className="label" htmlFor="q-roof">Usable roof area (sq ft) <span className="form-hint">(optional)</span></label>
                  <input id="q-roof" className="input" type="number" min="0" inputMode="numeric" value={f.roof_area}
                         onChange={set('roof_area')} aria-invalid={!!errors.roof_area} />
                  {err('roof_area') || (
                    <span className="form-hint">Open roof that gets sun most of the day, leaving out water tanks and stairs. Not sure? Leave it empty: we measure it at the free survey.</span>
                  )}
                </div>
              </div>

              <div style={{ borderTop: '1px solid var(--line)', paddingTop: 20 }} className="form-row">
                <div className="field">
                  <label className="label" htmlFor="q-name">Full name</label>
                  <input id="q-name" className="input" required autoComplete="name" value={f.name} onChange={set('name')} aria-invalid={!!errors.name}
                         readOnly={locked.name} aria-readonly={locked.name || undefined} />
                  {err('name') || (locked.name && <span className="form-hint">From your account. Change it in <Link to="/account">My account</Link>.</span>)}
                </div>
                <div className="field">
                  <label className="label" htmlFor="q-phone">Mobile number</label>
                  <input id="q-phone" className="input" type="tel" required inputMode="tel" autoComplete="tel" placeholder="+91"
                         value={f.phone} onChange={set('phone')} aria-invalid={!!errors.phone} readOnly={locked.phone} aria-readonly={locked.phone || undefined} />
                  {err('phone') || <span className="form-hint">{locked.phone ? 'From your account. ' : ''}We call this number to book your survey.</span>}
                </div>
                <div className="field">
                  <label className="label" htmlFor="q-email">Email <span className="form-hint">(optional)</span></label>
                  <input id="q-email" className="input" type="email" autoComplete="email" value={f.email} onChange={set('email')} aria-invalid={!!errors.email}
                         readOnly={locked.email} aria-readonly={locked.email || undefined} />
                  {err('email') || (locked.email && <span className="form-hint">From your account.</span>)}
                </div>
                <div className="field">
                  <label className="label" htmlFor="q-state">State</label>
                  <select id="q-state" className="select" value={f.state} onChange={set('state')}>
                    <option value="">Select your state</option>
                    {(table?.states || []).map((s) => <option key={s.name} value={s.name}>{s.name}</option>)}
                  </select>
                  {err('state')}
                </div>
                <div className="field field--full">
                  <label className="label" htmlFor="q-street">Address <span className="form-hint">(optional)</span></label>
                  <input id="q-street" className="input" autoComplete="street-address" value={f.street} onChange={set('street')} />
                  <span className="form-hint">The property to survey. For another property, enter its address here.</span>
                </div>
                <div className="field field--full">
                  <label className="label" htmlFor="q-notes">Anything else? <span className="form-hint">(optional)</span></label>
                  <textarea id="q-notes" className="textarea" rows={2} value={f.notes} onChange={set('notes')}
                            placeholder="Questions, a preferred date, power cuts, appliances you want to run (for Off-Grid)…" />
                </div>
              </div>

              {!offGrid && (
                <div className="switch-row">
                  <Switch checked={f.subsidy} onChange={(v) => put('subsidy', v)}>Apply for the PM Surya Ghar subsidy (we file it for you)</Switch>
                  <InfoTip label="About the PM Surya Ghar subsidy">
                    <strong>PM Surya Ghar: Muft Bijli Yojana</strong> is the Government of India scheme for rooftop solar on homes.
                    It pays a one-time subsidy for grid-connected systems: ₹30,000/kW for the first 2 kW and ₹18,000 for the 3rd kW
                    (up to ₹78,000; 10% more in special-category states). It is paid into your bank account after the system is
                    installed and inspected. We submit the application on the national portal for you.
                    <a href="https://pmsuryaghar.gov.in/" target="_blank" rel="noopener noreferrer" className="infotip__link">
                      Official website: pmsuryaghar.gov.in ↗
                    </a>
                  </InfoTip>
                </div>
              )}

              <div className="quote-total" aria-live="polite">
                {est ? (
                  <>
                    <div className="rows tabular">
                      <div><span className="muted">{est.kw} kW {TYPES[f.system_type].label} system{offGrid ? ' (with batteries)' : ''}</span><span>{inr(est.cost)}</span></div>
                      {subsidyShown && <div><span className="muted">PM Surya Ghar subsidy · {f.state || 'standard rate'}</span><span className="good">− {inr(est.subsidy)}</span></div>}
                      {offGrid && <div><span className="muted">Subsidy</span><span className="muted">Not available for Off-Grid</span></div>}
                    </div>
                    <div className="quote-total__sum">
                      <span>Estimated total</span>
                      <strong className="tabular">{inr(total)}</strong>
                    </div>
                    <p className="form-hint">
                      Estimate only{prefill?.custom ? `, using your price of ${inr(prefill.custom.costPerKw)}/kW` : ''}. Your exact quote comes after the survey.
                      {subsidyShown && ' The subsidy is paid by the government to your bank account after installation.'}
                    </p>
                  </>
                ) : (
                  <p className="form-hint">Add your monthly bill to see an estimated total, or leave it empty and our advisor will recommend a size.</p>
                )}
              </div>

              <button type="submit" className="btn btn--primary btn--block" disabled={sending}>
                {sending ? 'Sending…' : 'Book my free survey'}
              </button>
              <p className="form-hint center">No payment now. The survey is free and there’s no obligation to buy.</p>
            </form>
          )}
        </div>
      </section>
    </>
  );
}

