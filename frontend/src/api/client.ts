import type { CaseResponse, ExpertItem, GameRound, GridResponse, ManualCaseRequest, Witness, LifetimeItem, LifetimeResponse, TwistResponse, VariableId } from "./types";
import { defaultBbox, mockGrid, mockTwist } from "../mock/grid";
import { mockAzraq } from "../mock/azraq";

// Flip VITE_USE_MOCK=false once the backend serves POST /case in the shape of types.ts.
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}

export async function openCase(question: string, loc?: { lat: number; lon: number }): Promise<CaseResponse> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 900));
    return loc ? { ...mockAzraq, question, case_id: `custom_${loc.lat}_${loc.lon}`, place: { name: `${loc.lat.toFixed(2)}°N ${loc.lon.toFixed(2)}°E`, name_ar: "", lat: loc.lat, lon: loc.lon } } : { ...mockAzraq, question };
  } else {
    const body = loc ? { question, lat: loc.lat, lon: loc.lon } : { question };
    const [c, ex] = await Promise.all([
      post<CaseResponse>("/case", body),
      post<{ variables: Record<string, ExpertItem> }>("/case/expert", body).catch(() => null), // expert info is optional
    ]);
    return { ...c, expert: ex?.variables };
  }
}

// ---- Since you were born -------------------------------------------------------------
// Uses GET /lifetime when the backend has it; on 404/501/network error it falls back to a mock that is
// labelled "mock" in data_label (the UI shows SIMULATED), so the switch happens automatically.
export async function getLifetime(place: string, birthYear: number, ctx: CaseResponse): Promise<LifetimeResponse> {
  if (!USE_MOCK) {
    try {
      const res = await fetch(`/api/lifetime?place=${encodeURIComponent(place)}&birth_year=${birthYear}`);
      const ct = res.headers.get("content-type") ?? "";
      if (res.ok && ct.includes("json")) return await res.json();
    } catch { /* endpoint not there yet */ }
  }
  await new Promise((r) => setTimeout(r, 350));
  return mockLifetime(place, birthYear, ctx);
}

const PICK: VariableId[] = ["T2M", "PRECTOTCORR", "HOT_DAYS", "GWETROOT", "NDVI"];
const PHRASE: Record<string, [string, string]> = {
  T2M: ["hotter", "cooler"], T2M_MAX: ["hotter days", "cooler days"], PRECTOTCORR: ["more rain", "less rain"],
  GWETROOT: ["wetter ground", "drier ground"], GWETTOP: ["wetter surface soil", "drier surface soil"],
  HOT_DAYS: ["more days above 35 °C per year", "fewer days above 35 °C per year"], NDVI: ["greener", "less green"],
};

// Simulated: scales the case's own per-period change to the years since birth. Not a real lifetime test.
function mockLifetime(place: string, birthYear: number, ctx: CaseResponse): LifetimeResponse {
  const start = ctx.period.start, end = ctx.period.end;
  const by = Math.min(Math.max(birthYear, start), end - 1), years = end - by;
  const ws = PICK.map((v) => ctx.witnesses.find((w) => w.variable === v)).filter((w): w is NonNullable<typeof w> => !!w).slice(0, 3);
  const items: LifetimeItem[] = ws.map((w) => {
    const absolute = w.variable === "T2M" || w.variable === "T2M_MAX" || w.variable === "HOT_DAYS";
    const span = Math.max(1, end - Math.max(start, w.start_year));
    const value = (absolute ? w.stats.total_change : w.stats.pct_change) * (years / span);
    const unit = w.variable === "HOT_DAYS" ? " days" : absolute ? "°C" : "%";
    const dir = value >= 0 ? 0 : 1;
    const digits = unit.trim() === "days" || (unit === "%" && Math.abs(value) >= 1) ? 0 : 1;
    return {
      variable: w.variable, label: w.label, value: +value.toFixed(3), display_unit: unit, direction: value >= 0 ? "up" : "down",
      headline: `${Math.abs(value).toFixed(digits)}${unit === "%" ? "%" : unit === "°C" ? " °C" : unit} ${(PHRASE[w.variable] ?? ["more", "less"])[dir]} since ${by}`,
      verdict: years >= 15 ? w.verdict : "NOT PROVEN", p: years >= 15 ? w.stats.p : 0.3, source: w.source,
    };
  });
  return { place: { name: place || ctx.place.name, lat: ctx.place.lat, lon: ctx.place.lon }, birth_year: by, end_year: end, years, items, data_label: { origin: "mock", fetched: ctx.data_label.fetched } };
}

