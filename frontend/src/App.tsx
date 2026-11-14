import { lazy, Suspense, useRef, useState } from "react";
import { openCase, openManualCase } from "./api/client";
import type { CaseResponse, ManualCaseRequest } from "./api/types";
import Hero from "./components/Hero";
import EvidenceBoard from "./components/EvidenceBoard";
import Verdict from "./components/Verdict";
import Lifetime from "./components/Lifetime";
import Twist from "./components/Twist";
import Game from "./components/Game";
import Report from "./components/Report";
const WhereMap = lazy(() => import("./components/WhereMap"));
const WitnessPicker = lazy(() => import("./components/WitnessPicker"));

export default function App() {
  const [data, setData] = useState<CaseResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [picker, setPicker] = useState(false);
  const boardRef = useRef<HTMLDivElement>(null);

  async function run(make: () => Promise<CaseResponse>) {
    setLoading(true); setError(null);
    try {
      const res = await make();
      setPicker(false);
      setData(res);
      setTimeout(() => boardRef.current?.scrollIntoView({ behavior: "smooth" }), 1800); // let the camera fly first
    } catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  }
  const submit = (q: string, loc?: { lat: number; lon: number }) => run(() => openCase(q, loc));
  const submitManual = (req: ManualCaseRequest) => run(() => openManualCase(req));

  return (
    <>
      <Hero onSubmit={submit} onPick={() => setPicker(true)} loading={loading} error={error} target={data?.place ?? null} />
      <div ref={boardRef}>{data && <EvidenceBoard data={data} onPick={() => setPicker(true)} />}</div>
      {data && <><Verdict data={data} />
        <Suspense fallback={null}><WhereMap key={data.case_id} data={data} onOpenCase={(lat, lon) => submit(`What is changing at ${lat.toFixed(2)}°N, ${lon.toFixed(2)}°E?`, { lat, lon })} /></Suspense>
        <Twist data={data} /><Lifetime data={data} /><Game data={data} /><Report data={data} /></>}
      {picker && <Suspense fallback={null}><WitnessPicker initial={data ? { name: data.place.name.split(",")[0], name_ar: data.place.name_ar, lat: data.place.lat, lon: data.place.lon } : null} onClose={() => setPicker(false)} onSubmit={submitManual} busy={loading} error={error} /></Suspense>}
    </>
  );
}
