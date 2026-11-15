// Built-in gazetteer: Jordan and nearby places (English names, centre point). OpenStreetMap Nominatim is only a fallback.
export interface Place { name: string; lat: number; lon: number }

export const GAZETTEER: Place[] = [
  { name: "Amman", lat: 31.95, lon: 35.93 },
  { name: "Irbid", lat: 32.556, lon: 35.85 },
  { name: "Zarqa", lat: 32.07, lon: 36.09 },
  { name: "Azraq", lat: 31.88, lon: 36.83 },
  { name: "Aqaba", lat: 29.53, lon: 35.0 },
  { name: "Madaba", lat: 31.72, lon: 35.79 },
  { name: "Karak", lat: 31.18, lon: 35.7 },
  { name: "Ma'an", lat: 30.19, lon: 35.73 },
  { name: "Salt", lat: 32.04, lon: 35.73 },
  { name: "Jerash", lat: 32.28, lon: 35.9 },
  { name: "Ajloun", lat: 32.33, lon: 35.75 },
  { name: "Mafraq", lat: 32.34, lon: 36.21 },
  { name: "Tafilah", lat: 30.84, lon: 35.6 },
  { name: "Petra", lat: 30.33, lon: 35.44 },
  { name: "Wadi Rum", lat: 29.58, lon: 35.42 },
  { name: "Dead Sea", lat: 31.5, lon: 35.5 },
  { name: "Ramtha", lat: 32.56, lon: 36.01 },
  { name: "Ruwaished", lat: 32.51, lon: 38.2 },
  { name: "Mount Nebo", lat: 31.77, lon: 35.73 },
  { name: "Jerusalem", lat: 31.77, lon: 35.21 },
  { name: "Gaza", lat: 31.5, lon: 34.47 },
  { name: "Eilat", lat: 29.56, lon: 34.95 },
  { name: "Damascus", lat: 33.51, lon: 36.29 },
  { name: "Beirut", lat: 33.89, lon: 35.5 },
  { name: "Baghdad", lat: 33.31, lon: 44.37 },
  { name: "Tabuk", lat: 28.38, lon: 36.57 },
  { name: "Riyadh", lat: 24.71, lon: 46.68 },
  { name: "Cairo", lat: 30.04, lon: 31.24 },
];

const norm = (s: string) => s.replace(/'/g, "").toLowerCase().trim();

export function searchGazetteer(q: string): Place[] {
  const n = norm(q);
  if (!n) return [];
  return GAZETTEER.filter((p) => norm(p.name).includes(n)).slice(0, 6);
}

export async function searchNominatim(q: string): Promise<Place | null> {
  const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(q)}`, { headers: { Accept: "application/json" } });
  const j = (await res.json()) as { display_name: string; lat: string; lon: string }[];
  return j[0] ? { name: j[0].display_name.split(",")[0], lat: +j[0].lat, lon: +j[0].lon } : null;
}
