import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../auth.jsx';
import { codeProblem, passwordProblem } from '../password.js';
import { CodeField, ConfirmField, PasswordField } from './ui/Secret.jsx';
import { useToast } from './ui/Toast.jsx';

/** Change password (typed twice, strong) and set/change the 4-digit recovery code.
 *  Used in the customer's Profile tab and the staff "My account" page. */
export default function SecuritySettings({ className = 'card card--alt form' }) {
  const toast = useToast();
  const { me, refresh } = useAuth();
  const [pw, setPw] = useState({ old: '', next: '', confirm: '' });
  const [pwErr, setPwErr] = useState({});
  const [code, setCode] = useState({ password: '', code: '' });
  const [codeErr, setCodeErr] = useState({});
  const [busy, setBusy] = useState('');

  const change = async (e) => {
    e.preventDefault();
    const errs = {};
    if (!pw.old) errs.old = 'Enter your current password.';
    if (passwordProblem(pw.next)) errs.next = passwordProblem(pw.next);
    if (pw.next !== pw.confirm) errs.confirm = 'The two new passwords don’t match.';
    setPwErr(errs);
    if (Object.keys(errs).length) return;
    setBusy('pw');
    try {
      const r = await api.myPassword(pw.old, pw.next, pw.confirm);
      if (!r?.ok) { setPwErr({ [r.field === 'new' ? 'next' : r.field || 'old']: r.error }); return; }
      toast('Password changed.');
      setPw({ old: '', next: '', confirm: '' });
    } catch (ex) { setPwErr({ old: ex.message }); } finally { setBusy(''); }
  };

  const saveCode = async (e) => {
    e.preventDefault();
    const errs = {};
    if (me?.has_password && !code.password) errs.password = 'Enter your current password.';
    if (codeProblem(code.code)) errs.code = codeProblem(code.code);
    setCodeErr(errs);
    if (Object.keys(errs).length) return;
    setBusy('code');
    try {
      const r = await api.setRecoveryCode(code.password, code.code);
      if (!r?.ok) { setCodeErr({ [r.field || 'code']: r.error }); return; }
      toast('Recovery code saved.');
      setCode({ password: '', code: '' });
      refresh();
    } catch (ex) { setCodeErr({ code: ex.message }); } finally { setBusy(''); }
  };

  return (
    <>
      <form className={className} onSubmit={change} noValidate>
        <h3>Change password</h3>
        <PasswordField label="Current password" value={pw.old} onChange={(v) => setPw({ ...pw, old: v })} error={pwErr.old} autoComplete="current-password" />
        <PasswordField label="New password" value={pw.next} onChange={(v) => setPw({ ...pw, next: v })} error={pwErr.next} showRules />
        <ConfirmField label="Confirm new password" value={pw.confirm} onChange={(v) => setPw({ ...pw, confirm: v })} against={pw.next} error={pwErr.confirm} />
        <button className="btn btn--primary" disabled={busy === 'pw'}>{busy === 'pw' ? 'Saving…' : 'Change password'}</button>
        <p className="form-hint">Forgot it? <Link to="/forgot-password" className="auth__small">Reset it with your recovery code</Link></p>
      </form>
      <form className={className} onSubmit={saveCode} noValidate>
        <h3>Recovery code {me?.has_recovery_code ? <span className="pill pill--ok">Set</span> : <span className="pill pill--warn">Not set</span>}</h3>
        <p className="muted small">A 4-digit code you’ll use to set a new password if you forget yours. {me?.has_recovery_code ? 'Saving a new one replaces the old code.' : 'Set one now so you never get locked out.'}</p>
        {me?.has_password && <PasswordField label="Current password" value={code.password} onChange={(v) => setCode({ ...code, password: v })} error={codeErr.password} autoComplete="current-password" />}
        <CodeField label="New recovery code" value={code.code} onChange={(v) => setCode({ ...code, code: v })} error={codeErr.code} />
        <button className="btn btn--secondary" disabled={busy === 'code'}>{busy === 'code' ? 'Saving…' : 'Save recovery code'}</button>
      </form>
    </>
  );
}
