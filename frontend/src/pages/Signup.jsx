import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { goHome, useAuth } from '../auth.jsx';
import { codeProblem, passwordProblem } from '../password.js';
import { CodeField, ConfirmField, PasswordField } from '../components/ui/Secret.jsx';
import GoogleButton from '../components/GoogleButton.jsx';

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export default function Signup() {
  const { me, refresh } = useAuth();
  const navigate = useNavigate();
  const [f, setF] = useState({ name: '', email: '', phone: '', password: '', confirm: '', recovery_code: '' });
  const [errors, setErrors] = useState({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState('');

  useEffect(() => { if (me?.authenticated) goHome(navigate, me.home); }, [me, navigate]);

  const set = (k) => (v) => { setF((s) => ({ ...s, [k]: v })); setErrors((s) => ({ ...s, [k]: '' })); };

  const validate = () => {
    const e = {};
    if (!f.name.trim()) e.name = 'Please enter your name.';
    if (!EMAIL_RE.test(f.email.trim())) e.email = 'Please enter a valid email address.';
    if (passwordProblem(f.password)) e.password = passwordProblem(f.password);
    if (f.confirm !== f.password) e.confirm = 'The two passwords don’t match.';
    if (codeProblem(f.recovery_code)) e.recovery_code = codeProblem(f.recovery_code);
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
        <div className="auth__card fade-up">
          <h1 className="headline">Check your email.</h1>
          <p className="lead">{sent}</p>
          <p className="muted small" style={{ marginBottom: 24 }}>The link works once and expires in 24 hours. Didn’t get it? Check spam, or ask for a new one.</p>
          <Link to="/login" className="btn btn--primary btn--block">Back to sign in</Link>
        </div>
      </section>
    );
  }

  return (
    <section className="wrap auth">
      <div className="auth__card fade-up">
        <h1 className="headline">Create account</h1>
        <p className="lead">Follow your installation, warranties and repairs in one place.</p>

        <GoogleButton mode="signup" portal="customer" onError={setError} />

        <form className="form" onSubmit={submit} noValidate>
          {error && <div className="form-error" role="alert">{error}</div>}
          <div className="field">
            <label className="label" htmlFor="s-name">Full name</label>
            <input id="s-name" className="input" autoComplete="name" value={f.name} onChange={(e) => set('name')(e.target.value)} aria-invalid={!!errors.name} />
            {errors.name && <span className="field-error">{errors.name}</span>}
          </div>
          <div className="field">
            <label className="label" htmlFor="s-email">Email</label>
            <input id="s-email" className="input" type="email" autoComplete="email" value={f.email} onChange={(e) => set('email')(e.target.value)} aria-invalid={!!errors.email} />
            {errors.email && <span className="field-error">{errors.email}</span>}
          </div>
          <div className="field">
            <label className="label" htmlFor="s-phone">Phone <span className="form-hint">(optional)</span></label>
            <input id="s-phone" className="input" type="tel" autoComplete="tel" value={f.phone} onChange={(e) => set('phone')(e.target.value)} />
          </div>
          <PasswordField value={f.password} onChange={set('password')} error={errors.password} showRules />
          <ConfirmField value={f.confirm} onChange={set('confirm')} against={f.password} error={errors.confirm} />
          <div className="auth__box">
            <CodeField label="Choose a 4-digit recovery code" value={f.recovery_code} onChange={set('recovery_code')} error={errors.recovery_code}
                       hint="If you ever forget your password, this code lets you set a new one. Keep it somewhere safe, and avoid easy ones like 1234." />
          </div>
          <button className="btn btn--primary btn--block" disabled={busy}>{busy ? 'Creating account…' : 'Create account'}</button>
          <p className="form-hint center">For homeowners and businesses. SunPower staff accounts are set up by the office.</p>
        </form>
        <p className="auth__foot muted">Already have an account? <Link to="/login" className="auth__small">Sign in</Link></p>
      </div>
    </section>
  );
}
