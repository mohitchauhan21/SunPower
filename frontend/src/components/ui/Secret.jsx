import { useId, useRef, useState } from 'react';
import { PASSWORD_RULES } from '../../password.js';

/** Password input with show/hide and (optionally) the live list of rules. */
export function PasswordField({ label = 'Password', value, onChange, error, showRules = false, autoComplete = 'new-password', id: givenId }) {
  const auto = useId();
  const id = givenId || auto;
  const [show, setShow] = useState(false);
  const passed = PASSWORD_RULES.filter((r) => r.test(value || '')).length;
  return (
    <div className="field">
      <label className="label" htmlFor={id}>{label}</label>
      <div className="secret">
        <input id={id} className="input" type={show ? 'text' : 'password'} autoComplete={autoComplete} value={value}
               onChange={(e) => onChange(e.target.value)} aria-invalid={!!error} aria-describedby={`${id}-help`} />
        <button type="button" className="secret__toggle" onClick={() => setShow(!show)} aria-label={show ? 'Hide password' : 'Show password'}>
          {show ? 'Hide' : 'Show'}
        </button>
      </div>
      {showRules && (
        <>
          <div className="meter" aria-hidden="true"><span style={{ width: `${(passed / PASSWORD_RULES.length) * 100}%` }} className={`meter__bar meter__bar--${passed}`} /></div>
          <ul className="rules" id={`${id}-help`}>
            {PASSWORD_RULES.map((r) => {
              const ok = r.test(value || '');
              return <li key={r.key} className={ok ? 'is-ok' : ''}><span aria-hidden="true">{ok ? '✓' : '○'}</span>{r.label}</li>;
            })}
          </ul>
        </>
      )}
      {error && <span className="field-error" id={showRules ? undefined : `${id}-help`}>{error}</span>}
    </div>
  );
}

/** "Type it again" field with a live match indicator. */
export function ConfirmField({ value, onChange, against, error, label = 'Confirm password' }) {
  const id = useId();
  const matches = value && value === against;
  return (
    <div className="field">
      <label className="label" htmlFor={id}>{label}</label>
      <input id={id} className="input" type="password" autoComplete="new-password" value={value} onChange={(e) => onChange(e.target.value)}
             aria-invalid={!!error || (value && !matches)} aria-describedby={`${id}-help`} />
      <span id={`${id}-help`} className={error || (value && !matches) ? 'field-error' : 'form-hint'}>
        {error || (!value ? 'Type the same password again.' : matches ? '✓ Passwords match' : 'Passwords don’t match yet.')}
      </span>
    </div>
  );
}

/** Four single-digit boxes for the recovery code. */
export function CodeField({ label = 'Recovery code', value, onChange, error, hint }) {
  const refs = useRef([]);
  const id = useId();
  const digits = (value || '').padEnd(4, ' ').slice(0, 4).split('');
  const put = (i, d) => {
    const next = digits.map((x, k) => (k === i ? d : x)).join('').replace(/\s+$/, '');
    onChange(next.replace(/\s/g, ''));
  };
  const onKey = (i, e) => {
    if (e.key === 'Backspace' && !digits[i].trim() && i > 0) refs.current[i - 1]?.focus();
    if (e.key === 'ArrowLeft' && i > 0) refs.current[i - 1]?.focus();
    if (e.key === 'ArrowRight' && i < 3) refs.current[i + 1]?.focus();
  };
  const onInput = (i, e) => {
    const v = e.target.value.replace(/\D/g, '');
    if (v.length > 1) { onChange(v.slice(0, 4)); refs.current[Math.min(v.length, 4) - 1]?.focus(); return; }
    put(i, v || ' ');
    if (v && i < 3) refs.current[i + 1]?.focus();
  };
  return (
    <div className="field">
      <span className="label" id={id}>{label}</span>
      <div className="code" role="group" aria-labelledby={id}>
        {digits.map((d, i) => (
          <input key={i} ref={(el) => (refs.current[i] = el)} className="code__box" inputMode="numeric" autoComplete="off"
                 maxLength={4} value={d.trim()} aria-label={`Digit ${i + 1}`} aria-invalid={!!error}
                 onChange={(e) => onInput(i, e)} onKeyDown={(e) => onKey(i, e)} onFocus={(e) => e.target.select()} />
        ))}
      </div>
      {error ? <span className="field-error">{error}</span> : hint && <span className="form-hint">{hint}</span>}
    </div>
  );
}
