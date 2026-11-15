import { useEffect, useRef, useState } from "react";
import { motion, useInView, useReducedMotion } from "framer-motion";
import type { CaseResponse, LifetimeItem, LifetimeResponse } from "../api/types";
import { getLifetime } from "../api/client";
import { digitsFor, isOrange, ORANGE_HEX, BLUE_HEX } from "../lib/format";
import Stamp from "./Stamp";

function useCountUp(target: number, active: boolean, reduced: boolean, ms = 1700) {
  const [v, setV] = useState(reduced ? target : 0);
  useEffect(() => {
    if (reduced) { setV(target); return; }
    if (!active) return;
    let raf = 0, t0 = 0;
    const tick = (t: number) => { if (!t0) t0 = t; const k = Math.min(1, (t - t0) / ms); setV(target * (1 - Math.pow(1 - k, 3))); if (k < 1) raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, active, reduced, ms]);
  return v;
}

function Giant({ item, i, active, reduced, birth }: { item: LifetimeItem; i: number; active: boolean; reduced: boolean; birth: number }) {
  const v = useCountUp(item.value, active, reduced);
  const d = digitsFor(item.display_unit, item.value);
  const confirmed = item.verdict === "CONFIRMED";
  const color = !confirmed ? "#9aa3b2" : isOrange(item.variable, item.value) ? ORANGE_HEX : BLUE_HEX;
  const sign = item.value > 0 ? "+" : item.value < 0 ? "−" : "";
  return (
    <motion.div initial={reduced ? false : { opacity: 0, y: 30 }} animate={active ? { opacity: 1, y: 0 } : {}} transition={{ delay: 0.2 + i * 0.25, duration: 0.7 }}
      className="flex flex-col items-center text-center" title={`Source: ${item.source} · p = ${item.p < 0.0001 ? "<0.0001" : item.p.toFixed(3)}`}>
      <p className="font-display font-black leading-none tracking-tight" style={{ color, fontSize: "clamp(2.6rem, 7vw, 6rem)", textShadow: confirmed ? `0 0 18px ${color}, 0 0 60px ${color}88` : "none" }}>
        {sign}{Math.abs(v).toFixed(d)}<span className="ml-1 text-[0.45em]">{item.display_unit}</span>
      </p>
      <p className="mt-4 max-w-[16rem] font-hand text-3xl leading-8 text-paper/90">{item.headline}</p>
      <div className="mt-4"><Stamp dark verdict={item.verdict} p={item.p} delay={0.9 + i * 0.25} /></div>
      <p className="mt-2 font-mono text-[10px] text-paper/40">{item.label} · {birth}→now</p>
    </motion.div>
  );
}

const inputCls = "plain border-b-2 border-dashed border-heat/70 bg-transparent text-center font-hand text-heat outline-none focus:border-solid focus:border-heat";

export default function Lifetime({ data }: { data: CaseResponse }) {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.3 });
  const reduced = !!useReducedMotion();
  const { start, end } = data.period;
  const [birth, setBirth] = useState("2005");
  const [place, setPlace] = useState(data.place.name.split(",")[0]);
  const [res, setRes] = useState<LifetimeResponse | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { setPlace(data.place.name.split(",")[0]); }, [data.place.name]);

  // debounce edits, ignore stale responses
  useEffect(() => {
    const by = parseInt(birth, 10);
    if (!Number.isFinite(by) || birth.length < 4 || !place.trim()) return;
    let stale = false; setBusy(true);
    const t = setTimeout(() => {
      getLifetime(place.trim(), Math.min(Math.max(by, start), end - 1), data)
        .then((r) => { if (!stale) setRes(r); })
        .catch(() => { if (!stale) setRes(null); })
        .finally(() => { if (!stale) setBusy(false); });
    }, 450);
    return () => { stale = true; clearTimeout(t); };
  }, [birth, place, data, start, end]);

  const by = parseInt(birth, 10);
  const clamped = Number.isFinite(by) && (by < start || by > end - 1);
  const mock = res?.data_label.origin === "mock";

  return (
    <section ref={ref} className="relative overflow-hidden bg-gradient-to-b from-[#020305] via-[#07090f] to-night px-5 py-28">
      <div className="pointer-events-none absolute left-1/2 top-1/3 h-[60vh] w-[80vw] -translate-x-1/2 rounded-full bg-cool/5 blur-3xl" />
      <div className="relative mx-auto max-w-5xl text-center">
        <p className="font-mono text-xs tracking-[0.5em] text-paper/50">SINCE YOU WERE BORN</p>

        <h2 className="mt-8 font-hand text-[clamp(2rem,5.5vw,4.2rem)] leading-tight text-paper">
          I was born in{" "}
          <input aria-label="Birth year" type="number" inputMode="numeric" min={start} max={end - 1} value={birth} onChange={(e) => setBirth(e.target.value.slice(0, 4))}
            className={inputCls} style={{ width: "4.6ch" }} />{" "}
          in{" "}
          <input aria-label="Place" value={place} onChange={(e) => setPlace(e.target.value)}
            className={inputCls} style={{ width: `${Math.max(5, place.length + 1)}ch` }} />.
          <br />Since then…
        </h2>
        {clamped && <p className="mt-3 font-mono text-[11px] text-heat/80">NASA POWER data covers {start}–{end}; counting from {Math.min(Math.max(by, start), end - 1)}.</p>}

        <div className={`mt-16 grid gap-14 transition-opacity duration-300 sm:grid-cols-3 sm:gap-6 ${busy ? "opacity-40" : "opacity-100"}`}>
          {res?.items.map((it, i) => <Giant key={it.variable + res.birth_year} item={it} i={i} active={inView} reduced={reduced} birth={res.birth_year} />)}
        </div>

        {res && (
          <p className="mt-14 font-mono text-[11px] text-paper/40" title="Origin of these numbers">
            {mock ? "⚠ SIMULATED · GET /lifetime not available yet, numbers are scaled from the case · " : res.data_label.origin === "cache" ? "cached data · " : "live NASA data · "}
            {res.years} years, {res.birth_year}–{res.end_year}
          </p>
        )}
      </div>
    </section>
  );
}
