import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { passwordProblem } from '../password.js';
import { CodeField, ConfirmField, PasswordField } from '../components/ui/Secret.jsx';
import { useToast } from '../components/ui/Toast.jsx';

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** Forgot password: email + 4-digit recovery code + new password (twice).
 *  No code? An emailed reset link is the fallback. */
export default function ForgotPassword() {
  const navigate = useNavigate();
  const toast = useToast();
  const [mode, setMode] = useState('code');
  const [f, setF] = useState({ email: '', code: '', password: '', confirm: '' });
  const [errors, setErrors] = useState({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState('');
  const set = (k) => (v) => { setF((s) => ({ ...s, [k]: v })); setErrors((s) => ({ ...s, [k]: '' })); };

  const recover = async (e) => {
    e.preventDefault();
    setError('');
    const errs = {};
    if (!EMAIL_RE.test(f.email.trim())) errs.email = 'Please enter your email address.';
    if (!/^\d{4}$/.test(f.code)) errs.code = 'Enter your 4-digit recovery code.';
    if (passwordProblem(f.password)) errs.password = passwordProblem(f.password);
    if (f.confirm !== f.password) errs.confirm = 'The two passwords don’t match.';
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      const r = await api.recover({ ...f, email: f.email.trim() });
      if (!r?.ok) {
        if (r?.field) setErrors({ [r.field]: r.error }); else setError(r?.error || 'Please try again.');
        return;
      }
      toast('Password changed. Sign in with your new password.');
      navigate('/login', { replace: true });
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  };

  const emailLink = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const res = await api.requestReset(f.email.trim());
      if (!res?.ok) throw new Error(res?.error || 'Please try again.');
      setSent(res.message);
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  };

  return (
    <section className="wrap auth">
      <div className="auth__card fade-up" key={mode}>
        <h1 className="headline">Forgot password?</h1>
        {mode === 'code' ? (
          <>
            <p className="lead">Use the 4-digit recovery code you chose when you created your account.</p>
            <form className="form" onSubmit={recover} noValidate>
              {error && <div className="form-error" role="alert">{error}</div>}
              <div className="field">
                <label className="label" htmlFor="f-email">Email</label>
                <input id="f-email" className="input" type="email" autoComplete="email" value={f.email}
                       onChange={(e) => set('email')(e.target.value)} aria-invalid={!!errors.email} />
                {errors.email && <span className="field-error">{errors.email}</span>}
              </div>
              <CodeField value={f.code} onChange={set('code')} error={errors.code} />
              <PasswordField label="New password" value={f.password} onChange={set('password')} error={errors.password} showRules />
              <ConfirmField label="Confirm new password" value={f.confirm} onChange={set('confirm')} against={f.password} error={errors.confirm} />
              <button className="btn btn--primary btn--block" disabled={busy}>{busy ? 'Saving…' : 'Set new password'}</button>
            </form>
            <p className="auth__foot muted">Don’t have your code? <button type="button" className="link--btn auth__small" onClick={() => { setMode('email'); setError(''); }}>Email me a reset link</button></p>
          </>
        ) : sent ? (
          <>
            <p className="lead">{sent}</p>
            <p className="muted">Check your inbox (and spam). The link works once and expires in 24 hours.</p>
            <Link to="/login" className="btn btn--primary btn--block">Back to sign in</Link>
          </>
        ) : (
          <>
            <p className="lead">Enter your email and we’ll send you a link to choose a new password.</p>
            <form className="form" onSubmit={emailLink}>
              {error && <div className="form-error" role="alert">{error}</div>}
              <div className="field">
                <label className="label" htmlFor="f-email2">Email</label>
                <input id="f-email2" className="input" type="email" required autoComplete="email" value={f.email} onChange={(e) => set('email')(e.target.value)} />
              </div>
              <button className="btn btn--primary btn--block" disabled={busy || !f.email}>{busy ? 'Sending…' : 'Send reset link'}</button>
            </form>
            <p className="auth__foot muted"><button type="button" className="link--btn auth__small" onClick={() => setMode('code')}>Use my recovery code instead</button></p>
          </>
        )}
        <p className="auth__foot muted" style={{ marginTop: 8 }}><Link to="/login" className="auth__small">Back to sign in</Link></p>
      </div>
    </section>
  );
}
