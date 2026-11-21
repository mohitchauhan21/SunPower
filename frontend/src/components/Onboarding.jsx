import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../auth.jsx';

// One-time welcome tour. Visitors: once per browser. Signed-in people: once per
// account (stored on the server, so it doesn't come back on another device).
const I = {
  sun: 'M12 3v2M12 19v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M3 12h2M19 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4M12 8a4 4 0 100 8 4 4 0 000-8z',
  chart: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  home: 'M3 11l9-7 9 7M5 10v10h14V10',
  shield: 'M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z',
  list: 'M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01',
  grid: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
  tool: 'M14.7 6.3a4 4 0 00-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 005.4-5.4l-2.5 2.5-2.5-2.5z',
  truck: 'M3 7h11v9H3zM14 10h4l3 3v3h-7M7 19a2 2 0 100-4 2 2 0 000 4zM17 19a2 2 0 100-4 2 2 0 000 4z',
  key: 'M15 7a4 4 0 11-3.9 4.9L3 20v-3h3v-3h3l1.1-1.1A4 4 0 0115 7z',
  card: 'M3 6h18v12H3zM3 10h18',
  phone: 'M5 4h4l2 5-3 2a11 11 0 005 5l2-3 5 2v4a2 2 0 01-2 2A16 16 0 013 6a2 2 0 012-2'
};

const TOURS = {
  visitor: [
    { icon: I.sun, title: 'Welcome to SunPower', text: 'Rooftop solar for your home, done for you: survey, installation, government subsidy and service, all by one team.' },
    { icon: I.chart, title: 'See what you’d save', text: 'Enter your monthly bill or units. You get the right system size, savings, subsidy and payback in seconds.', to: '/estimate', cta: 'Try the estimate' },
    { icon: I.home, title: 'Book a free roof survey', text: 'An advisor calls you within two hours, an engineer checks your roof, and you get a fixed price. No obligation.' },
    { icon: I.shield, title: 'Follow everything online', text: 'Create an account to track your installation, see every warranty, and get repairs quickly.', to: '/signup', cta: 'Create an account' }
  ],
  customer: [
    { icon: I.sun, title: 'Your solar, in one place', text: 'This is your account. Everything about your system lives here.' },
    { icon: I.list, title: 'Track your installation', text: 'The System tab shows each step: confirmed, advance paid, kit dispatched, crew on site and handed over.' },
    { icon: I.card, title: 'Accept quotes and pay online', text: 'When a quotation is ready, review it, accept it and pay the advance here. You can also add another system anytime.' },
    { icon: I.tool, title: 'Something not working?', text: 'Report it from the Service tab. Warranty repairs are free, and you confirm the fix before we close it.' },
    { icon: I.key, title: 'Keep your recovery code safe', text: 'Your 4-digit recovery code lets you reset a forgotten password. You can change it in Profile.' }
  ],
  director: [
    { icon: I.sun, title: 'Start every day on Today', text: 'Today shows only what needs you now: sales to move forward, money to collect, work on site, warehouse and service.' },
    { icon: I.grid, title: 'Five groups, that’s all', text: 'Sales, Operations, Service and Business hold everything else. Pages inside a group are tabs at the top.' },
    { icon: I.chart, title: 'Trends live in Insights', text: 'Week, month and year results, profit by job and the printable report are under Business → Insights.' },
    { icon: I.key, title: 'Set up your team', text: 'Business → Settings: staff accounts, prices, payments, email and Google sign-in.' }
  ],
  sales: [
    { icon: I.sun, title: 'Your day starts on Today', text: 'New enquiries to call, surveys to approve, quotes to send and money to collect, in that order.' },
    { icon: I.phone, title: 'Call within two hours', text: 'Open the enquiry, screen the roof, bill and grid, then book a technician for the survey.' },
    { icon: I.list, title: 'Approve, quote, confirm', text: 'Approve the visited survey, prepare the quote in one click, send it, and record the advance when it’s paid.' }
  ],
  warehouse: [
    { icon: I.sun, title: 'Your day starts on Today', text: 'Kits ready to dispatch, kits waiting for the advance, and items to reorder.' },
    { icon: I.truck, title: 'Dispatch with serials', text: 'A kit can leave only after the advance. Scanning each serial starts that item’s warranty automatically.' },
    { icon: I.grid, title: 'Keep stock healthy', text: 'Operations → Stock shows what’s low. Use Receive when new stock arrives.' }
  ],
  technician: [
    { icon: I.sun, title: 'Your jobs are on Today', text: 'Installations, roof surveys and repairs assigned to you, with the time, address and a call button.' },
    { icon: I.tool, title: 'On the roof', text: 'Tap Start job, tick the checklist (it saves as you go), add photos, enter the kW and the reading.' },
    { icon: I.shield, title: 'Hand over', text: 'The homeowner signs on your screen, then Finish & hand over. The certificate goes to them automatically.' }
  ],
  support: [
    { icon: I.sun, title: 'Your day starts on Today', text: 'New requests, repairs in progress and customers who need to confirm a fix.' },
    { icon: I.phone, title: 'Find the customer fast', text: 'Search by phone, name or serial number. The warranty is checked for you.' },
    { icon: I.tool, title: 'Diagnose, repair, confirm', text: 'Use AI diagnose for likely causes and safe steps, assign a technician, and ask the customer to confirm.' }
  ]
};

