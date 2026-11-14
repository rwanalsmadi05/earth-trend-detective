import type { CaseResponse, GridCell, GridResponse, TwistResponse, VariableId } from "../api/types";

// SIMULATED grid + twist. Shapes match GridResponse / TwistResponse in api/types.ts.
const WORDS: Record<string, { up: string; down: string }> = {
  T2M: { up: "hotter", down: "cooler" }, T2M_MAX: { up: "hotter days", down: "cooler days" },
  PRECTOTCORR: { up: "more rain", down: "less rain" }, GWETROOT: { up: "wetter ground", down: "drier ground" },
  GWETTOP: { up: "wetter surface soil", down: "drier surface soil" }, HOT_DAYS: { up: "more hot days", down: "fewer hot days" },
  NDVI: { up: "greener", down: "less green" }, RH2M: { up: "more humid", down: "drier air" },
};

const rnd = (a: number, b: number, s: number) => { const x = Math.sin(a * 12.9898 + b * 78.233 + s * 37.719) * 43758.5453; return x - Math.floor(x); };
const bump = (lat: number, lon: number, la: number, lo: number, w: number) => Math.exp(-(((lat - la) ** 2 + ((lon - lo) * 0.86) ** 2)) / w);

export const defaultBbox = (lat: number, lon: number): [number, number, number, number] =>
  lat >= 29 && lat <= 34 && lon >= 34 && lon <= 40 ? [34, 29, 40, 34] : [lon - 3, lat - 2.5, lon + 3, lat + 2.5];

export function mockGrid(variable: VariableId, bbox: [number, number, number, number], ctx: CaseResponse): GridResponse {
  const [w, s, e, n] = bbox, step = 0.5;
  const years = Array.from({ length: ctx.period.end - ctx.period.start + 1 }, (_, i) => ctx.period.start + i);
  const wit = ctx.witnesses.find((x) => x.variable === variable);
  const absolute = variable === "T2M" || variable === "T2M_MAX" || variable === "HOT_DAYS";
  const unit = variable === "HOT_DAYS" ? " days" : absolute ? "°C" : "%";
  const scale = wit ? (absolute ? wit.stats.total_change : wit.stats.pct_change) : 1; // the case place's own change
  const { lat: pl, lon: po } = ctx.place;
  const seed = variable.length * 7 + variable.charCodeAt(0);

  const field = (lat: number, lon: number) => {
    let v = scale * (0.45 + 0.9 * bump(lat, lon, pl, po, 1.6)) + (rnd(lat, lon, seed) - 0.5) * Math.abs(scale) * 0.55;
    // a pocket that moves the other way, so "The Twist" has something real to find
    if (variable === "PRECTOTCORR") v += Math.abs(scale) * 1.35 * bump(lat, lon, pl - 1.5, po - 1.4, 0.45);
    return v;
  };
  const nearest = { v: field(pl, po) };
  const delta = scale - nearest.v; // make the case cell match its witness exactly
  const nCols = Math.round((e - w) / step), nRows = Math.round((n - s) / step);
  const cells: GridCell[] = [];
  for (let r = 0; r < nRows; r++) for (let c = 0; c < nCols; c++) {
    const lat = n - (r + 0.5) * step, lon = w + (c + 0.5) * step;
    const value = field(lat, lon) + delta * bump(lat, lon, pl, po, 0.5);
    const q = Math.min(0.9, 0.012 * Math.exp(-(Math.abs(value) / (Math.abs(scale) || 1) - 0.35) * 5) + rnd(lat, lon, seed + 3) * 0.04);
    const significant = Math.abs(value) > 0.3 * Math.abs(scale) && q < 0.05;
    const series = years.map((_, i) => +(value * (i / (years.length - 1)) + (rnd(i, lat + lon, seed) - 0.5) * Math.abs(scale) * 0.3).toFixed(3));
    cells.push({ lat, lon, value: +value.toFixed(3), q: +q.toFixed(4), significant, verdict: significant ? "CONFIRMED" : "NOT PROVEN", series });
  }
  return { variable, label: wit?.label ?? variable, display_unit: unit, words: WORDS[variable] ?? { up: "more", down: "less" }, bbox, step, years, cells, fdr: "benjamini-hochberg", data_label: { origin: "mock", fetched: ctx.data_label.fetched } };
}

const scaleOf = (ctx: CaseResponse, v: VariableId) => { const w = ctx.witnesses.find((x) => x.variable === v)!; return v === "T2M" || v === "T2M_MAX" || v === "HOT_DAYS" ? w.stats.total_change : w.stats.pct_change; };

// Strongest significant cell whose sign is opposite to the case place's cell. Found from the grid, not hard-coded.
export function mockTwist(ctx: CaseResponse): TwistResponse {
  const order: VariableId[] = ["PRECTOTCORR", "GWETROOT", "T2M"];
  for (const v of order) {
    if (!ctx.witnesses.some((w) => w.variable === v)) continue;
    const g = mockGrid(v, defaultBbox(ctx.place.lat, ctx.place.lon), ctx);
    const home = g.cells.reduce((a, b) => (Math.hypot(a.lat - ctx.place.lat, a.lon - ctx.place.lon) < Math.hypot(b.lat - ctx.place.lat, b.lon - ctx.place.lon) ? a : b));
    if (!home.significant) continue;
    const other = g.cells.filter((c) => c.significant && Math.sign(c.value) === -Math.sign(home.value)).sort((a, b) => Math.abs(b.value) - Math.abs(a.value))[0];
    if (!other) continue;
    const fmt = (x: number) => `${Math.abs(x).toFixed(g.display_unit === "%" ? 0 : 1)}${g.display_unit === "%" ? "%" : g.display_unit === "°C" ? " °C" : g.display_unit}`;
    const word = (x: number) => (x > 0 ? g.words.up : g.words.down);
    const name = (c: GridCell) => `${Math.abs(c.lat).toFixed(1)}° ${c.lat >= 0 ? "N" : "S"}, ${Math.abs(c.lon).toFixed(1)}° ${c.lon >= 0 ? "E" : "W"}`;
    return {
      found: true, variable: v, label: g.label, words: g.words,
      a: { name: ctx.place.name.split(",")[0], lat: ctx.place.lat, lon: ctx.place.lon, value: scaleOf(ctx, v), display_unit: g.display_unit, p: home.q, verdict: home.verdict },
      b: { name: name(other), lat: other.lat, lon: other.lon, value: other.value, display_unit: g.display_unit, p: other.q, verdict: other.verdict },
      sentence: `${g.label} changed by ${fmt(scaleOf(ctx, v))} (${word(scaleOf(ctx, v))}) at ${ctx.place.name.split(",")[0]} but ${fmt(other.value)} (${word(other.value)}) at ${name(other)}. Same region, same climate system, yet the trends point in opposite directions, so one regional average would hide both.`,
      data_label: g.data_label,
    };
  }
  return { found: false };
}
