import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api.js';
import { goHome, useAuth } from '../auth.jsx';

// Pages a ?next= may send a user back to, by role
const STAFF = ['director', 'sales', 'warehouse', 'technician', 'support'];
const NEXT_ROLES = { '/app': STAFF, '/account': ['customer'] };

export const GoogleMark = () => (
  <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
    <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z"/>
    <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/>
    <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44z"/>
    <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z"/>
  </svg>
);

export default function Login() {
  const { me, refresh } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get('next');
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [providers, setProviders] = useState([]);

  useEffect(() => { api.providers().then((p) => setProviders(p || [])).catch(() => {}); }, []);

  // Already signed in? Go straight to your own screen.
  useEffect(() => {
    const area = next && next.startsWith('/') && !next.startsWith('//') ? '/' + next.split('/')[1] : null;
    if (me?.authenticated) goHome(navigate, area && NEXT_ROLES[area]?.includes(me.role) ? next : me.home);
  }, [me, next, navigate]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api.login(login.trim(), password);
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

        {providers.map((p) => (
          <a key={p.id} className="btn btn--secondary btn--block btn--google" href={p.url}>
            <GoogleMark /> Continue with Google
          </a>
        ))}
        {providers.length > 0 && <div className="auth__or"><span>or</span></div>}

        <form className="form" onSubmit={submit} noValidate>
          {error && <div className="form-error" role="alert">{error}</div>}
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
        <p className="auth__foot muted">New to SunPower? <Link to="/signup" className="auth__small">Create an account</Link></p>
      </div>
    </section>
  );
}
