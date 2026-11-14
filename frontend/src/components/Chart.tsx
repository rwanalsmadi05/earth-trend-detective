import type { Witness } from "../api/types";

export default function Chart({ w }: { w: Witness }) {
  const W = 480, H = 160, pad = 8;
  const xs = w.series.map((s) => s.year), ys = w.series.map((s) => s.value);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const X = (x: number) => pad + ((x - x0) / (x1 - x0)) * (W - 2 * pad);
  const Y = (y: number) => H - pad - ((y - y0) / (y1 - y0 || 1)) * (H - 2 * pad);
  const line = w.series.map((s, i) => `${i ? "L" : "M"}${X(s.year).toFixed(1)},${Y(s.value).toFixed(1)}`).join(" ");
  // Sen-style line for display: slope per decade through the series mean
  const mean = ys.reduce((a, b) => a + b, 0) / ys.length, mx = (x0 + x1) / 2, k = w.stats.sen_per_decade / 10;
  const ty = (x: number) => mean + k * (x - mx);
  const color = w.direction === "up" ? "#7CC8FF" : "#FF8A3D";
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      <path d={line} fill="none" stroke="#F4F1EA" strokeOpacity=".5" strokeWidth="1.5" />
      <line x1={X(x0)} x2={X(x1)} y1={Y(ty(x0))} y2={Y(ty(x1))} stroke={color} strokeWidth="2.5" />
      <text x={pad} y={H - 1} fontSize="9" fill="#F4F1EA" opacity=".5" fontFamily="JetBrains Mono">{x0}</text>
      <text x={W - pad} y={H - 1} fontSize="9" fill="#F4F1EA" opacity=".5" textAnchor="end" fontFamily="JetBrains Mono">{x1}</text>
    </svg>
  );
}
