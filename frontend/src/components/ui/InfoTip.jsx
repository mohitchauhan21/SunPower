import { useEffect, useId, useRef, useState } from 'react';

/* Small "i" button: shows a short explanation on hover, keyboard focus or tap.
   The popup stays open while the pointer is over it, so links inside are clickable. */
export default function InfoTip({ label = 'More information', children }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const timer = useRef(null);

  const show = () => { clearTimeout(timer.current); setOpen(true); };
  const hide = () => { timer.current = setTimeout(() => setOpen(false), 150); };

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === 'Escape' && setOpen(false);
    const onDown = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false);
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onDown);
    return () => { document.removeEventListener('keydown', onKey); document.removeEventListener('pointerdown', onDown); };
  }, [open]);

  return (
    <span className="infotip" ref={ref} onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}>
      <button type="button" className="infotip__btn" aria-label={label} aria-expanded={open} aria-describedby={open ? id : undefined}
              onClick={() => setOpen((o) => !o)}>i</button>
      {open && <span id={id} role="tooltip" className="infotip__pop">{children}</span>}
    </span>
  );
}
