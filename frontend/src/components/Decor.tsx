export function Lamp() {
  return (
    <div className="pointer-events-none absolute left-1/2 top-0 z-[18] -translate-x-1/2">
      <svg width="150" height="92" viewBox="0 0 150 92" className="overflow-visible">
        <defs>
          <linearGradient id="shade" x1="0" x2="1"><stop offset="0" stopColor="#1a1f1c" /><stop offset=".45" stopColor="#3f4a43" /><stop offset="1" stopColor="#141815" /></linearGradient>
          <radialGradient id="bulb"><stop offset="0" stopColor="#fff6dc" /><stop offset=".5" stopColor="#ffd27a" /><stop offset="1" stopColor="#ffb347" stopOpacity="0" /></radialGradient>
        </defs>
        <line x1="75" y1="0" x2="75" y2="26" stroke="#0b0b0b" strokeWidth="2.5" />
        <circle cx="75" cy="88" r="46" fill="url(#bulb)" className="flicker" />
        <path d="M43 62 Q75 8 107 62 Z" fill="url(#shade)" stroke="#0a0c0b" strokeWidth="1.5" />
        <path d="M56 50 Q75 26 94 50" fill="none" stroke="#9fb3a5" strokeOpacity=".35" strokeWidth="2" />
        <ellipse cx="75" cy="62" rx="32" ry="4" fill="#fff0c4" />
        <rect x="71" y="22" width="8" height="8" rx="2" fill="#2b2f2c" />
      </svg>
    </div>
  );
}

export function Magnifier({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 190 190" className={className} style={{ filter: "drop-shadow(12px 16px 9px rgba(0,0,0,.55))" }} aria-label="magnifying glass">
      <defs>
        <linearGradient id="rim" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#f0d792" /><stop offset=".5" stopColor="#b98b3c" /><stop offset="1" stopColor="#6d4b16" /></linearGradient>
        <linearGradient id="wood" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#4a2a14" /><stop offset=".5" stopColor="#7b4a26" /><stop offset="1" stopColor="#3a210f" /></linearGradient>
        <radialGradient id="lens" cx=".4" cy=".35"><stop offset="0" stopColor="#dff2ff" stopOpacity=".42" /><stop offset=".7" stopColor="#9cc7e6" stopOpacity=".2" /><stop offset="1" stopColor="#5d8fb5" stopOpacity=".32" /></radialGradient>
      </defs>
      {/* handle */}
      <g transform="rotate(45 78 78)">
        <rect x="70" y="124" width="16" height="22" rx="3" fill="url(#rim)" />
        <rect x="68" y="144" width="20" height="58" rx="9" fill="url(#wood)" />
        <rect x="72" y="150" width="3" height="44" rx="1.5" fill="#fff" opacity=".12" />
      </g>
      {/* rim, lens, reflections */}
      <circle cx="78" cy="78" r="56" fill="none" stroke="url(#rim)" strokeWidth="11" />
      <circle cx="78" cy="78" r="50" fill="none" stroke="#3a2a0e" strokeOpacity=".6" strokeWidth="1.5" />
      <circle cx="78" cy="78" r="50" fill="url(#lens)" />
      <path d="M44 66 A38 38 0 0 1 70 42" fill="none" stroke="#fff" strokeOpacity=".75" strokeWidth="5" strokeLinecap="round" />
      <path d="M50 84 A32 32 0 0 0 64 106" fill="none" stroke="#fff" strokeOpacity=".25" strokeWidth="3" strokeLinecap="round" />
      <circle cx="104" cy="104" r="3" fill="#fff" opacity=".35" />
    </svg>
  );
}
