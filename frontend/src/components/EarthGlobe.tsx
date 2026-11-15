import { useEffect, useMemo, useRef, useState } from "react";
import GlobeGL from "react-globe.gl";
import type * as THREE from "three";
import { createCinematic, type Cinematic, type QualityLevel } from "./globe/cinematic";

export interface GlobePlace { lat: number; lon: number; name: string }
const GOLD = "255,200,87";

export type GlobeStatus = "locked" | "investigating";
interface Props {
  lat: number; lon: number; name: string;
  status: GlobeStatus;                 // investigating = a place was just picked and its case is loading
  zoomed: boolean;                     // a case (or pick) exists: fly in closer
  busy: boolean;                       // ignore clicks while a case loads
  onPick: (lat: number, lon: number) => void;
  places: GlobePlace[];                // real places that get a golden radar ping: demo cases + places already investigated
}

const fmtCoord = (lat: number, lon: number) =>
  `${Math.abs(lat).toFixed(2)}° ${lat >= 0 ? "N" : "S"} · ${Math.abs(lon).toFixed(2)}° ${lon >= 0 ? "E" : "W"}`;

const FILL = 0.62;   // globe diameter / canvas size at ALT
const ALT = 2.6;     // camera altitude that gives that fill (fov 50)
const ALT_ZOOM = 1.9; // closer, once a place is chosen

function useSize() {
  const get = () => {
    const W = window.innerWidth, H = window.innerHeight;
    // D = visible globe diameter, (cx, cy) = where its centre sits on screen
    const mobile = W < 768;
    const D = mobile ? W * 1.15 : Math.min(H * 0.92, W * 0.62);
    const cx = mobile ? W / 2 : W * 0.68, cy = mobile ? H * 0.76 : H * 0.48;
    const S = D / FILL;
    return { S, left: cx - S / 2, top: cy - S / 2 };
  };
  const [s, setS] = useState(get);
  useEffect(() => { const f = () => setS(get()); window.addEventListener("resize", f); return () => window.removeEventListener("resize", f); }, []);
  return s;
}

const STEPS = ["Pulling NASA POWER data", "Removing seasonality", "Running trend tests", "Pinning clues to the board"];

function Marker({ name, lat, lon, status }: { name: string; lat: number; lon: number; status: GlobeStatus }) {
  const inv = status === "investigating";
  const [step, setStep] = useState(0);
  useEffect(() => {
    if (!inv) { setStep(0); return; }
    const id = setInterval(() => setStep((s) => (s + 1) % STEPS.length), 1700);
    return () => clearInterval(id);
  }, [inv]);
  return (
    <div className="pointer-events-none relative h-0 w-0">
      {/* expanding CSS rings: faster while investigating */}
      {[0, 0.8, 1.6].map((d) => (
        <span key={d} className="absolute -left-6 -top-6 h-12 w-12 rounded-full border-2 border-heat"
          style={{ animation: `lock-ring ${inv ? 1.3 : 2.4}s ${d * (inv ? 0.5 : 1)}s ease-out infinite` }} />
      ))}
      {/* thin crosshair lens */}
      <svg className="absolute -left-14 -top-14" width="112" height="112" viewBox="-56 -56 112 112" fill="none" stroke="#FF8A3D" strokeWidth="1">
        <circle r="38" strokeOpacity=".85" />
        <circle r="50" strokeOpacity=".3" strokeDasharray="2 6" />
        <path d="M-56 0H-14M14 0H56M0 -56V-14M0 14V56" strokeOpacity=".9" />
        {inv && <g className="scan-spin"><circle r="62" strokeOpacity=".9" strokeWidth="1.5" strokeDasharray="18 40" /><circle r="44" strokeOpacity=".7" strokeDasharray="4 10" /></g>}
      </svg>
      {/* bright core */}
      <span className="absolute -left-[7px] -top-[7px] h-[14px] w-[14px] rounded-full bg-heat"
        style={{ boxShadow: "0 0 10px 3px #FF8A3D, 0 0 28px 8px rgba(255,138,61,.7)", animation: `lock-core ${inv ? 0.6 : 1.2}s ease-in-out infinite` }} />
      {/* HUD label: centred under the marker so it can never run off the right edge */}
      <div className="absolute left-1/2 top-16 w-max max-w-[280px] -translate-x-1/2 rounded border border-heat/50 bg-black/70 px-3 py-2 text-center font-mono text-[11px] leading-4 tracking-widest text-heat backdrop-blur-sm">
        {inv ? (
          <>
            <b className="block text-paper">INVESTIGATING<span className="dots" /></b>
            <span className="block whitespace-nowrap">{fmtCoord(lat, lon)}</span>
            <span className="mt-1 block text-[10px] normal-case tracking-normal text-paper/70">{STEPS[step]}…</span>
          </>
        ) : (
          <>
            <b className="block text-paper">LOCKED ON TARGET</b>
            {name && <span className="block">{name.toUpperCase()}</span>}
            <span className="block whitespace-nowrap">{fmtCoord(lat, lon)}</span>
          </>
        )}
      </div>
    </div>
  );
}

