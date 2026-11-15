import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import type { ManualCaseRequest, VariableId } from "../api/types";
import { CATALOG } from "../data/catalog";
import { GAZETTEER, searchGazetteer, searchNominatim, type Place } from "../data/gazetteer";

maplibregl.setWorkerUrl(workerUrl);

const FIRST = 1981, NDVI_FROM = 2000, MIN_SPAN = 10;
export const LATEST_FULL_YEAR = new Date().getFullYear() - 1;

const near = (lat: number, lon: number): Place | undefined =>
  GAZETTEER.find((p) => Math.hypot(p.lat - lat, p.lon - lon) < 0.25);

function dot() {
  const el = document.createElement("div");
  el.style.cssText = "width:18px;height:18px;border-radius:50%;background:#C8261E;border:3px solid #F4F1EA;box-shadow:0 0 0 6px rgba(200,38,30,.35),0 3px 8px rgba(0,0,0,.6)";
  return el;
}

interface Props { initial: Place | null; onClose: () => void; onSubmit: (req: ManualCaseRequest) => void; busy: boolean; error: string | null }

export default function WitnessPicker({ initial, onClose, onSubmit, busy, error }: Props) {
  const [place, setPlace] = useState<Place>(initial ?? GAZETTEER.find((p) => p.name === "Azraq")!);
  const [query, setQuery] = useState("");
  const [online, setOnline] = useState<"idle" | "busy" | "none">("idle");
  const [vars, setVars] = useState<Set<VariableId>>(new Set(["T2M", "PRECTOTCORR"]));
  const [range, setRange] = useState<[number, number]>([FIRST, LATEST_FULL_YEAR]);

  const suggestions = useMemo(() => searchGazetteer(query), [query]);
  const onlyNdvi = vars.size > 0 && [...vars].every((v) => v === "NDVI");
  const minYear = onlyNdvi ? NDVI_FROM : FIRST;
  const hasNdvi = vars.has("NDVI");
  const [a, b] = [Math.max(range[0], minYear), range[1]];
  const valid = vars.size > 0 && b - a >= MIN_SPAN;

  // lock page scroll + Esc to close
  useEffect(() => {
    const prev = document.body.style.overflow; document.body.style.overflow = "hidden";
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => { document.body.style.overflow = prev; window.removeEventListener("keydown", k); };
  }, [onClose]);

  // ---- mini map: click to choose the place ----
  const boxRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markerRef = useRef<maplibregl.Marker | null>(null);
  useEffect(() => {
    if (!boxRef.current) return;
    const map = new maplibregl.Map({
      container: boxRef.current, center: [place.lon, place.lat], zoom: 5.6, attributionControl: { compact: true }, dragRotate: false,
      style: { version: 8, sources: { base: { type: "raster", tileSize: 256, tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"], maxzoom: 16, attribution: "Tiles © Esri, HERE, Garmin, OpenStreetMap contributors" } },
        layers: [{ id: "bg", type: "background", paint: { "background-color": "#05070B" } }, { id: "base", type: "raster", source: "base" }] },
    });
    mapRef.current = map;
    markerRef.current = new maplibregl.Marker({ element: dot() }).setLngLat([place.lon, place.lat]).addTo(map);
    map.on("click", (e) => {
      const lat = +e.lngLat.lat.toFixed(3), lon = +e.lngLat.lng.toFixed(3);
      const g = near(lat, lon);
      setPlace(g ?? { name: `${lat.toFixed(2)}°N ${lon.toFixed(2)}°E`, lat, lon });
    });
    return () => { map.remove(); mapRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    markerRef.current?.setLngLat([place.lon, place.lat]);
    mapRef.current?.easeTo({ center: [place.lon, place.lat], duration: 500 });
  }, [place]);

  function toggle(id: VariableId) {
    setVars((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  }
  async function fromOnline() {
    setOnline("busy");
    try { const p = await searchNominatim(query); if (p) { setPlace(p); setQuery(""); setOnline("idle"); } else setOnline("none"); } catch { setOnline("none"); }
  }
  function setA(v: number) { setRange([Math.min(Math.max(v, minYear), b - MIN_SPAN), b]); }
  function setB(v: number) { setRange([a, Math.max(Math.min(v, LATEST_FULL_YEAR), a + MIN_SPAN)]); }
  function submit() {
    if (!valid || busy) return;
    onSubmit({ question: "", place: place.name, lat: place.lat, lon: place.lon, variables: CATALOG.filter((c) => vars.has(c.id)).map((c) => c.id), start: a, end: b });
  }
  const pct = (y: number) => ((y - FIRST) / (LATEST_FULL_YEAR - FIRST)) * 100;

  return (
    <motion.div className="fixed inset-0 z-[60] overflow-y-auto bg-black/80 p-3 backdrop-blur-sm sm:p-8" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <motion.div initial={{ y: 40, rotate: -1 }} animate={{ y: 0, rotate: 0 }} transition={{ type: "spring", damping: 18 }}
        className="relative mx-auto max-w-5xl bg-paper p-5 font-type text-night shadow-[0_30px_80px_rgba(0,0,0,.7)] sm:p-9"
        style={{ backgroundImage: "repeating-linear-gradient(transparent 0 31px, rgba(80,120,200,.12) 31px 32px)" }}>
        <span className="absolute -top-3 left-1/2 h-5 w-5 -translate-x-1/2 rounded-full bg-stamp shadow-[0_3px_5px_rgba(0,0,0,.5)]" />
        <button onClick={onClose} aria-label="Close" className="absolute right-4 top-3 text-2xl text-night/50 hover:text-night">×</button>

        <p className="text-[11px] tracking-[0.4em] text-night/50">FORM 7-B · NO AI REQUIRED</p>
        <h2 className="mt-1 text-3xl leading-tight sm:text-4xl">Pick the witnesses yourself</h2>
        <p className="mt-1 font-hand text-2xl text-night/70">Choose where, what and when. The statistics decide the verdicts.</p>

        {/* 1. place */}
        <section className="mt-8">
          <h3 className="text-sm tracking-[0.3em] text-stamp">1 · THE PLACE</h3>
          <div className="mt-3 grid gap-4 md:grid-cols-[1fr_1.1fr]">
            <div>
              <div className="relative">
                <input value={query} onChange={(e) => { setQuery(e.target.value); setOnline("idle"); }} placeholder="Search: Azraq, Irbid, Aqaba…"
                  className="w-full border-b-2 border-night/40 bg-white/60 px-3 py-2 font-type text-lg outline-none focus:border-stamp" />
                {query.trim() && (
                  <ul className="absolute z-20 mt-1 w-full border border-night/20 bg-paper shadow-lg">
                    {suggestions.map((p) => (
                      <li key={p.name}><button className="flex w-full justify-between px-3 py-2 text-left hover:bg-stamp/10" onClick={() => { setPlace(p); setQuery(""); }}>
                        <span>{p.name}</span></button></li>
                    ))}
                    {!suggestions.length && (
                      <li className="px-3 py-2 text-sm">
                        {online === "none" ? <span className="text-night/60">Nothing found online either.</span> :
                          <button className="underline" disabled={online === "busy"} onClick={fromOnline}>{online === "busy" ? "Searching…" : `Not in the gazetteer. Search OpenStreetMap for “${query}”`}</button>}
                      </li>
                    )}
                  </ul>
                )}
              </div>
              <p className="mt-4 text-[11px] tracking-widest text-night/50">SELECTED</p>
              <p className="text-2xl">{place.name}</p>
              <p className="text-sm text-night/60">{place.lat.toFixed(3)}°N, {place.lon.toFixed(3)}°E</p>
              <p className="mt-3 font-hand text-xl text-night/70">…or click the map to drop the red pin anywhere.</p>
            </div>
            <div ref={boxRef} className="h-56 w-full overflow-hidden border-4 border-white shadow-[0_6px_14px_rgba(0,0,0,.35)] sm:h-64" />
          </div>
        </section>

        {/* 2. variables */}
        <section className="mt-9">
          <h3 className="text-sm tracking-[0.3em] text-stamp">2 · THE WITNESSES <span className="text-night/40">· tick one or more</span></h3>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {CATALOG.map((c, i) => {
              const on = vars.has(c.id);
              return (
                <motion.button key={c.id} type="button" onClick={() => toggle(c.id)} aria-pressed={on} whileHover={{ y: -3, rotate: 0 }} animate={{ rotate: on ? 0 : (i % 2 ? 0.8 : -0.8) }}
                  className={`relative flex gap-3 border bg-white/70 p-3 pr-4 text-left shadow-[0_4px_8px_rgba(0,0,0,.18)] transition ${on ? "border-stamp ring-2 ring-stamp/70" : "border-night/20"}`}>
                  <span className="text-3xl leading-none">{c.icon}</span>
                  <span className="min-w-0">
                    <span className="block text-base leading-5">{c.label}{c.from && <span className="ml-1 bg-[#f6e27a] px-1 font-hand text-sm">from {c.from}</span>}</span>
                    <span className="mt-0.5 block font-hand text-lg leading-5 text-night/75">{c.line}</span>
                    <span className="mt-1 block text-[9px] tracking-wide text-night/45">{c.source}</span>
                  </span>
                  {on && <span className="absolute -right-2 -top-2 rotate-12 border-2 border-stamp bg-paper/80 px-1.5 text-[11px] font-bold tracking-widest text-stamp">CALLED</span>}
                </motion.button>
              );
            })}
          </div>
          {hasNdvi && <p className="mt-3 font-hand text-xl text-night/70">Vegetation (NDVI) starts in 2000, so it is only tested from 2000 on.</p>}
        </section>

        {/* 3. period */}
        <section className="mt-9">
          <h3 className="text-sm tracking-[0.3em] text-stamp">3 · THE PERIOD</h3>
          <p className="mt-2 text-3xl tabular-nums">{a} <span className="text-night/40">→</span> {b} <span className="ml-2 text-base text-night/50">({b - a} years)</span></p>
          <div className="relative mt-3 h-8">
            <div className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded bg-night/20" />
            <div className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded bg-stamp" style={{ left: `${pct(a)}%`, width: `${pct(b) - pct(a)}%` }} />
            {onlyNdvi && <div className="absolute top-1/2 h-3 -translate-y-1/2 bg-night/30" style={{ left: 0, width: `${pct(NDVI_FROM)}%` }} title="No NDVI before 2000" />}
            <input type="range" className="dual" min={FIRST} max={LATEST_FULL_YEAR} value={a} onChange={(e) => setA(+e.target.value)} aria-label="Start year" />
            <input type="range" className="dual" min={FIRST} max={LATEST_FULL_YEAR} value={b} onChange={(e) => setB(+e.target.value)} aria-label="End year" />
          </div>
          <div className="mt-1 flex justify-between text-[11px] text-night/50"><span>{FIRST}</span><span>{LATEST_FULL_YEAR} (latest full year)</span></div>
          <p className="mt-1 text-[11px] text-night/50">At least {MIN_SPAN} years are needed to tell a trend from noise.</p>
        </section>

        {/* open */}
        <div className="mt-9 flex flex-wrap items-center justify-between gap-4 border-t-2 border-dashed border-night/30 pt-5">
          <p className="max-w-md text-sm leading-5 text-night/70">
            {vars.size ? `${vars.size} witness${vars.size === 1 ? "" : "es"} · ${place.name} · ${a}–${b}` : "Tick at least one witness."}
            {error && <span className="mt-1 block text-stamp">{error}</span>}
          </p>
          <div className="flex items-center gap-4">
            <button onClick={onClose} className="text-sm underline text-night/60">cancel</button>
            <button onClick={submit} disabled={!valid || busy}
              className="-rotate-1 border-[3px] border-stamp bg-stamp px-6 py-2.5 text-lg font-bold tracking-[0.2em] text-paper shadow-[0_6px_0_#7d140f] transition enabled:hover:-translate-y-0.5 disabled:opacity-40">
              {busy ? "OPENING…" : "OPEN CASE"}
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