// ---- Where map + The Twist -----------------------------------------------------------
// Both use the real endpoint when it answers with JSON, otherwise a mock labelled "mock" (shown as SIMULATED).
async function tryGet<T>(url: string): Promise<T | null> {
  if (USE_MOCK) return null;
  try {
    const res = await fetch(url);
    if (res.ok && (res.headers.get("content-type") ?? "").includes("json")) return (await res.json()) as T;
  } catch { /* endpoint not there yet */ }
  return null;
}

export async function getGrid(variable: VariableId, bbox: [number, number, number, number], ctx: CaseResponse): Promise<GridResponse> {
  const real = await tryGet<GridResponse>(`/api/grid?variable=${variable}&bbox=${bbox.join(",")}`);
  if (real) return real;
  await new Promise((r) => setTimeout(r, 250));
  return mockGrid(variable, bbox, ctx);
}

export async function getTwist(ctx: CaseResponse): Promise<TwistResponse> {
  const real = await tryGet<TwistResponse>(`/api/twist?case_id=${encodeURIComponent(ctx.case_id)}`);
  if (real) return real;               // includes {found:false}: then the section hides
  return mockTwist(ctx);
}

export { defaultBbox };

// ---- Manual mode: pick the witnesses yourself ---------------------------------------
export async function openManualCase(req: ManualCaseRequest): Promise<CaseResponse> {
  const place = req.place?.trim() || `${req.lat.toFixed(2)}°N ${req.lon.toFixed(2)}°E`;
  const title = `Manual case: ${req.variables.length} witness${req.variables.length === 1 ? "" : "es"} at ${place}, ${req.start}–${req.end}`;
  const body = { question: "", place: req.place, lat: req.lat, lon: req.lon, variables: req.variables, start: req.start, end: req.end };
  let data: CaseResponse;
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 700));
    const ws = mockAzraq.witnesses.filter((w) => req.variables.includes(w.variable));
    if (!ws.length) throw new Error("The demo data only has temperature, rainfall, root-zone soil moisture and NDVI. Start the backend for the rest.");
    const confirmed = ws.filter((w) => w.verdict === "CONFIRMED").length;
    data = {
      ...mockAzraq, case_id: `manual_${req.lat}_${req.lon}`, place: { name: place, name_ar: "", lat: req.lat, lon: req.lon },
      period: { start: req.start, end: req.end }, witnesses: ws, chain: [], hints: [],
      verdict: { confirmed, total: ws.length, headline: `${confirmed} of ${ws.length} witnesses show a significant change (simulated)` },
    };
  } else {
    data = await post<CaseResponse>("/case", body);
    try { const ex = await post<{ variables: Record<string, ExpertItem> }>("/case/expert", body); data = { ...data, expert: ex.variables }; } catch { /* optional */ }
  }
  return { ...data, question: data.question?.trim() || title };
}

// ---- Real or noise? ---------------------------------------------------------------
// Every answer is a real test result: GET /game/round when the backend has it, otherwise the case's own witnesses
// (their verdicts come from the backend's statistics). More real series are pulled from POST /case if the case has too few.
const pTxt = (p: number) => (p < 0.0001 ? "p < 0.0001" : `p = ${p.toFixed(3)}`);

export function explain(w: Witness, place: string, borderline: boolean): string {
  if (w.verdict === "CONFIRMED") {
    return `Real trend: ${w.headline.charAt(0).toLowerCase()}${w.headline.slice(1)} at ${place} (${pTxt(w.stats.p)}). ${borderline ? "It only just passes the bar, so it is a borderline call." : "Chance alone would rarely draw a line this steady."}`;
  }
  return `Just noise, as far as the test can tell: ${w.label.toLowerCase()} at ${place} wobbles about as much as chance would make it (${pTxt(w.stats.p)}).`;
}

