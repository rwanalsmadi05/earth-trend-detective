import { useEffect, useMemo, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import type { CaseResponse, GridCell, GridResponse, VariableId } from "../api/types";
import { defaultBbox, getGrid } from "../api/client";
import { formatBig } from "../lib/format";

maplibregl.setWorkerUrl(workerUrl); // Vite: load the worker as its own file instead of letting dep pre-bundling break it

const BLUE = [124, 200, 255], ORANGE = [255, 138, 61];
const WINDOW = 5; // years in the running mean that drives the slider

const fmt = (v: number, unit: string) => {
  const b = formatBig(Math.abs(v), unit);
  return `${b.value}${unit === "%" ? "%" : unit === "°C" ? " °C" : unit}`;
};

function targetEl() {
  const el = document.createElement("div");
  el.style.cssText = "width:0;height:0;pointer-events:none";
  el.innerHTML = [0, 0.8, 1.6].map((d) => `<span style="position:absolute;left:-22px;top:-22px;width:44px;height:44px;border:2px solid #FF8A3D;border-radius:50%;animation:lock-ring 2.4s ${d}s ease-out infinite"></span>`).join("")
    + `<svg style="position:absolute;left:-26px;top:-26px" width="52" height="52" viewBox="-26 -26 52 52" fill="none" stroke="#FF8A3D" stroke-width="1"><circle r="16"/><path d="M-25 0H-8M8 0H25M0 -25V-8M0 8V25"/></svg>`
    + `<span style="position:absolute;left:-6px;top:-6px;width:12px;height:12px;border-radius:50%;background:#FF8A3D;box-shadow:0 0 10px 3px #FF8A3D,0 0 24px 8px rgba(255,138,61,.7)"></span>`;
  return el;
}

// per-cell value shown at each year = change since the first year (running mean), the final year = the tested trend
function useValues(grid: GridResponse | null) {
  return useMemo(() => {
    if (!grid) return null;
    const n = grid.years.length;
    const disp = grid.cells.map((c) => {
      const S = c.series.map((_, i) => { const a = Math.max(0, i - WINDOW + 1); const sl = c.series.slice(a, i + 1); return sl.reduce((x, y) => x + y, 0) / sl.length; });
      return S.map((s, i) => (i === n - 1 ? c.value : s - S[0]));
    });
    const mags = grid.cells.filter((c) => c.significant).map((c) => Math.abs(c.value)).sort((a, b) => a - b);
    const vmax = mags.length ? mags[Math.floor(mags.length * 0.9)] || mags[mags.length - 1] : 1;
    return { disp, vmax: vmax || 1 };
  }, [grid]);
}

function heatURL(grid: GridResponse, vals: { disp: number[][]; vmax: number }, k: number): string {
  const [w, s, e, n] = grid.bbox, cols = Math.round((e - w) / grid.step), rows = Math.round((n - s) / grid.step), S = 24;
  const tmp = document.createElement("canvas"); tmp.width = cols * S; tmp.height = rows * S;
  const t = tmp.getContext("2d")!;
  grid.cells.forEach((c, i) => {
    const col = Math.floor((c.lon - w) / grid.step), row = Math.floor((n - c.lat) / grid.step);
    const v = vals.disp[i][k];
    if (!c.significant) t.fillStyle = "rgba(205,214,228,0.10)";
    else {
      const rgb = v >= 0 ? BLUE : ORANGE, a = 0.72 * Math.pow(Math.min(1, Math.abs(v) / vals.vmax), 0.8);
      t.fillStyle = `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a.toFixed(3)})`;
    }
    t.fillRect(col * S, row * S, S + 0.5, S + 0.5);
  });
  const out = document.createElement("canvas"); out.width = tmp.width; out.height = tmp.height;
  const o = out.getContext("2d")!;
  o.filter = "blur(7px)"; // smooth, soft-edged cells (falls back to crisp where unsupported)
  o.drawImage(tmp, 0, 0);
  return out.toDataURL();
}

function hatchImage() {
  const c = document.createElement("canvas"); c.width = 10; c.height = 10;
  const g = c.getContext("2d")!; g.strokeStyle = "rgba(244,241,234,0.42)"; g.lineWidth = 1.2;
  g.beginPath(); g.moveTo(-1, 11); g.lineTo(11, -1); g.moveTo(-1, 1); g.lineTo(1, -1); g.moveTo(9, 11); g.lineTo(11, 9); g.stroke();
  return g.getImageData(0, 0, 10, 10);
}

const square = (c: GridCell, step: number) => ({
  type: "Feature" as const, properties: {}, geometry: { type: "Polygon" as const, coordinates: [[[c.lon - step / 2, c.lat - step / 2], [c.lon + step / 2, c.lat - step / 2], [c.lon + step / 2, c.lat + step / 2], [c.lon - step / 2, c.lat + step / 2], [c.lon - step / 2, c.lat - step / 2]]] },
});

interface Hover { x: number; y: number; i: number }

export default function WhereMap({ data, onOpenCase }: { data: CaseResponse; onOpenCase: (lat: number, lon: number) => void }) {
  const { place, period } = data;
  const bbox = useMemo(() => defaultBbox(place.lat, place.lon), [place.lat, place.lon]);
  const [variable, setVariable] = useState<VariableId>(data.witnesses[0]?.variable ?? "T2M");
  const [grid, setGrid] = useState<GridResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [k, setK] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [hover, setHover] = useState<Hover | null>(null);
  const [ready, setReady] = useState(false);

  const boxRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const cache = useRef(new Map<string, GridResponse>());
  const first = useRef(true);
  const fitted = useRef(false);
  const live = useRef({ grid: null as GridResponse | null, onOpenCase });
  live.current = { grid, onOpenCase };
  const vals = useValues(grid);

  // ---- load a grid per witness (cached) ----
  useEffect(() => {
    let stale = false;
    const hit = cache.current.get(variable);
    if (hit) { setGrid(hit); return; }
    setLoading(true); setErr(null);
    getGrid(variable, bbox, data)
      .then((g) => { if (stale) return; cache.current.set(variable, g); const isFirst = first.current; first.current = false; setGrid(g); setK((o) => (isFirst ? g.years.length - 1 : Math.min(o, g.years.length - 1))); })
      .catch((e) => !stale && setErr((e as Error).message))
      .finally(() => !stale && setLoading(false));
    return () => { stale = true; };
  }, [variable, bbox, data]);

  // ---- play button ----
  useEffect(() => {
    if (!playing || !grid) return;
    const last = grid.years.length - 1;
    const id = setInterval(() => setK((o) => { if (o >= last) { setPlaying(false); return last; } return o + 1; }), 260);
    return () => clearInterval(id);
  }, [playing, grid]);

  // ---- map, created once ----
  useEffect(() => {
    if (!boxRef.current) return;
    const map = new maplibregl.Map({
      container: boxRef.current, center: [place.lon, place.lat], zoom: 5.4, attributionControl: { compact: true }, dragRotate: false, pitchWithRotate: false,
      style: { version: 8, sources: { base: { type: "raster", tileSize: 256, tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"], maxzoom: 16, attribution: "Tiles © Esri, HERE, Garmin, OpenStreetMap contributors" } },
        layers: [{ id: "bg", type: "background", paint: { "background-color": "#05070B" } }, { id: "base", type: "raster", source: "base", paint: { "raster-opacity": 0.9 } }] },
    });
    mapRef.current = map;
    map.touchZoomRotate.disableRotation();
    map.on("load", () => setReady(true));
    new maplibregl.Marker({ element: targetEl() }).setLngLat([place.lon, place.lat]).addTo(map);
    map.on("mousemove", (e) => {
      const g = live.current.grid; if (!g) return;
      const [w, s, ee, n] = g.bbox, col = Math.floor((e.lngLat.lng - w) / g.step), row = Math.floor((n - e.lngLat.lat) / g.step);
      const i = g.cells.findIndex((c) => Math.floor((c.lon - w) / g.step) === col && Math.floor((n - c.lat) / g.step) === row);
      const inside = e.lngLat.lng >= w && e.lngLat.lng <= ee && e.lngLat.lat >= s && e.lngLat.lat <= n && i >= 0;
      map.getCanvas().style.cursor = inside ? "pointer" : "";
      setHover(inside ? { x: e.point.x, y: e.point.y, i } : null);
      const src = map.getSource("hov") as maplibregl.GeoJSONSource | undefined;
      src?.setData({ type: "FeatureCollection", features: inside ? [square(g.cells[i], g.step)] : [] });
    });
    map.on("mouseout", () => setHover(null));
    map.on("click", (e) => {
      const g = live.current.grid; if (!g) return;
      const [w, , , n] = g.bbox, col = Math.floor((e.lngLat.lng - w) / g.step), row = Math.floor((n - e.lngLat.lat) / g.step);
      const c = g.cells.find((c) => Math.floor((c.lon - w) / g.step) === col && Math.floor((n - c.lat) / g.step) === row);
      if (c) live.current.onOpenCase(c.lat, c.lon);
    });
    return () => { map.remove(); mapRef.current = null; setReady(false); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- (re)build the data layers when the grid changes ----
  const kRef = useRef(k); kRef.current = k;
  useEffect(() => {
    const map = mapRef.current; if (!map || !ready || !grid || !vals) return;
    const [w, s, e, n] = grid.bbox;
    for (const id of ["hov-line", "nosig-hatch", "heat"]) if (map.getLayer(id)) map.removeLayer(id);
    for (const id of ["hov", "nosig", "heat"]) if (map.getSource(id)) map.removeSource(id);
    if (!map.hasImage("hatch")) map.addImage("hatch", hatchImage());
    map.addSource("heat", { type: "image", url: heatURL(grid, vals, kRef.current), coordinates: [[w, n], [e, n], [e, s], [w, s]] });
    map.addLayer({ id: "heat", type: "raster", source: "heat", paint: { "raster-resampling": "linear", "raster-fade-duration": 0 } });
    map.addSource("nosig", { type: "geojson", data: { type: "FeatureCollection", features: grid.cells.filter((c) => !c.significant).map((c) => square(c, grid.step)) } });
    map.addLayer({ id: "nosig-hatch", type: "fill", source: "nosig", paint: { "fill-pattern": "hatch", "fill-opacity": 0.8 } });
    map.addSource("hov", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    map.addLayer({ id: "hov-line", type: "line", source: "hov", paint: { "line-color": "#F4F1EA", "line-width": 2 } });
    if (!fitted.current) { map.fitBounds([[w, s], [e, n]], { padding: 14, duration: 0 }); fitted.current = true; }
  }, [ready, grid, vals]);

  // ---- slider frames ----
  useEffect(() => {
    const map = mapRef.current; if (!map || !ready || !grid || !vals) return;
    const src = map.getSource("heat") as maplibregl.ImageSource | undefined;
    const [w, s, e, n] = grid.bbox;
    src?.updateImage({ url: heatURL(grid, vals, k), coordinates: [[w, n], [e, n], [e, s], [w, s]] });
  }, [k, ready, grid, vals]);

  const cell = hover && grid ? grid.cells[hover.i] : null;
  const last = grid ? grid.years.length - 1 : 0;
  const describe = (c: GridCell, i: number) => {
    if (!grid || !vals) return "";
    const unit = grid.display_unit, word = (v: number) => (v >= 0 ? grid.words.up : grid.words.down);
    if (k === last) return c.significant ? `Here: ${fmt(c.value, unit)} ${word(c.value)} since ${period.start} · ${c.verdict}` : `Here: no clear change since ${period.start} · NOT PROVEN`;
    const v = vals.disp[i][k];
    return `By ${grid.years[k]}: ${fmt(v, unit)} ${word(v)} than in ${period.start}${c.significant ? "" : " · no clear trend overall"}`;
  };

  const mock = grid?.data_label.origin === "mock";
  const upWord = grid?.words.up ?? "rising", downWord = grid?.words.down ?? "falling";

  return (
    <section className="relative bg-night px-4 py-24 sm:px-8">
      <div className="mx-auto max-w-6xl">
        <p className="font-mono text-xs tracking-[0.5em] text-paper/50">WHERE</p>
        <h2 className="mt-3 font-display text-[clamp(1.6rem,4vw,3rem)] font-black leading-tight">Where is it changing?</h2>

        <div className="mt-6 flex flex-wrap gap-2">
          {data.witnesses.map((w) => (
            <button key={w.variable} onClick={() => setVariable(w.variable)}
              className={`rounded-full border px-4 py-1.5 font-mono text-xs transition ${variable === w.variable ? "border-heat bg-heat/15 text-heat" : "border-white/15 text-paper/70 hover:border-white/40"}`}>{w.label}</button>
          ))}
        </div>

        <div className="relative mt-5 overflow-hidden rounded-xl border border-white/10 shadow-[0_0_60px_rgba(0,0,0,.6)]">
          <div ref={boxRef} className="h-[62vh] min-h-[380px] w-full bg-[#05070B]" />

          {/* legend, in plain words */}
          <div className="pointer-events-none absolute bottom-3 left-3 z-10 max-w-[15rem] rounded-lg border border-white/10 bg-black/65 p-3 font-mono text-[11px] leading-5 text-paper/85 backdrop-blur">
            <p className="mb-1 text-paper/50">CHANGE SINCE {period.start}</p>
            <p><span className="mr-2 inline-block h-3 w-3 rounded-sm align-middle" style={{ background: "rgb(124,200,255)" }} />{upWord}</p>
            <p><span className="mr-2 inline-block h-3 w-3 rounded-sm align-middle" style={{ background: "rgb(255,138,61)" }} />{downWord}</p>
            <p><span className="mr-2 inline-block h-3 w-3 rounded-sm border border-paper/40 align-middle" style={{ background: "repeating-linear-gradient(45deg, rgba(244,241,234,.5) 0 1px, transparent 1px 4px)" }} />no clear change</p>
            <p className="mt-1 text-paper/50">stronger colour = bigger change</p>
          </div>
          <div className="pointer-events-none absolute right-3 top-3 z-10 rounded bg-black/65 px-3 py-1.5 text-right font-mono text-[11px] text-paper/70 backdrop-blur">
            click any cell to open a case there
          </div>
          {loading && <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/40 font-mono text-xs tracking-widest text-paper/70">LOADING GRID…</div>}
          {err && <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/60 font-mono text-xs text-stamp">{err}</div>}

          {cell && hover && (
            <div className="pointer-events-none absolute z-20 max-w-[16rem] rounded-md border border-white/15 bg-black/85 px-3 py-2 font-mono text-[11px] leading-4 text-paper shadow-xl"
              style={{ left: Math.min(hover.x + 14, (boxRef.current?.clientWidth ?? 600) - 260), top: Math.max(8, hover.y - 8) }}>
              {describe(cell, hover.i)}
              <span className="mt-1 block text-[9px] text-paper/45">{cell.lat.toFixed(2)}°N {cell.lon.toFixed(2)}°E · FDR q = {cell.q < 0.001 ? "<0.001" : cell.q.toFixed(3)}</span>
            </div>
          )}
        </div>

        {/* time slider */}
        <div className="mt-4 flex items-center gap-4 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
          <button aria-label={playing ? "Pause" : "Play"} disabled={!grid}
            onClick={() => { if (!grid) return; if (!playing && k >= last) setK(0); setPlaying((p) => !p); }}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-heat text-night transition hover:brightness-110 disabled:opacity-40">
            {playing ? <span className="text-sm font-black">❚❚</span> : <span className="ml-0.5 text-sm">▶</span>}
          </button>
          <input type="range" min={0} max={last} value={Math.min(k, last)} disabled={!grid} onChange={(e) => { setPlaying(false); setK(+e.target.value); }}
            className="min-w-0 flex-1 accent-[#FF8A3D]" aria-label="Year" />
          <span className="w-24 shrink-0 text-right font-display text-xl font-black tabular-nums">{grid ? grid.years[Math.min(k, last)] : "—"}</span>
        </div>
        <p className="mt-3 font-mono text-[11px] text-paper/45">
          {mock ? "⚠ SIMULATED GRID · GET /grid not available yet · " : grid?.data_label.origin === "cache" ? "cached data · " : grid ? "live NASA data · " : ""}
          each cell is tested separately, then corrected for many tests (Benjamini–Hochberg FDR). Hatched = could be chance. POWER is ~0.5° reanalysis.
        </p>
      </div>
    </section>
  );
}
