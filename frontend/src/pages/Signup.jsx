import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { goHome, useAuth } from '../auth.jsx';
import { GoogleMark } from './Login.jsx';

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export default function Signup() {
  const { me, refresh } = useAuth();
  const navigate = useNavigate();
  const [f, setF] = useState({ name: '', email: '', phone: '', password: '' });
  const [errors, setErrors] = useState({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState('');
  const [providers, setProviders] = useState([]);

  useEffect(() => { api.providers().then((p) => setProviders(p || [])).catch(() => {}); }, []);
  useEffect(() => { if (me?.authenticated) goHome(navigate, me.home); }, [me, navigate]);

  const set = (k) => (e) => { setF((s) => ({ ...s, [k]: e.target.value })); setErrors((s) => ({ ...s, [k]: '' })); };

  const validate = () => {
    const e = {};
    if (!f.name.trim()) e.name = 'Please enter your name.';
    if (!EMAIL_RE.test(f.email.trim())) e.email = 'Please enter a valid email address.';
    if (f.password.length < 8) e.password = 'Use at least 8 characters.';
    setErrors(e);
    return !Object.keys(e).length;
  };

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (!validate()) return;
    setBusy(true);
    try {
      const res = await api.signup({ ...f, name: f.name.trim(), email: f.email.trim() });
      if (!res?.ok) {
        if (res?.field) setErrors({ [res.field]: res.error });
        else setError(res?.error || 'Please try again.');
        return;
      }
      if (res.status === 'check_email') { setSent(res.message); return; }
      await refresh(); // signed in: the effect above moves to /account
    } catch (err) {
      setError(err.message || 'We couldn’t create your account. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  if (sent) {
    return (
      <section className="wrap auth">
        <div className="auth__card">
          <h1 className="headline">Check your email.</h1>
          <p className="lead">{sent}</p>
          <p className="muted small" style={{ marginBottom: 24 }}>The link works once and expires in 24 hours. Didn’t get it? Check spam, or ask for a new one.</p>
          <Link to="/login" className="btn btn--primary btn--block">Back to sign in</Link>
          <p className="auth__foot"><Link to="/forgot-password" className="auth__small">Send a new link</Link></p>
        </div>
      </section>
    );
  }

  return (
    <section className="wrap auth">
      <div className="auth__card">
        <h1 className="headline">Create account</h1>
        <p className="lead">Follow your installation, warranties and repairs in one place.</p>

        {providers.map((p) => (
          <a key={p.id} className="btn btn--secondary btn--block btn--google" href={p.url}>
            <GoogleMark /> Sign up with Google
          </a>
        ))}
        {providers.length > 0 && <div className="auth__or"><span>or</span></div>}

        <form className="form" onSubmit={submit} noValidate>
          {error && <div className="form-error" role="alert">{error}</div>}
          <div className="field">
            <label className="label" htmlFor="s-name">Full name</label>
            <input id="s-name" className="input" autoComplete="name" value={f.name} onChange={set('name')}
                   aria-invalid={!!errors.name} aria-describedby="s-name-e" />
            {errors.name && <span id="s-name-e" className="field-error">{errors.name}</span>}
          </div>
          <div className="field">
            <label className="label" htmlFor="s-email">Email</label>
            <input id="s-email" className="input" type="email" autoComplete="email" value={f.email} onChange={set('email')}
                   aria-invalid={!!errors.email} aria-describedby="s-email-e" />
            {errors.email && <span id="s-email-e" className="field-error">{errors.email}</span>}
          </div>
          <div className="field">
            <label className="label" htmlFor="s-phone">Phone <span className="form-hint">(optional)</span></label>
            <input id="s-phone" className="input" type="tel" autoComplete="tel" value={f.phone} onChange={set('phone')} />
          </div>
          <div className="field">
            <label className="label" htmlFor="s-pass">Password</label>
            <input id="s-pass" className="input" type="password" autoComplete="new-password" value={f.password} onChange={set('password')}
                   aria-invalid={!!errors.password} aria-describedby="s-pass-e" />
            {errors.password ? <span id="s-pass-e" className="field-error">{errors.password}</span>
              : <span className="form-hint">At least 8 characters.</span>}
          </div>
          <button className="btn btn--primary btn--block" disabled={busy}>{busy ? 'Creating account…' : 'Create account'}</button>
          <p className="form-hint center">For homeowners and businesses. SunPower staff accounts are set up by the office.</p>
        </form>
        <p className="auth__foot muted">Already have an account? <Link to="/login" className="auth__small">Sign in</Link></p>
      </div>
    </section>
  );
}