export default function EarthGlobe({ lat, lon, name, status, zoomed, busy, onPick, places }: Props) {
  const ref = useRef<any>(null);
  const { S, left, top } = useSize();
  const pings = useMemo(() => places.map((p) => ({ lat: p.lat, lng: p.lon })), [places]);
  const intro = useRef(true);

  // cinematic layer (day/night shader, ocean glint, cloud shells, stars, bloom) + an FPS watchdog that steps the quality down
  const cine = useRef<Cinematic | null>(null);
  const [globeMat, setGlobeMat] = useState<THREE.Material | undefined>(undefined);
  useEffect(() => {
    const g = ref.current; if (!g) return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const phone = window.matchMedia?.("(pointer: coarse)").matches || window.innerWidth < 768;
    // ?quality=0|1|2 forces a level and turns the FPS watchdog off (for testing)
    const forcedRaw = new URLSearchParams(window.location.search).get("quality");
    const forced = forcedRaw !== null && ["0", "1", "2"].includes(forcedRaw) ? (Number(forcedRaw) as QualityLevel) : null;
    const c = createCinematic(g, { quality: forced ?? (phone ? 1 : 2), reduced });
    cine.current = c; setGlobeMat(c.material);
    if (new URLSearchParams(window.location.search).has("debug")) { (window as any).__globe = g; (window as any).__cine = c; } // test hook (?debug)
    let raf = 0, last = performance.now(), acc = 0, frames = 0, t0 = last, since = last;
    const loop = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000); last = now;
      c.update(dt, reduced);
      // average fps over ~2 s windows after a 3 s warm-up; drop one quality level when it sags below ~46 fps
      acc += dt; frames++;
      if (acc >= 2) {
        const fps = frames / acc; acc = 0; frames = 0;
        if (forced === null && now - t0 > 3000 && now - since > 2500 && fps < 46 && c.quality > 0) { c.setQuality((c.quality - 1) as QualityLevel); since = now; }
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => { cancelAnimationFrame(raf); c.dispose(); cine.current = null; };
  }, []);

  // drag to rotate; scroll stays with the page
  useEffect(() => {
    const c = ref.current?.controls(); if (!c) return;
    c.noZoom = true; c.noPan = true; c.noRotate = false; c.rotateSpeed = 0.8; // trackball controls
    c.enableZoom = false; c.enablePan = false; c.enableRotate = true; c.autoRotate = false;
  }, []);

  // camera: slow glide-in on first load, then a smooth flight to every new target
  useEffect(() => {
    const g = ref.current; if (!g) return;
    const alt = zoomed ? ALT_ZOOM : ALT;
    if (intro.current) {
      g.pointOfView({ lat, lng: lon - 60, altitude: ALT }, 0);
      const t = setTimeout(() => { intro.current = false; g.pointOfView({ lat, lng: lon, altitude: alt }, zoomed ? 2200 : 6000); }, 50);
      return () => clearTimeout(t);
    }
    g.pointOfView({ lat, lng: lon, altitude: alt }, 1800);
  }, [lat, lon, zoomed]);

  // pin the HUD marker to the projected position of (lat, lon) every frame; hide it when it turns to the far side
  const markerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const g = ref.current, el = markerRef.current;
      if (g && el) {
        const p = g.getScreenCoords(lat, lon, 0.01);
        const cam = g.camera().position, c = g.getCoords(lat, lon, 0), R = g.getGlobeRadius();
        const d = Math.hypot(cam.x, cam.y, cam.z), dot = (cam.x * c.x + cam.y * c.y + cam.z * c.z) / (d * Math.hypot(c.x, c.y, c.z));
        const facing = dot > R / d + 0.02; // above the horizon as seen from the camera
        if (p && facing) { el.style.transform = `translate(${p.x}px, ${p.y}px)`; el.style.opacity = "1"; }
        else el.style.opacity = "0";
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [lat, lon]);

  return (
    <div className={`globe-wrap pointer-events-auto absolute ${busy ? "busy" : ""}`} style={{ left, top, width: S, height: S, WebkitMaskImage: "radial-gradient(circle closest-side at 50% 50%, #000 78%, transparent 100%)", maskImage: "radial-gradient(circle closest-side at 50% 50%, #000 78%, transparent 100%)" }}>
      <GlobeGL ref={ref} width={S} height={S}
        backgroundColor="#05070B" rendererConfig={{ antialias: true, alpha: false, powerPreference: "high-performance" }}
        globeMaterial={globeMat} showAtmosphere atmosphereColor="#5aa8ff" atmosphereAltitude={0.17}
        onGlobeClick={({ lat: la, lng }: { lat: number; lng: number }) => { if (!busy) onPick(+la.toFixed(3), +(((lng + 540) % 360) - 180).toFixed(3)); }}
        pointsData={pings} pointLat="lat" pointLng="lng" pointColor={() => `rgb(${GOLD})`} pointRadius={0.22} pointAltitude={0.004} pointResolution={10}
        ringsData={pings} ringLat="lat" ringLng="lng" ringColor={() => (t: number) => `rgba(${GOLD},${(1 - t) * 0.9})`} ringMaxRadius={2.6} ringPropagationSpeed={1.6} ringRepeatPeriod={2200} />
      {/* HTML marker overlay, positioned from the globe's own projection */}
      <div ref={markerRef} className="pointer-events-none absolute left-0 top-0 opacity-0"><Marker name={name} lat={lat} lon={lon} status={status} /></div>
    </div>
  );
}
