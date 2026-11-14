import { JORDAN_RINGS } from "../data/jordan";

// Equirectangular map with a cos(lat) correction, framed around Jordan.
const LON0 = 34.5, LON1 = 39.7, LAT0 = 28.9, LAT1 = 33.7;
const KX = Math.cos((31 * Math.PI) / 180);
const K = 100 / ((LON1 - LON0) * KX);
const H = (LAT1 - LAT0) * K;
const px = (lon: number) => (lon - LON0) * KX * K;
const py = (lat: number) => (LAT1 - lat) * K;

const AMMAN = { lat: 31.95, lon: 35.93 };
const NEIGHBOURS: [string, number, number][] = [["SYRIA", 36.9, 33.5], ["IRAQ", 39.0, 32.9], ["SAUDI ARABIA", 37.6, 29.35], ["ISRAEL · PALESTINE", 34.75, 31.0]];

export default function JordanMap({ lat, lon, name }: { lat: number; lon: number; name: string }) {
  const outline = JORDAN_RINGS.map((r) => "M" + r.map(([x, y]) => `${px(x).toFixed(1)},${py(y).toFixed(1)}`).join("L") + "Z").join("");
  const cx = px(lon), cy = py(lat), ax = px(AMMAN.lon), ay = py(AMMAN.lat);
  const nearAmman = Math.hypot(cx - ax, cy - ay) < 16;
  // hand-drawn marker loop: overshoots its own start, like a real red pen
  const r = 6.5;
  const loop = `M${cx - r},${cy - 1} C${cx - r},${cy - r * 1.3} ${cx + r},${cy - r * 1.4} ${cx + r * 1.05},${cy} C${cx + r * 1.1},${cy + r * 1.3} ${cx - r * 1.1},${cy + r * 1.35} ${cx - r * 1.02},${cy - 2} C${cx - r * 0.9},${cy - r * 1.1} ${cx - 1},${cy - r * 1.25} ${cx + 3},${cy - r * 1.1}`;
  const grat = [29, 30, 31, 32, 33].map((l) => <line key={l} x1="0" x2="100" y1={py(l)} y2={py(l)} />).concat([35, 36, 37, 38, 39].map((l) => <line key={"x" + l} y1="0" y2={H} x1={px(l)} x2={px(l)} />));
  return (
    <svg viewBox={`0 0 100 ${H.toFixed(1)}`} className="block w-full" role="img" aria-label={`Map of Jordan with ${name} circled`}>
      <rect width="100" height={H} fill="#e8dcc0" />
      <g stroke="#b9a77c" strokeWidth=".25" strokeDasharray="1 1.4" opacity=".7">{grat}</g>
      <g fontFamily="JetBrains Mono, monospace" fontSize="2.6" fill="#8a7a55" opacity=".8" letterSpacing=".3">
        {NEIGHBOURS.map(([t, lo, la]) => <text key={t} x={px(lo)} y={py(la)} textAnchor="middle">{t}</text>)}
      </g>
      <path d={outline} fill="#f3e9cf" stroke="#6b5a36" strokeWidth=".9" strokeLinejoin="round" />
      <path d={outline} fill="none" stroke="#6b5a36" strokeWidth=".25" transform="translate(.7 .9)" opacity=".35" />
      <text x={px(36.3)} y={py(30.25)} textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="3.4" fill="#6b5a36" letterSpacing=".8">JORDAN</text>
      {/* Amman */}
      <circle cx={ax} cy={ay} r="1.3" fill="#2a2418" />
      <text x={ax - 2.5} y={ay - 2} textAnchor="end" fontFamily="Caveat, cursive" fontSize="6" fill="#2a2418">Amman</text>
      {/* the place, circled in red marker */}
      <path d={loop} fill="none" stroke="#C8261E" strokeWidth="1.5" strokeLinecap="round" opacity=".9" />
      <circle cx={cx} cy={cy} r=".9" fill="#C8261E" />
      <text x={cx + (nearAmman ? 11 : 0)} y={cy + r * 1.35 + 6} textAnchor="middle" fontFamily="Caveat, cursive" fontSize="6.5" fontWeight="700" fill="#C8261E">{name.split(",")[0]}</text>
    </svg>
  );
}
