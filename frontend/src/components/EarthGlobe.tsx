import { useEffect, useMemo, useRef, useState } from "react";
import GlobeGL from "react-globe.gl";

const TEX = "https://unpkg.com/three-globe/example/img";

interface Props { lat: number; lon: number; name: string; locked: boolean }

const fmtCoord = (lat: number, lon: number) =>
  `${Math.abs(lat).toFixed(1)}° ${lat >= 0 ? "N" : "S"} · ${Math.abs(lon).toFixed(1)}° ${lon >= 0 ? "E" : "W"}`;

const FILL = 0.62;   // globe diameter / canvas size at ALT
const ALT = 2.6;     // camera altitude that gives that fill (fov 50)

function useSize() {
  const get = () => {
    const W = window.innerWidth, H = window.innerHeight;
    // D = visible globe diameter, (cx, cy) = where its centre sits on screen
    const mobile = W < 768;
    const D = mobile ? W * 1.15 : Math.min(H * 0.92, W * 0.62);
    const cx = mobile ? W / 2 : W * 0.68, cy = mobile ? H * 0.76 : H * 0.48;
    const S = D / FILL;
    return { S, left: cx - S / 2, top: cy - S / 2, mobile };
  };
  const [s, setS] = useState(get);
  useEffect(() => { const f = () => setS(get()); window.addEventListener("resize", f); return () => window.removeEventListener("resize", f); }, []);
  return s;
}

function Marker({ name, lat, lon, mobile }: { name: string; lat: number; lon: number; mobile: boolean }) {
  return (
    <div className="pointer-events-none relative h-0 w-0">
      {/* expanding CSS rings */}
      {[0, 0.8, 1.6].map((d) => (
        <span key={d} className="absolute -left-6 -top-6 h-12 w-12 rounded-full border-2 border-heat"
          style={{ animation: `lock-ring 2.4s ${d}s ease-out infinite` }} />
      ))}
      {/* thin crosshair lens */}
      <svg className="absolute -left-14 -top-14" width="112" height="112" viewBox="-56 -56 112 112" fill="none" stroke="#FF8A3D" strokeWidth="1">
        <circle r="38" strokeOpacity=".85" />
        <circle r="50" strokeOpacity=".3" strokeDasharray="2 6" />
        <path d="M-56 0H-14M14 0H56M0 -56V-14M0 14V56" strokeOpacity=".9" />
      </svg>
      {/* bright core */}
      <span className="absolute -left-[7px] -top-[7px] h-[14px] w-[14px] rounded-full bg-heat"
        style={{ boxShadow: "0 0 10px 3px #FF8A3D, 0 0 28px 8px rgba(255,138,61,.7)", animation: "lock-core 1.2s ease-in-out infinite" }} />
      {/* HUD label: centred under the marker so it can never run off the right edge */}
      <div className="absolute left-1/2 top-16 w-max max-w-[280px] -translate-x-1/2 rounded border border-heat/50 bg-black/60 px-3 py-2 text-center font-mono text-[11px] leading-4 tracking-widest text-heat backdrop-blur-sm">
        <b className="block text-paper">LOCKED ON TARGET</b>
        <span className="block">{name.toUpperCase()}</span>
        <span className="block whitespace-nowrap">{fmtCoord(lat, lon)}</span>
      </div>
    </div>
  );
}

export default function EarthGlobe({ lat, lon, name, locked }: Props) {
  const ref = useRef<any>(null);
  const { S, left, top, mobile } = useSize();
  const markers = useMemo(() => [{ lat, lng: lon }], [lat, lon]);

  useEffect(() => {
    const g = ref.current; if (!g) return;
    const c = g.controls();
    c.enableZoom = false; c.enablePan = false; c.enableRotate = false; c.autoRotate = false;
    // slow drift in from 60° west, then stop with the target exactly centred
    g.pointOfView({ lat, lng: lon - 60, altitude: ALT }, 0);
    const t = setTimeout(() => g.pointOfView({ lat, lng: lon, altitude: ALT }, locked ? 2200 : 6000), 50);
    return () => clearTimeout(t);
  }, [lat, lon, locked]);

  // pin the HUD marker to the real projected position of (lat, lon) every frame, so it can never drift off Azraq
  const markerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const g = ref.current, el = markerRef.current;
      if (g && el) {
        const p = g.getScreenCoords(lat, lon, 0.01);
        if (p) { el.style.transform = `translate(${p.x}px, ${p.y}px)`; el.style.opacity = "1"; }
        else el.style.opacity = "0";
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [lat, lon]);

  return (
    <div className="absolute" style={{ left, top, width: S, height: S }}>
      <GlobeGL ref={ref} width={S} height={S}
        backgroundColor="rgba(0,0,0,0)" globeImageUrl={`${TEX}/earth-blue-marble.jpg`} bumpImageUrl={`${TEX}/earth-topology.png`}
        showAtmosphere atmosphereColor="#7CC8FF" atmosphereAltitude={0.22}
        ringsData={markers} ringColor={() => (t: number) => `rgba(255,138,61,${1 - t})`} ringMaxRadius={5} ringPropagationSpeed={2.5} ringRepeatPeriod={1200} />
      {/* HTML marker overlay, positioned from the globe's own projection */}
      <div ref={markerRef} className="pointer-events-none absolute left-0 top-0 opacity-0"><Marker name={name} lat={lat} lon={lon} mobile={mobile} /></div>
    </div>
  );
}


