// Built-in gazetteer: Jordan and nearby places (English, Arabic, centre point). OpenStreetMap Nominatim is only a fallback.
export interface Place { name: string; name_ar: string; lat: number; lon: number }

export const GAZETTEER: Place[] = [
  { name: "Amman", name_ar: "عمّان", lat: 31.95, lon: 35.93 },
  { name: "Irbid", name_ar: "إربد", lat: 32.556, lon: 35.85 },
  { name: "Zarqa", name_ar: "الزرقاء", lat: 32.07, lon: 36.09 },
  { name: "Azraq", name_ar: "الأزرق", lat: 31.88, lon: 36.83 },
  { name: "Aqaba", name_ar: "العقبة", lat: 29.53, lon: 35.0 },
  { name: "Madaba", name_ar: "مأدبا", lat: 31.72, lon: 35.79 },
  { name: "Karak", name_ar: "الكرك", lat: 31.18, lon: 35.7 },
  { name: "Ma'an", name_ar: "معان", lat: 30.19, lon: 35.73 },
  { name: "Salt", name_ar: "السلط", lat: 32.04, lon: 35.73 },
  { name: "Jerash", name_ar: "جرش", lat: 32.28, lon: 35.9 },
  { name: "Ajloun", name_ar: "عجلون", lat: 32.33, lon: 35.75 },
  { name: "Mafraq", name_ar: "المفرق", lat: 32.34, lon: 36.21 },
  { name: "Tafilah", name_ar: "الطفيلة", lat: 30.84, lon: 35.6 },
  { name: "Petra", name_ar: "البتراء", lat: 30.33, lon: 35.44 },
  { name: "Wadi Rum", name_ar: "وادي رم", lat: 29.58, lon: 35.42 },
  { name: "Dead Sea", name_ar: "البحر الميت", lat: 31.5, lon: 35.5 },
  { name: "Ramtha", name_ar: "الرمثا", lat: 32.56, lon: 36.01 },
  { name: "Ruwaished", name_ar: "الرويشد", lat: 32.51, lon: 38.2 },
  { name: "Mount Nebo", name_ar: "جبل نبو", lat: 31.77, lon: 35.73 },
  { name: "Jerusalem", name_ar: "القدس", lat: 31.77, lon: 35.21 },
  { name: "Gaza", name_ar: "غزة", lat: 31.5, lon: 34.47 },
  { name: "Eilat", name_ar: "إيلات", lat: 29.56, lon: 34.95 },
  { name: "Damascus", name_ar: "دمشق", lat: 33.51, lon: 36.29 },
  { name: "Beirut", name_ar: "بيروت", lat: 33.89, lon: 35.5 },
  { name: "Baghdad", name_ar: "بغداد", lat: 33.31, lon: 44.37 },
  { name: "Tabuk", name_ar: "تبوك", lat: 28.38, lon: 36.57 },
  { name: "Riyadh", name_ar: "الرياض", lat: 24.71, lon: 46.68 },
  { name: "Cairo", name_ar: "القاهرة", lat: 30.04, lon: 31.24 },
];

const norm = (s: string) => s.normalize("NFKD").replace(/[ً-ٰٟ']/g, "").toLowerCase().trim();

export function searchGazetteer(q: string): Place[] {
  const n = norm(q);
  if (!n) return [];
  return GAZETTEER.filter((p) => norm(p.name).includes(n) || norm(p.name_ar).includes(n)).slice(0, 6);
}

export async function searchNominatim(q: string): Promise<Place | null> {
  const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(q)}`, { headers: { Accept: "application/json" } });
  const j = (await res.json()) as { display_name: string; lat: string; lon: string }[];
  return j[0] ? { name: j[0].display_name.split(",")[0], name_ar: "", lat: +j[0].lat, lon: +j[0].lon } : null;
}
