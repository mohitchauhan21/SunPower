import { useLayoutEffect, useRef, useState } from 'react';

/* Segmented control with a sliding indicator (Arc UI "Tabs" pattern). */
export default function Tabs({ items, value, onChange, label = 'Options' }) {
  const refs = useRef([]);
  const [pos, setPos] = useState({ x: 0, w: 0 });
  const index = Math.max(0, items.findIndex((i) => i.value === value));

  useLayoutEffect(() => {
    const measure = () => {
      const el = refs.current[index];
      if (el) setPos({ x: el.offsetLeft, w: el.offsetWidth });
    };
    measure();
    // Re-measure when fonts load or the layout shifts, not only on window resize.
    const ro = new ResizeObserver(measure);
    refs.current.forEach((el) => el && ro.observe(el));
    document.fonts?.ready.then(measure);
    return () => ro.disconnect();
  }, [index, items.length]);

  const onKey = (e) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    const next = (index + (e.key === 'ArrowRight' ? 1 : items.length - 1)) % items.length;
    onChange(items[next].value);
    refs.current[next]?.focus();
  };

  return (
    <div className="tabs" role="tablist" aria-label={label} onKeyDown={onKey}>
      <span className="tabs__indicator" style={{ width: pos.w, transform: `translateX(${pos.x}px)` }} />
      {items.map((item, i) => (
        <button
          key={item.value}
          ref={(el) => (refs.current[i] = el)}
          type="button"
          role="tab"
          aria-selected={i === index}
          tabIndex={i === index ? 0 : -1}
          className={`tabs__tab${i === index ? ' is-active' : ''}`}
          onClick={() => onChange(item.value)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
