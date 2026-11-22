import { useId } from 'react';

/* The SunPower mark: a sun rising over a solar panel.
   The sun and its rays share one warm gradient (gold at the top, deep orange below);
   the panel is a dark trapezoid in perspective with a white edge that cuts it out of the sun.
   The same drawing is inlined in index.html (preloader) and public/favicon.svg. */
export function LogoMark({ size = 24, className = '' }) {
  const id = useId().replace(/:/g, '');   // gradient ids must be unique: the logo appears several times per page
  const sun = `sun${id}`;
  const panel = `panel${id}`;
  return (
    <svg className={`logo__mark ${className}`} width={size} height={size} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id={sun} x1="32" y1="6" x2="32" y2="52" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#FFD45C" />
          <stop offset="0.55" stopColor="#F5A623" />
          <stop offset="1" stopColor="#E8740C" />
        </linearGradient>
        <linearGradient id={panel} x1="32" y1="40" x2="32" y2="58" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#3A3A3E" />
          <stop offset="1" stopColor="#111113" />
        </linearGradient>
      </defs>
      <g className="logo__rays" stroke={`url(#${sun})`} strokeWidth="4.5" strokeLinecap="round">
        <path d="M32 15V7" /><path d="M17.9 21.9l-5-5" /><path d="M46.1 21.9l5-5" /><path d="M12 36H5" /><path d="M52 36h7" />
      </g>
      <circle className="logo__sun" cx="32" cy="36" r="14" fill={`url(#${sun})`} />
      <path className="logo__panel" d="M14 40h36l6.5 17h-49z" fill={`url(#${panel})`} stroke="#fff" strokeWidth="3" strokeLinejoin="round" paintOrder="stroke" />
      <path className="logo__grid" d="M10.6 48.5h42.8M26.2 40.5l-1.6 16M37.8 40.5l1.6 16" stroke="#fff" strokeOpacity="0.38" strokeWidth="1.6" />
    </svg>
  );
}

export default function Logo({ size = 24, word = true }) {
  return (
    <span className="logo">
      <LogoMark size={size} />
      {word && <span className="logo__word"><span className="logo__sun-word">Sun</span>Power</span>}
    </span>
  );
}
