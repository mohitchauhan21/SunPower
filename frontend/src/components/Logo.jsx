export default function Logo({ size = 22, word = true }) {
  return (
    <span className="logo">
      <svg width={size} height={size} viewBox="0 0 64 64" fill="none" aria-hidden="true">
        <circle cx="32" cy="32" r="13" fill="#F5A623" />
        <g stroke="#F5A623" strokeWidth="4" strokeLinecap="round">
          <path d="M32 4v7M32 53v7M4 32h7M53 32h7M12.2 12.2l5 5M46.8 46.8l5 5M12.2 51.8l5-5M46.8 17.2l5-5" />
        </g>
        <path d="M24 36h16l-3-8H27z" fill="#1D1D1F" />
      </svg>
      {word && <span>SunPower</span>}
    </span>
  );
}
