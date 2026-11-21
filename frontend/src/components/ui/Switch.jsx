import { useId } from 'react';

/* iOS-style switch (Arc UI "Switch" pattern). */
export default function Switch({ checked, onChange, children }) {
  const id = useId();
  return (
    <div className="switch">
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        className="switch__track"
        onClick={() => onChange(!checked)}
      >
        <span className="switch__knob" />
      </button>
      <label htmlFor={id} className="switch__label">{children}</label>
    </div>
  );
}
