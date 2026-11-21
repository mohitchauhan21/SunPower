import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api.js';
import { codeProblem, passwordProblem } from '../password.js';
import { CodeField, ConfirmField, PasswordField } from '../components/ui/Secret.jsx';

/** Emailed link: invited staff and customers choose their first password here
 *  (and a recovery code if they don't have one yet); others reset a forgotten one. */
export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get('token') || '';
  const welcome = params.get('welcome') === '1';
  const [state, setState] = useState('checking'); // checking | ready | invalid | done
  const [name, setName] = useState('');
  const [needsCode, setNeedsCode] = useState(false);
  const [f, setF] = useState({ password: '', confirm: '', code: '' });
  const [errors, setErrors] = useState({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const set = (k) => (v) => { setF((s) => ({ ...s, [k]: v })); setErrors((s) => ({ ...s, [k]: '' })); };

  useEffect(() => {
    if (!token) { setState('invalid'); return; }
    api.checkReset(token)
      .then((r) => { if (r?.ok) { setName(r.name); setNeedsCode(!!r.needs_code); setState('ready'); } else setState('invalid'); })
      .catch(() => setState('invalid'));
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    const errs = {};
    if (passwordProblem(f.password)) errs.password = passwordProblem(f.password);
    if (f.confirm !== f.password) errs.confirm = 'The two passwords don’t match.';
    if (needsCode && codeProblem(f.code)) errs.code = codeProblem(f.code);
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      const r = await api.confirmReset({ token, password: f.password, confirm: f.confirm, ...(needsCode ? { code: f.code } : {}) });
      if (!r?.ok) {
        if (r?.field) setErrors({ [r.field]: r.error }); else setError(r?.error || 'This link has expired.');
        return;
      }
      setState('done');
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  };

  return (
    <section className="wrap auth">
      <div className="auth__card fade-up" key={state}>
        {state === 'checking' && <p className="empty">Checking your link…</p>}
        {state === 'invalid' && (
          <>
            <h1 className="headline">Link expired.</h1>
            <p className="lead">This link is invalid or has already been used.</p>
            <Link to="/forgot-password" className="btn btn--primary btn--block">Reset my password</Link>
          </>
        )}
        {state === 'done' && (
          <>
            <h1 className="headline">All set.</h1>
            <p className="lead">{welcome ? 'Your password is saved. Sign in to get started.' : 'Your password has been changed. Sign in with your new password.'}</p>
            <Link to="/login" className="btn btn--primary btn--block">Sign in</Link>
          </>
        )}
        {state === 'ready' && (
          <>
            <h1 className="headline">{welcome ? 'Welcome to SunPower.' : 'New password'}</h1>
            <p className="lead">{welcome ? `Choose a password for your account, ${name}.` : `for ${name}.`}</p>
            <form className="form" onSubmit={submit} noValidate>
              {error && <div className="form-error" role="alert">{error}</div>}
              <PasswordField label="New password" value={f.password} onChange={set('password')} error={errors.password} showRules />
              <ConfirmField value={f.confirm} onChange={set('confirm')} against={f.password} error={errors.confirm} />
              {needsCode && (
                <div className="auth__box">
                  <CodeField label="Choose a 4-digit recovery code" value={f.code} onChange={set('code')} error={errors.code}
                             hint="If you ever forget your password, this code lets you set a new one. Keep it safe." />
                </div>
              )}
              <button className="btn btn--primary btn--block" disabled={busy}>{busy ? 'Saving…' : welcome ? 'Save and continue' : 'Change password'}</button>
            </form>
          </>
        )}
      </div>
    </section>
  );
}