const AUTH_PAGES = ['/login', '/signup', '/forgot-password', '/reset-password', '/logout'];
const LOCAL_KEY = 'sp_tour_done';
const seenLocally = (key) => { try { return localStorage.getItem(`${LOCAL_KEY}:${key}`) === '1'; } catch { return false; } };
const markLocally = (key) => { try { localStorage.setItem(`${LOCAL_KEY}:${key}`, '1'); } catch { /* private mode */ } };

export default function Onboarding() {
  const { me, refresh } = useAuth();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const primary = useRef(null);

  const audience = !me ? null : me.authenticated ? (TOURS[me.role] ? me.role : null) : 'visitor';
  const key = me?.authenticated ? `user${me.id}` : 'visitor';
  const steps = audience ? TOURS[audience] : [];

  useEffect(() => {
    if (!audience || AUTH_PAGES.some((p) => pathname.startsWith(p)) || pathname.startsWith('/print')) return;
    if (seenLocally(key)) return;
    if (me.authenticated && me.onboarded) return;
    const t = setTimeout(() => { setStep(0); setOpen(true); }, 700);
    return () => clearTimeout(t);
  }, [audience, key, me, pathname]);

  const finish = useCallback(async (to) => {
    setOpen(false);
    markLocally(key);
    if (me?.authenticated) { await api.onboarded().catch(() => {}); refresh(); }
    if (to) navigate(to);
  }, [key, me, refresh, navigate]);

  useEffect(() => {
    if (!open) return;
    primary.current?.focus();
    const onKey = (e) => {
      if (e.key === 'Escape') finish();
      if (e.key === 'ArrowRight') setStep((s) => Math.min(s + 1, steps.length - 1));
      if (e.key === 'ArrowLeft') setStep((s) => Math.max(s - 1, 0));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, finish, steps.length, step]);

  if (!open || !steps.length) return null;
  const s = steps[step];
  const last = step === steps.length - 1;
  return (
    <div className="tour" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      <div className="tour__backdrop" onClick={() => finish()} />
      <div className="tour__card">
        <button type="button" className="tour__skip" onClick={() => finish()}>Skip</button>
        <div className="tour__body" key={step}>
          <span className="tour__icon" aria-hidden="true">
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d={s.icon} /></svg>
          </span>
          <span className="tour__step">Step {step + 1} of {steps.length}</span>
          <h2 id="tour-title">{s.title}</h2>
          <p>{s.text}</p>
        </div>
        <div className="tour__dots" aria-hidden="true">
          {steps.map((_, i) => <span key={i} className={i === step ? 'is-on' : i < step ? 'is-done' : ''} />)}
        </div>
        <div className="tour__actions">
          {step > 0 ? <button type="button" className="btn btn--secondary btn--sm" onClick={() => setStep(step - 1)}>Back</button> : <span />}
          <div className="tour__right">
            {s.to && <button type="button" className="btn btn--secondary btn--sm" onClick={() => finish(s.to)}>{s.cta}</button>}
            <button ref={primary} type="button" className="btn btn--primary btn--sm" onClick={() => (last ? finish() : setStep(step + 1))}>
              {last ? 'Get started' : 'Next'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
