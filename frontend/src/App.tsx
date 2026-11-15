import { lazy, Suspense, useRef, useState } from "react";
import { inCachedGrid, openCase, openManualCase } from "./api/client";
import type { CaseResponse, ManualCaseRequest } from "./api/types";
import Hero from "./components/Hero";
import EvidenceBoard from "./components/EvidenceBoard";
import Verdict from "./components/Verdict";
import Lifetime from "./components/Lifetime";
import Twist from "./components/Twist";
import Game from "./components/Game";
import Report from "./components/Report";
import ChatPanel from "./components/ChatPanel";
import Footer from "./components/Footer";
import type { GlobePlace } from "./components/EarthGlobe";
const WhereMap = lazy(() => import("./components/WhereMap"));
const WitnessPicker = lazy(() => import("./components/WitnessPicker"));

// real places that always carry a golden radar ping on the globe
const DEMO_PLACES: GlobePlace[] = [
  { name: "Azraq", lat: 31.88, lon: 36.83 },
  { name: "Irbid", lat: 32.556, lon: 35.85 },
  { name: "Dead Sea", lat: 31.5, lon: 35.5 },
];
const KEY = "etd.visited";
const loadVisited = (): GlobePlace[] => { try { return JSON.parse(localStorage.getItem(KEY) ?? "[]"); } catch { return []; } };

export default function App() {
  const [visited, setVisited] = useState<GlobePlace[]>(loadVisited);
  const [data, setData] = useState<CaseResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [picker, setPicker] = useState(false);
  const [pending, setPending] = useState<{ lat: number; lon: number } | null>(null); // clicked on the globe, case loading
  const boardRef = useRef<HTMLDivElement>(null);

  async function run(make: () => Promise<CaseResponse>, scrollDelay = 1800) {
    setLoading(true); setError(null);
    try {
      const res = await make();
      setPicker(false);
      setData(res);
      // remember the place so it keeps a golden ping on the globe
      setVisited((v) => {
        const near = (a: GlobePlace) => Math.hypot(a.lat - res.place.lat, a.lon - res.place.lon) < 0.15;
        if (DEMO_PLACES.some(near) || v.some(near)) return v;
        const n = [...v, { name: res.place.name.split(",")[0], lat: res.place.lat, lon: res.place.lon }].slice(-12);
        try { localStorage.setItem(KEY, JSON.stringify(n)); } catch { /* private mode */ }
        return n;
      });
      setTimeout(() => boardRef.current?.scrollIntoView({ behavior: "smooth" }), scrollDelay); // let the camera fly first
    } catch (e) { setError((e as Error).message); }
    finally { setLoading(false); setPending(null); }
  }
  const submit = (q: string, loc?: { lat: number; lon: number }) => run(() => openCase(q, loc));
  // click on the globe: fly in, drop the target, "investigating…", then the board
  const pickOnGlobe = (lat: number, lon: number) => {
    if (loading) return;
    setPending({ lat, lon });
    run(() => openCase(`What is changing at ${lat.toFixed(2)}°N, ${lon.toFixed(2)}°E?`, { lat, lon }), 700);
  };
  const submitManual = (req: ManualCaseRequest) => run(() => openManualCase(req));

  return (
    <>
      <Hero onSubmit={submit} onPick={() => setPicker(true)} loading={loading} error={error} target={data?.place ?? null} pending={pending} onGlobePick={pickOnGlobe} places={[...DEMO_PLACES, ...visited]} />
      <div ref={boardRef}>{data && <EvidenceBoard data={data} onPick={() => setPicker(true)} />}</div>
      {data && <><Verdict data={data} />
        {inCachedGrid(data.place.lat, data.place.lon) && <Suspense fallback={null}><WhereMap key={data.case_id} data={data} onOpenCase={(lat, lon) => submit(`What is changing at ${lat.toFixed(2)}°N, ${lon.toFixed(2)}°E?`, { lat, lon })} /></Suspense>}
        <Twist data={data} /><Lifetime data={data} /><Game data={data} /><Report data={data} /></>}
      {data && <ChatPanel key={data.case_id} data={data} />}
      <Footer />
      {picker && <Suspense fallback={null}><WitnessPicker initial={data ? { name: data.place.name.split(",")[0], lat: data.place.lat, lon: data.place.lon } : null} onClose={() => setPicker(false)} onSubmit={submitManual} busy={loading} error={error} /></Suspense>}
    </>
  );
}
