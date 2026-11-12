import { Link } from "react-router-dom";

export function BrandMark({ className = "" }) {
  return (
    <svg className={`brand-mark-svg ${className}`} viewBox="0 0 40 40" aria-hidden="true" focusable="false">
      <rect x="1" y="1" width="38" height="38" rx="12" fill="currentColor" />
      <circle cx="18" cy="18" r="10" fill="none" stroke="white" strokeWidth="2.7" />
      <path d="m25.2 25.2 8 8v-8" fill="none" stroke="white" strokeWidth="2.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Brand({ compact = false, to = "/", className = "" }) {
  return (
    <Link to={to} className={`brand ${className}`.trim()} aria-label="QueMe home">
      <BrandMark />
      {!compact && <span className="brand-word">QueMe</span>}
    </Link>
  );
}
