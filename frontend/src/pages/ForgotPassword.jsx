import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState('');
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const res = await api.requestReset(email.trim());
      if (!res?.ok) throw new Error(res?.error || 'Please try again.');
      setSent(res.message);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="wrap auth">
      <div className="auth__card">
        <h1 className="headline">Forgot password?</h1>
        {sent ? (
          <>
            <p className="lead">{sent}</p>
            <p className="muted">Check your inbox (and spam folder). The link works once and expires in 24 hours.</p>
            <Link to="/login" className="btn btn--primary btn--block">Back to sign in</Link>
          </>
        ) : (
          <>
            <p className="lead">Enter your email and we’ll send you a link to choose a new one.</p>
            <form className="form" onSubmit={submit}>
              {error && <div className="form-error" role="alert">{error}</div>}
              <div className="field">
                <label className="label" htmlFor="f-email">Email</label>
                <input id="f-email" className="input" type="email" required autoComplete="email"
                       value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              <button className="btn btn--primary btn--block" disabled={busy || !email}>
                {busy ? 'Sending…' : 'Send reset link'}
              </button>
            </form>
            <p className="auth__foot muted"><Link to="/login" className="auth__small">Back to sign in</Link></p>
          </>
        )}
      </div>
    </section>
  );
}
