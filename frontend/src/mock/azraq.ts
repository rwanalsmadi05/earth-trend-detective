import type { CaseResponse, SatImage, VariableId, Witness } from "../api/types";

const bbox = "31.4,36.4,32.4,37.4"; // s,w,n,e around Azraq
const sat = (date: string): SatImage => ({
  date,
  bbox: [36.4, 31.4, 37.4, 32.4], // west, south, east, north (matches BBOX in the URL below)
  url: `https://wvs.earthdata.nasa.gov/api/v1/snapshot?REQUEST=GetSnapshot&TIME=${date}&BBOX=${bbox}&CRS=EPSG:4326&LAYERS=MODIS_Terra_CorrectedReflectance_TrueColor&FORMAT=image/jpeg&WIDTH=600&HEIGHT=500`,
});

// deterministic pseudo-noise so the mock looks the same on every load
const rnd = (i: number, s: number) => { const x = Math.sin(i * 12.9898 + s * 78.233) * 43758.5453; return x - Math.floor(x); };
const series = (start: number, end: number, slope: number, noise: number, seed: number) =>
  Array.from({ length: end - start + 1 }, (_, i) => ({ year: start + i, value: +(slope * i + (rnd(i, seed) - 0.5) * noise).toFixed(3) }));

const END = 2025;
const POWER = "https://power.larc.nasa.gov/";

const witnesses: Witness[] = [
  {
    variable: "PRECTOTCORR", label: "Rainfall", unit: "mm/day", direction: "down", verdict: "CONFIRMED", start_year: 1981,
    reason: "Rain refills the Azraq oasis. If it is drying up, rainfall is the first suspect.",
    source: "NASA POWER · PRECTOTCORR", source_url: POWER, images: { before: sat("1990-03-15"), after: sat("2024-03-15") },
    stats: { n: 540, tau: -0.12, p: 0.018, sen_per_decade: -0.004, total_change: -0.018, pct_change: -18 },
    headline: "18% less rain since 1981", series: series(1981, END, -0.0004, 0.08, 1),
  },
  {
    variable: "T2M", label: "Temperature", unit: "°C", direction: "up", verdict: "CONFIRMED", start_year: 1981,
    reason: "Hotter air pulls more water out of soil and open water.",
    source: "NASA POWER · T2M", source_url: POWER, images: { before: sat("1990-08-15"), after: sat("2024-08-15") },
    stats: { n: 540, tau: 0.41, p: 0.00001, sen_per_decade: 0.46, total_change: 2.0, pct_change: 11 },
    headline: "2.0 °C hotter since 1981", series: series(1981, END, 0.046, 0.6, 2),
  },
  {
    variable: "GWETROOT", label: "Root-zone soil moisture", unit: "fraction", direction: "down", verdict: "CONFIRMED", start_year: 1981,
    reason: "Soil moisture shows whether the ground still holds water for plants.",
    source: "NASA POWER · GWETROOT", source_url: POWER, images: { before: sat("1990-05-15"), after: sat("2024-05-15") },
    stats: { n: 540, tau: -0.19, p: 0.004, sen_per_decade: -0.012, total_change: -0.053, pct_change: -14 },
    headline: "14% drier ground under the roots since 1981", series: series(1981, END, -0.0012, 0.04, 3),
  },
  {
    variable: "NDVI", label: "Vegetation (NDVI)", unit: "index", direction: "down", verdict: "NOT PROVEN", start_year: 2000,
    reason: "Plants are the visible witness: green fades when water runs short.",
    source: "MODIS MOD13Q1 · ORNL DAAC", source_url: "https://modis.ornl.gov/", images: { before: sat("2000-05-15"), after: sat("2024-05-15") },
    stats: { n: 300, tau: -0.06, p: 0.21, sen_per_decade: -0.004, total_change: -0.01, pct_change: -4 },
    headline: "Plants slightly lower, but could be chance", series: series(2000, END, -0.0004, 0.03, 4),
  },
];


export const mockAzraq: CaseResponse = {
  case_id: "azraq-demo",
  question: "Is Azraq drying up?",
  place: { name: "Azraq, Jordan", lat: 31.88, lon: 36.83 },
  period: { start: 1981, end: END },
  witnesses,
  chain: [
    { from: "T2M", to: "GWETROOT", lag_months: 2, r: -0.46 },
    { from: "GWETROOT", to: "NDVI", lag_months: 1, r: 0.38 },
  ],
  hints: [
    { after: "T2M", text: "Notice the heat climbed first… then the soil dried." },
    { after: "NDVI", text: "Does 'could be chance' mean 'nothing happened'?" },
  ],
  verdict: { confirmed: 3, total: 4, headline: "3 of 4 witnesses confirm: Azraq is getting drier" },
  data_label: { origin: "mock", fetched: "2026-11-14" },
};

