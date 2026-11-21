import { useRef, useState } from 'react';

/* Slider that stretches past its ends and springs back (Arc UI "Elastic slider" pattern). */
export default function ElasticSlider({ min, max, step = 1, value, onChange, format = (v) => v, label }) {
  const ref = useRef(null);
  const dragging = useRef(false);
  const [drag, setDrag] = useState(false);
  const [stretch, setStretch] = useState(0); // px past an end; negative = left

  const clampStep = (v) => Math.min(max, Math.max(min, Math.round(v / step) * step));
  const pct = ((Math.min(max, Math.max(min, value)) - min) / (max - min)) * 100;

  const update = (clientX) => {
    const r = ref.current.getBoundingClientRect();
    const x = clientX - r.left;
    const over = x < 0 ? x : x > r.width ? x - r.width : 0;
    setStretch(Math.sign(over) * Math.sqrt(Math.abs(over)) * 2.2);
    const next = clampStep(min + (Math.min(Math.max(x, 0), r.width) / r.width) * (max - min));
    if (next !== value) onChange(next);
  };

  const onDown = (e) => {
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* synthetic pointer */ }
    dragging.current = true;
    setDrag(true);
    update(e.clientX);
  };
  const onMove = (e) => dragging.current && update(e.clientX);
  const onUp = () => {
    dragging.current = false;
    setDrag(false);
    setStretch(0);
  };
  const onKey = (e) => {
    const map = { ArrowRight: step, ArrowUp: step, ArrowLeft: -step, ArrowDown: -step, PageUp: step * 10, PageDown: -step * 10 };
    if (e.key in map) { e.preventDefault(); onChange(clampStep(value + map[e.key])); }
    if (e.key === 'Home') onChange(min);
    if (e.key === 'End') onChange(max);
  };

  const scale = 1 + Math.abs(stretch) / 400;
  const origin = stretch < 0 ? 'right' : 'left';

  return (
    <div
      className={`eslider${drag ? ' is-drag' : ''}`}
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerCancel={onUp}
    >
      <div
        ref={ref}
        className="eslider__track"
        style={{ transform: `translateX(${stretch * 0.35}px) scaleX(${scale})`, transformOrigin: origin }}
      >
        <div className="eslider__fill" style={{ width: `${pct}%` }} />
        <div
          className="eslider__thumb"
          style={{ left: `${pct}%` }}
          role="slider"
          tabIndex={0}
          aria-label={label}
          aria-valuemin={min}
          aria-valuemax={max}
          aria-valuenow={value}
          aria-valuetext={String(format(value))}
          onKeyDown={onKey}
        />
      </div>
      <div className="eslider__scale"><span>{format(min)}</span><span>{format(max)}</span></div>
    </div>
  );
}
