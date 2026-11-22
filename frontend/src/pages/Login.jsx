import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api.js';
import { goHome, useAuth } from '../auth.jsx';
import GoogleButton from '../components/GoogleButton.jsx';
import Tabs from '../components/ui/Tabs.jsx';

const GOOGLE_ERRORS = {
  google: 'Google sign-in didn’t complete. Please try again or use your email.',
  google_off: 'Google sign-in is being set up. Please use your email for now.',
  inactive: 'This account is switched off. Please contact SunPower.'
};

// Pages a ?next= may send a user back to, by role
const STAFF = ['director', 'sales', 'warehouse', 'technician', 'support'];
const NEXT_ROLES = { '/app': STAFF, '/account': ['customer'] };

// Demo accounts from backend/app/seed.py (temporary, for testing). One click fills the form.
const DEMO_PASSWORD = 'Sunpower@2026';
const DEMO_LOGINS = [
  { label: 'Director', email: 'director@sunpower.demo', portal: 'team' },
  { label: 'Sales', email: 'sales@sunpower.demo', portal: 'team' },
  { label: 'Warehouse', email: 'warehouse@sunpower.demo', portal: 'team' },
  { label: 'Technician', email: 'tech01@sunpower.demo', portal: 'team' },
  { label: 'Service desk', email: 'support@sunpower.demo', portal: 'team' },
  { label: 'Customer', email: 'customer@sunpower.demo', portal: 'customer' }
];

export default function Login() {
  const { me, refresh } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get('next');
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  // Which door: customers vs the SunPower team. Staff links (?next=/app…) open on the team side.
  const [portal, setPortal] = useState(() => (next && next.startsWith('/app') ? 'team' : 'customer'));
  const googleError = GOOGLE_ERRORS[params.get('error')] || '';

  // Already signed in? Go straight to your own screen.
  useEffect(() => {
    const area = next && next.startsWith('/') && !next.startsWith('//') ? '/' + next.split(/[/?#]/)[1] : null;
    if (me?.authenticated) goHome(navigate, area && NEXT_ROLES[area]?.includes(me.role) ? next : me.home);
  }, [me, next, navigate]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api.login(login.trim(), password, portal);
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="wrap auth">
      <div className="auth__card">
        <h1 className="headline">Sign in</h1>
        <p className="lead">to your SunPower account.</p>

        <div className="portal-pick">
          <Tabs label="Sign in as" value={portal} onChange={(v) => { setPortal(v); setError(''); }}
                items={[{ value: 'customer', label: 'Customer' }, { value: 'team', label: 'SunPower team' }]} />
          <span className="form-hint">{portal === 'customer'
            ? 'Track your solar system, payments, warranties and repairs.'
            : 'Director, sales, warehouse, technicians and service desk. You open on the screens for your role.'}</span>
        </div>

        <GoogleButton portal={portal} onError={setError} />

        <form className="form" onSubmit={submit} noValidate>
          {(error || googleError) && <div className="form-error" role="alert">{error || googleError}</div>}
          <div className="field">
            <label className="label" htmlFor="l-login">Email</label>
            <input id="l-login" className="input" type="email" required autoComplete="username"
                   value={login} onChange={(e) => setLogin(e.target.value)} />
          </div>
          <div className="field">
            <div className="auth__row">
              <label className="label" htmlFor="l-pass">Password</label>
              <Link to="/forgot-password" className="auth__small">Forgot password?</Link>
            </div>
            <input id="l-pass" className="input" type="password" required autoComplete="current-password"
                   value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <button className="btn btn--primary btn--block" disabled={busy || !login || !password}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <div className="demo-logins">
          <span className="form-hint">Demo accounts: click one to fill in its email and password.</span>
          <div className="demo-logins__list">
            {DEMO_LOGINS.map((d) => (
              <button key={d.email} type="button"
                      className={`btn btn--secondary btn--sm${login === d.email ? ' is-active' : ''}`}
                      onClick={() => { setPortal(d.portal); setLogin(d.email); setPassword(DEMO_PASSWORD); setError(''); }}>
                {d.label}
              </button>
            ))}
          </div>
        </div>

        {portal === 'customer'
          ? <p className="auth__foot muted">New to SunPower? <Link to="/signup" className="auth__small">Create an account</Link></p>
          : <p className="auth__foot muted">Team accounts are created by the Director. Ask them if you can't sign in.</p>}
      </div>
    </section>
  );
}
