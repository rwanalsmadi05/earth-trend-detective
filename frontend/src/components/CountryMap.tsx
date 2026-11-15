import { useEffect, useState, type ReactElement } from "react";

// Natural Earth 1:50m admin-0 outlines (public domain), bundled as /data/countries.json: [{ n, b:[w,s,e,n], p:[ring,...] }]
interface Country { n: string; b: [number, number, number, number]; p: [number, number][][] }
let cache: Promise<Country[]> | null = null;
const load = () => (cache ??= fetch(`${import.meta.env.BASE_URL}data/countries.json`).then((r) => r.json() as Promise<Country[]>).catch((e) => { cache = null; throw e; }));

const inRing = (x: number, y: number, ring: [number, number][]) => {
  let c = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c;
  }
  return c;
};
const containing = (cs: Country[], lon: number, lat: number) => cs.find((c) => lon >= c.b[0] && lon <= c.b[2] && lat >= c.b[1] && lat <= c.b[3] && c.p.some((r) => inRing(lon, lat, r)));
const nearest = (cs: Country[], lon: number, lat: number) => {
  let best: Country | undefined, bd = Infinity;
  for (const c of cs) for (const r of c.p) for (const [x, y] of r) { const d = Math.hypot(x - lon, y - lat); if (d < bd) { bd = d; best = c; } }
  return { c: best, d: bd };
};

const LOOP = (cx: number, cy: number, r: number) =>
  `M${cx - r},${cy - 1} C${cx - r},${cy - r * 1.3} ${cx + r},${cy - r * 1.4} ${cx + r * 1.05},${cy} C${cx + r * 1.1},${cy + r * 1.3} ${cx - r * 1.1},${cy + r * 1.35} ${cx - r * 1.02},${cy - 2} C${cx - r * 0.9},${cy - r * 1.1} ${cx - 1},${cy - r * 1.25} ${cx + 3},${cy - r * 1.1}`;

export default function CountryMap({ lat, lon, name }: { lat: number; lon: number; name: string }) {
  const [cs, setCs] = useState<Country[] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => { load().then(setCs).catch(() => setFailed(true)); }, []);

  if (!cs) return <div className="flex aspect-square items-center justify-center bg-[#e8dcc0] font-mono text-[10px] text-night/40">{failed ? "map unavailable" : "…"}</div>;

  // which country holds the point? (sea: nearest coast within 4 degrees, else a plain region frame)
  const inside = containing(cs, lon, lat);
  const near = inside ? undefined : nearest(cs, lon, lat);
  const main = inside ?? (near && near.d <= 4 ? near.c : undefined);

  // frame: the whole country when it is small enough, otherwise a window around the point
  let w: number, s: number, e: number, n: number;
  if (main && main.b[2] - main.b[0] <= 24 && main.b[3] - main.b[1] <= 20) {
    const px = (main.b[2] - main.b[0]) * 0.12 + 0.3, py = (main.b[3] - main.b[1]) * 0.12 + 0.3;
    [w, s, e, n] = [main.b[0] - px, main.b[1] - py, main.b[2] + px, main.b[3] + py];
  } else {
    const hx = main ? 9 : 4.5, hy = main ? 7 : 3.5;
    [w, s, e, n] = [lon - hx, lat - hy, lon + hx, lat + hy];
  }
  for (const side of [0, 1]) { // keep the card roughly square and never tiny
    const kx = Math.cos((((s + n) / 2) * Math.PI) / 180);
    const wd = (e - w) * kx, ht = n - s;
    if (side === 0 && ht / wd < 0.7) { const add = (0.7 * wd - ht) / 2; s -= add; n += add; }
    else if (side === 0 && ht / wd > 1.25) { const add = (ht / 1.25 - wd) / 2 / kx; w -= add; e += add; }
  }
  if (e - w < 4) { const m = (w + e) / 2; w = m - 2; e = m + 2; }
  const kx = Math.cos((((s + n) / 2) * Math.PI) / 180), K = 100 / ((e - w) * kx), H = (n - s) * K;
  const X = (x: number) => (x - w) * kx * K, Y = (y: number) => (n - y) * K;
  const path = (c: Country) => c.p.map((r) => "M" + r.map(([x, y]) => `${X(x).toFixed(1)},${Y(y).toFixed(1)}`).join("L") + "Z").join("");

  const neighbours = cs.filter((c) => c !== main && c.b[0] < e && c.b[2] > w && c.b[1] < n && c.b[3] > s);
  const cx = X(lon), cy = Y(lat);
  const step = e - w > 14 ? 5 : e - w > 6 ? 2 : 1;
  const grat: ReactElement[] = [];
  for (let la = Math.ceil(s / step) * step; la < n; la += step) grat.push(<line key={"a" + la} x1="0" x2="100" y1={Y(la)} y2={Y(la)} />);
  for (let lo = Math.ceil(w / step) * step; lo < e; lo += step) grat.push(<line key={"o" + lo} y1="0" y2={H} x1={X(lo)} x2={X(lo)} />);
  // country label at the middle of its visible part, nudged away from the circled point
  const lbl = (c: Country, size: number) => {
    const mx = (Math.max(c.b[0], w) + Math.min(c.b[2], e)) / 2, my = (Math.max(c.b[1], s) + Math.min(c.b[3], n)) / 2;
    let x = X(mx), y = Y(my); if (Math.hypot(x - cx, y - cy) < 16) y += 20;
    return x > 8 && x < 92 && y > 6 && y < H - 4 ? <text key={c.n} x={x} y={y} textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize={size} fill={c === main ? "#6b5a36" : "#a89870"} letterSpacing=".4">{c.n.toUpperCase()}</text> : null;
  };
  const place = name.split(",")[0];

  return (
    <svg viewBox={`0 0 100 ${H.toFixed(1)}`} className="block w-full" role="img" aria-label={`Map of ${main?.n ?? "the region"} with ${place} circled`}>
      <rect width="100" height={H} fill="#e8dcc0" />
      <g stroke="#b9a77c" strokeWidth=".25" strokeDasharray="1 1.4" opacity=".7">{grat}</g>
      {neighbours.map((c) => <path key={c.n} d={path(c)} fill="#ece1c6" stroke="#bfae84" strokeWidth=".35" strokeLinejoin="round" />)}
      {neighbours.map((c) => lbl(c, 2.5))}
      {main ? (
        <>
          <path d={path(main)} fill="#f6edd4" stroke="#6b5a36" strokeWidth=".9" strokeLinejoin="round" />
          <path d={path(main)} fill="none" stroke="#6b5a36" strokeWidth=".25" transform="translate(.7 .9)" opacity=".35" />
          {lbl(main, 3.4)}
        </>
      ) : (
        <>
          <rect x="3" y="3" width="94" height={H - 6} fill="none" stroke="#8a7a55" strokeWidth=".5" strokeDasharray="2 2" />
          <text x="50" y="9" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="3" fill="#8a7a55">OPEN WATER · REGION VIEW</text>
        </>
      )}
      {/* the place, circled in red marker */}
      <path d={LOOP(cx, cy, 6.5)} fill="none" stroke="#C8261E" strokeWidth="1.5" strokeLinecap="round" opacity=".9" />
      <circle cx={cx} cy={cy} r=".9" fill="#C8261E" />
      <text x={cx} y={Math.min(H - 3, cy + 6.5 * 1.35 + 6)} textAnchor="middle" fontFamily="Caveat, cursive" fontSize="6.5" fontWeight="700" fill="#C8261E">{place}</text>
    </svg>
  );
}
