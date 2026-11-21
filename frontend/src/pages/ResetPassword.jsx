import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api.js';

const strength = (p) => {
  let s = 0;
  if (p.length >= 8) s += 1;
  if (p.length >= 12) s += 1;
  if (/[A-Z]/.test(p) && /[a-z]/.test(p)) s += 1;
  if (/\d/.test(p) && /[^A-Za-z0-9]/.test(p)) s += 1;
  return [null, 'Weak', 'Fair', 'Good', 'Strong'][s] || (p ? 'Too short' : null);
};

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get('token') || '';
  const [state, setState] = useState('checking'); // checking | ready | invalid | done
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) { setState('invalid'); return; }
    api.checkReset(token)
      .then((r) => { if (r?.ok) { setName(r.name); setState('ready'); } else setState('invalid'); })
      .catch(() => setState('invalid'));
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (password.length < 8) return setError('Use at least 8 characters.');
    if (password !== confirm) return setError('The two passwords don’t match.');
    setBusy(true);
    try {
      const r = await api.confirmReset(token, password);
      if (!r?.ok) throw new Error(r?.error || 'This link has expired.');
      setState('done');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const label = strength(password);
  return (
    <section className="wrap auth">
      <div className="auth__card">
        {state === 'checking' && <p className="empty">Checking your link…</p>}
        {state === 'invalid' && (
          <>
            <h1 className="headline">Link expired.</h1>
            <p className="lead">This reset link is invalid or has already been used.</p>
            <Link to="/forgot-password" className="btn btn--primary btn--block">Send a new link</Link>
          </>
        )}
        {state === 'done' && (
          <>
            <h1 className="headline">All set.</h1>
            <p className="lead">Your password has been changed. Sign in with your new password.</p>
            <Link to="/login" className="btn btn--primary btn--block">Sign in</Link>
          </>
        )}
        {state === 'ready' && (
          <>
            <h1 className="headline">New password</h1>
            <p className="lead">for {name}.</p>
            <form className="form" onSubmit={submit}>
              {error && <div className="form-error" role="alert">{error}</div>}
              <div className="field">
                <label className="label" htmlFor="r-pass">New password</label>
                <input id="r-pass" className="input" type="password" required minLength={8} autoComplete="new-password"
                       value={password} onChange={(e) => setPassword(e.target.value)} />
                {label && <span className={`auth__strength auth__strength--${label.toLowerCase().replace(' ', '-')}`}>{label}</span>}
              </div>
              <div className="field">
                <label className="label" htmlFor="r-confirm">Confirm password</label>
                <input id="r-confirm" className="input" type="password" required autoComplete="new-password"
                       value={confirm} onChange={(e) => setConfirm(e.target.value)} />
              </div>
              <button className="btn btn--primary btn--block" disabled={busy}>{busy ? 'Saving…' : 'Change password'}</button>
            </form>
          </>
        )}
      </div>
    </section>
  );
}