function toRound(w: Witness, ctx: CaseResponse, borderline: boolean): GameRound {
  const place = ctx.place.name.split(",")[0];
  return {
    variable: w.variable, label: w.label, unit: w.unit, place: { name: place, lat: ctx.place.lat, lon: ctx.place.lon },
    period: { start: w.series[0]?.year ?? ctx.period.start, end: w.series[w.series.length - 1]?.year ?? ctx.period.end },
    series: w.series, verdict: w.verdict, p: w.stats.p, tau: w.stats.tau, sen_per_decade: w.stats.sen_per_decade, n: w.stats.n,
    borderline, explanation: explain(w, place, borderline), data_label: ctx.data_label,
  };
}

const shuffle = <T,>(a: T[]) => { const b = [...a]; for (let i = b.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [b[i], b[j]] = [b[j], b[i]]; } return b; };

export async function getGameRounds(ctx: CaseResponse, n = 5): Promise<GameRound[]> {
  if (USE_MOCK || ctx.data_label.origin === "mock") return []; // simulated verdicts are never used as answers

  // 1) the real endpoint, alternating the verdict we ask for so the rounds mix both outcomes
  const fromApi: GameRound[] = [];
  for (let i = 0; i < n; i++) {
    const want = i % 2 === 0 ? "CONFIRMED" : "NOT PROVEN";
    const r = await tryGet<GameRound>(`/api/game/round?case_id=${encodeURIComponent(ctx.case_id)}&want=${encodeURIComponent(want)}&exclude=${fromApi.map((x) => x.variable).join(",")}`);
    if (!r) break;
    fromApi.push(r);
  }
  if (fromApi.length === n) return shuffle(fromApi);

  // 2) the case's own series, plus extra real ones from the backend when the case is too small or one-sided
  let ws = ctx.witnesses.filter((w) => w.series.length >= 8);
  const rounds = new Map<string, GameRound>();
  ws.forEach((w) => rounds.set(w.variable, toRound(w, ctx, !!ctx.expert?.[w.variable]?.borderline && w.verdict === "CONFIRMED")));
  const both = () => { const v = [...rounds.values()].map((r) => r.verdict); return v.includes("CONFIRMED") && v.includes("NOT PROVEN"); };
  if (rounds.size < n || !both()) {
    const missing = (["T2M", "T2M_MAX", "PRECTOTCORR", "GWETROOT", "GWETTOP", "RH2M", "ALLSKY_SFC_SW_DWN", "HOT_DAYS"] as const).filter((v) => !rounds.has(v));
    try {
      const body = { question: "", place: ctx.place.name.split(",")[0], lat: ctx.place.lat, lon: ctx.place.lon, variables: missing, start: ctx.period.start, end: ctx.period.end };
      const extra = await post<CaseResponse>("/case", body);
      const ex = await post<{ variables: Record<string, ExpertItem> }>("/case/expert", body).catch(() => null);
      for (const w of extra.witnesses) if (w.series.length >= 8 && !rounds.has(w.variable)) rounds.set(w.variable, toRound(w, extra, !!ex?.variables[w.variable]?.borderline && w.verdict === "CONFIRMED"));
    } catch { /* keep what we have */ }
  }
  // keep a mix: put NOT PROVEN first so they are not cut off, then fill with CONFIRMED
  const all = [...rounds.values()];
  const np = all.filter((r) => r.verdict === "NOT PROVEN"), cf = all.filter((r) => r.verdict === "CONFIRMED");
  const take: GameRound[] = [];
  const target = Math.min(n, all.length), wantNp = Math.min(np.length, Math.max(1, Math.round(target * 0.4)));
  take.push(...shuffle(np).slice(0, wantNp)); take.push(...shuffle(cf).slice(0, target - take.length));
  if (take.length < target) take.push(...np.filter((r) => !take.includes(r)).slice(0, target - take.length));
  return shuffle(take);
}
