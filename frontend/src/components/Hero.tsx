import { lazy, Suspense, useState } from "react";
import { motion } from "framer-motion";
import type { CaseResponse } from "../api/types";
import Ticker from "./Ticker";

const Globe = lazy(() => import("./EarthGlobe"));
const LINES = ["THE EARTH", "IS LEAVING", "CLUES."];

interface Props { onSubmit: (q: string) => void; onPick: () => void; loading: boolean; error: string | null; target: CaseResponse["place"] | null; }

export default function Hero({ onSubmit, onPick, loading, error, target }: Props) {
  const [q, setQ] = useState("");
  const place = target ?? { name: "Azraq, Jordan", lat: 31.88, lon: 36.83 };
  return (
    <section className="relative h-screen min-h-[640px] overflow-hidden bg-night">
      <div className="stars absolute inset-0 opacity-80" />
      <div className="absolute -left-40 top-10 h-[60vh] w-[60vh] rounded-full bg-cool/10 blur-3xl" />
      <div className="absolute inset-0 pointer-events-none overflow-hidden [mask-image:linear-gradient(to_bottom,black_82%,transparent_97%)]"><Suspense fallback={null}><Globe lat={place.lat} lon={place.lon} name={place.name} locked={!!target} /></Suspense></div>
      <div className="pointer-events-none absolute inset-0 z-[5] bg-gradient-to-r from-night via-night/85 to-transparent md:via-night/70 md:from-night/95 md:[mask-image:linear-gradient(to_right,black_35%,transparent_62%)] max-md:bg-gradient-to-b max-md:from-night max-md:via-night/80 max-md:to-transparent" />

            <div className="relative z-10 flex h-full flex-col items-start justify-start px-6 pt-[14vh] text-left md:justify-center md:px-[6vw] md:pt-0 md:max-w-[52vw]">
        <h1 className="font-display text-[clamp(1.8rem,4.6vw,4.6rem)] font-black leading-[1.05] drop-shadow-[0_0_30px_rgba(0,0,0,.8)]">
          {LINES.map((l, i) => (
            <motion.span key={l} className="block" initial={{ opacity: 0, filter: "blur(18px)", y: 20 }}
              animate={{ opacity: 1, filter: "blur(0px)", y: 0 }} transition={{ delay: 0.4 + i * 0.5, duration: 0.9 }}>
              {l}
            </motion.span>
          ))}
        </h1>
        <motion.form initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 2.1 }}
          onSubmit={(e) => { e.preventDefault(); if (q.trim() && !loading) onSubmit(q.trim()); }}
          className="mt-8 flex w-full max-w-lg items-center gap-2 rounded-full border border-white/20 bg-white/10 p-2 pl-6 backdrop-blur-xl shadow-[0_0_40px_rgba(124,200,255,.15)]">
          <input value={q} onChange={(e) => setQ(e.target.value)} dir="auto" placeholder='Open a case… "Is Azraq drying up?"  /  هل إربد عم تسخن؟'
            className="min-w-0 flex-1 bg-transparent font-body text-sm text-paper placeholder:text-paper/40 focus:outline-none sm:text-base" />
          <button disabled={loading} className="rounded-full bg-heat px-5 py-2 font-mono text-xs font-semibold text-night transition hover:brightness-110 disabled:opacity-50">
            {loading ? "OPENING…" : "OPEN CASE"}
          </button>
        </motion.form>
        {error && <p className="mt-3 font-mono text-xs text-stamp">{error}</p>}
        <button type="button" onClick={() => onSubmit("Is Azraq drying up?")} className="mt-4 font-mono text-[11px] tracking-widest text-cool/70 underline-offset-4 hover:underline">
          or run the demo case: Azraq →
        </button>
        <button type="button" onClick={onPick} className="mt-2 font-mono text-[11px] tracking-widest text-heat/80 underline-offset-4 hover:underline">
          or pick the witnesses yourself →
        </button>
      </div>
      <Ticker />
    </section>
  );
}


