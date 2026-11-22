import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, fmtDate, inr } from '../api.js';
import { useToast } from '../components/ui/Toast.jsx';
import { ErrorBox, Loading, useLoad } from '../staff/ui.jsx';

function loadRazorpay() {
  if (window.Razorpay) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = 'https://checkout.razorpay.com/v1/checkout.js';
    s.onload = resolve;
    s.onerror = () => reject(new Error('The payment window could not be loaded.'));
    document.body.appendChild(s);
  });
}

/** Customer: review a quotation, accept it and pay the advance (or the balance). */
export default function QuoteReview() {
  const { id } = useParams();
  const toast = useToast();
  const { data: q, error, reload } = useLoad(() => api.myQuote(id), [id]);
  const [name, setName] = useState('');
  const [plan, setPlan] = useState('advance');
  const [payment, setPayment] = useState(null); // {payment_id, mode, amount, razorpay?}
  const [card, setCard] = useState('4111 1111 1111 1111');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  if (error) return <section className="wrap section"><ErrorBox error={error} onRetry={reload} /></section>;
  if (!q) return <section className="wrap section"><Loading /></section>;

  const startPay = async (fn) => {
    setErr('');
    setBusy(true);
    try {
      const r = await fn();
      if (!r?.ok) {
        if (r?.accepted) reload();   // the acceptance was saved; only the payment couldn't start
        throw new Error(r?.error || 'Please try again.');
      }
      if (r.confirmed) {   // payment step skipped for now: accepting confirms the order
        toast('Thank you! Your order is confirmed and your installation is being scheduled.');
        reload();
        return;
      }
      if (r.mode === 'razorpay') {
        await loadRazorpay();
        new window.Razorpay({
          key: r.razorpay.key, order_id: r.razorpay.order_id, amount: Math.round(r.amount * 100), currency: 'INR',
          name: r.razorpay.name, description: r.description,
          handler: async (resp) => {
            try {
              const v = await api.verifyRazorpay({ payment_id: r.payment_id, ...resp });
              if (v.ok) { toast('Payment received. Thank you!'); reload(); } else toast(v.error, 'error');
            } catch (ex) {
              toast(ex.message, 'error');
            }
          }
        }).open();
      } else {
        setPayment(r);
      }
    } catch (ex) { setErr(ex.message); } finally { setBusy(false); }
  };
  const accept = (e) => { e.preventDefault(); startPay(() => api.acceptQuote(q.id, name, plan)); };
  const payTest = async (e) => {
    e.preventDefault();
    setBusy(true);
    setErr('');
    try {
      const r = await api.confirmTestPayment(payment.payment_id, card);
      if (!r.ok) throw new Error(r.error);
      toast('Payment received. Your installation is being booked.');
      setPayment(null);
      reload();
    } catch (ex) { setErr(ex.message); } finally { setBusy(false); }
  };

  const balance = q.total - q.paid;
  return (
    <>
      <section className="page-head wrap">
        <span className="eyebrow">{q.quote_pending ? 'Your quotation' : 'Your order'} {q.name}</span>
        <h1 className="headline">{q.kw} kW rooftop solar</h1>
        <p className="lead">{q.system_type === 'off_grid' ? 'Off-Grid with battery backup' : 'On-Grid with net metering'} · {inr(q.total)} including GST
          {q.valid_until && q.quote_pending ? ` · valid until ${fmtDate(q.valid_until)}` : ''}</p>
      </section>
      <section className="wrap wrap--narrow stack" style={{ paddingBottom: 'clamp(72px, 10vw, 120px)' }}>
        <div className="card card--outline">
          <div className="table-scroll">
            <table className="table">
              <thead><tr><th>Item</th><th className="num">Qty</th><th className="num">Amount</th></tr></thead>
              <tbody>
                {q.lines.map((l, i) => <tr key={i}><td>{l.description}</td><td className="num">{l.qty}</td><td className="num">{inr(l.subtotal)}</td></tr>)}
                <tr className="tot"><td colSpan={2} className="num">GST</td><td className="num">{inr(q.tax)}</td></tr>
                <tr className="tot tot--grand"><td colSpan={2} className="num">Total</td><td className="num">{inr(q.total)}</td></tr>
              </tbody>
            </table>
          </div>
          {q.subsidy_expected > 0 && <p className="muted">After the PM Surya Ghar subsidy of <strong className="good">{inr(q.subsidy_expected)}</strong> (paid to you by the government), your cost is about <strong>{inr(q.total - q.subsidy_expected)}</strong>.</p>}
          {q.est_kwh_year && <p className="muted small">Estimated generation {Math.round(q.est_kwh_year).toLocaleString('en-IN')} kWh a year, saving about {inr(q.est_savings_year)} a year.</p>}
          {q.note && <p className="muted small">{q.note}</p>}
          <div className="actions actions--left"><a className="btn btn--secondary btn--sm" href={q.pdf_url} target="_blank" rel="noreferrer">Download PDF</a></div>
        </div>

        {err && <div className="form-error" role="alert">{err}</div>}

        {payment ? (
          <form className="card card--alt form" onSubmit={payTest}>
            <h3>Pay {inr(payment.amount)}</h3>
            <p className="form-hint">Test payment: no money moves. Use any card number; one ending in 0002 is declined.</p>
            <div className="field"><label className="label" htmlFor="card">Card number</label><input id="card" className="input input--mono" value={card} onChange={(e) => setCard(e.target.value)} /></div>
            <div className="actions actions--left">
              <button className="btn btn--primary" disabled={busy}>{busy ? 'Paying…' : `Pay ${inr(payment.amount)}`}</button>
              <button type="button" className="link link--btn" onClick={() => setPayment(null)}>Cancel</button>
            </div>
          </form>
        ) : q.quote_pending && !q.accepted_by ? (
          <form className="card card--alt form" onSubmit={accept}>
            <h3>Accept and choose how to pay</h3>
            <div className="plans" role="radiogroup" aria-label="Payment plan">
              <button type="button" role="radio" aria-checked={plan === 'advance'} className={`plan${plan === 'advance' ? ' is-active' : ''}`} onClick={() => setPlan('advance')}>
                <strong>Advance now, rest later</strong>
                <span className="plan__amt">{inr(q.advance_amount)} now</span>
                <span className="muted small">{q.advance_pct}% to book. The balance of {inr(q.total - q.advance_amount)} is due after installation, before we switch the system on.</span>
              </button>
              {q.full_amount && (
                <button type="button" role="radio" aria-checked={plan === 'full'} className={`plan${plan === 'full' ? ' is-active' : ''}`} onClick={() => setPlan('full')}>
                  <strong>Pay in full upfront</strong>
                  <span className="plan__amt">{inr(q.full_amount)}</span>
                  <span className="muted small">{q.full_discount_pct}% off ({inr(q.total - q.full_amount)} saved). Nothing more to pay later.</span>
                </button>
              )}
            </div>
            <div className="field"><label className="label" htmlFor="acc">Type your full name to accept</label><input id="acc" className="input" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" /></div>
            <button className="btn btn--primary" disabled={busy || name.trim().length < 2}>
              Accept &amp; pay {inr(plan === 'full' ? q.full_amount : q.advance_amount)}</button>
          </form>
        ) : q.advance_due > 0 ? (
          <div className="card card--alt">
            <h3>{q.accepted_by ? `Accepted by ${q.accepted_by}` : 'Advance due'}</h3>
            <p className="muted">{q.payment_plan === 'full' && q.full_amount
              ? `You chose to pay in full upfront: ${inr(q.full_amount)} (${q.full_discount_pct}% off).`
              : `Pay the advance of ${inr(q.advance_due)} to book your installation.`}</p>
            <div className="actions actions--left">
              <button className="btn btn--primary" disabled={busy} onClick={() => startPay(() => api.payOrder(q.id, q.payment_plan === 'full' && q.full_amount ? 'full' : 'advance'))}>
                Pay {inr(q.payment_plan === 'full' && q.full_amount ? q.full_amount : q.advance_due)}</button>
              {q.full_amount && q.payment_plan !== 'full' && <button className="btn btn--secondary" disabled={busy} onClick={() => startPay(() => api.payOrder(q.id, 'full'))}>Pay in full instead ({inr(q.full_amount)})</button>}
            </div>
          </div>
        ) : (
          <div className="card card--alt">
            <h3>{balance > 0.5 ? 'Advance paid. Thank you!' : 'Fully paid. Thank you!'}</h3>
            <p className="muted">Paid {inr(q.paid)} of {inr(q.total)}. {balance > 0.5 ? `Balance ${inr(balance)} is due after installation.` : ''}</p>
            <div className="actions actions--left">
              {balance > 0.5 && <button className="btn btn--primary btn--sm" disabled={busy} onClick={() => startPay(() => api.payOrder(q.id, 'balance'))}>Pay balance {inr(balance)}</button>}
              <Link to="/account" className="btn btn--secondary btn--sm">Track my installation</Link>
            </div>
          </div>
        )}
      </section>
    </>
  );
}
