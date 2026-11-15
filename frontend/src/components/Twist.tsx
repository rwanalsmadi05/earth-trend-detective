import { useEffect, useRef, useState } from "react";
import { motion, useInView, useReducedMotion } from "framer-motion";
import type { CaseResponse, TwistResponse, TwistSide, VariableId } from "../api/types";
import { getTwist } from "../api/client";
import { formatBig, isOrange } from "../lib/format";
import Stamp from "./Stamp";

function Side({ s, variable, words, label, delay, reduced, active }: { s: TwistSide; variable: VariableId; words: { up: string; down: string }; label: string; delay: number; reduced: boolean; active: boolean }) {
  const color = isOrange(variable, s.value) ? "#FF8A3D" : "#7CC8FF";
  const b = formatBig(s.value, s.display_unit);
  const size = Math.round(Math.min(300, Math.max(190, 190 + Math.abs(s.value) * 2.2)));
  return (
    <motion.div initial={reduced ? false : { opacity: 0, scale: 0.7 }} animate={active ? { opacity: 1, scale: 1 } : {}} transition={{ delay, duration: 0.8, type: "spring", damping: 14 }}
      className="flex flex-col items-center text-center" title={`p = ${s.p < 0.0001 ? "<0.0001" : s.p.toFixed(3)}`}>
      <div className="relative flex items-center justify-center rounded-full" style={{ width: size, height: size, background: `radial-gradient(circle, ${color}55 0%, ${color}22 55%, transparent 72%)`, boxShadow: `0 0 70px 10px ${color}55, inset 0 0 40px ${color}44`, border: `2px solid ${color}` }}>
        {!reduced && <motion.span className="absolute inset-0 rounded-full" style={{ border: `2px solid ${color}` }} animate={{ scale: [1, 1.35], opacity: [0.6, 0] }} transition={{ duration: 2.6, repeat: Infinity, ease: "easeOut" }} />}
        <div>
          <p className="font-display font-black leading-none" style={{ color, fontSize: size * 0.2, textShadow: `0 0 18px ${color}` }}>{b.sign}{b.value}<span className="text-[0.5em]">{b.unit === " days" ? " days" : b.unit}</span></p>
          <p className="mt-2 font-hand text-2xl leading-6 text-paper">{s.value > 0 ? words.up : words.down}</p>
        </div>
      </div>
      <p className="mt-5 font-mono text-sm tracking-widest text-paper">{s.name.toUpperCase()}</p>
      <p className="font-mono text-[10px] text-paper/40">{label} · {s.lat.toFixed(2)}°N {s.lon.toFixed(2)}°E</p>
      <div className="mt-3"><Stamp dark verdict={s.verdict} p={s.p} delay={delay + 0.8} /></div>
    </motion.div>
  );
}

export default function Twist({ data }: { data: CaseResponse }) {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.35 });
  const reduced = !!useReducedMotion();
  const [res, setRes] = useState<TwistResponse | null>(null);

  useEffect(() => { let stale = false; setRes(null); getTwist(data).then((r) => !stale && setRes(r)).catch(() => !stale && setRes(null)); return () => { stale = true; }; }, [data]);

  // only a pair the statistics actually found; otherwise the section does not exist
  if (!res?.found || !res.a || !res.b || !res.words) return null;
  const mock = res.data_label?.origin === "mock";

  return (
    <section ref={ref} className="relative overflow-hidden bg-[#020305] px-5 py-28">
      <div className="pointer-events-none absolute inset-0" style={{ background: "radial-gradient(ellipse 60% 50% at 50% 55%, rgba(124,200,255,.07), transparent 70%), radial-gradient(ellipse 90% 80% at 50% 50%, transparent 45%, #000 100%)" }} />
      <div className="relative mx-auto max-w-5xl text-center">
        <p className="font-mono text-xs tracking-[0.5em] text-paper/50">THE TWIST</p>
        <h2 className="mt-3 font-display text-[clamp(1.6rem,4vw,3rem)] font-black leading-tight">One variable. Two directions.</h2>

        <div className="mt-14 flex flex-col items-center justify-center gap-10 md:flex-row md:gap-0">
          <Side s={res.a} variable={res.variable!} words={res.words} label={res.label ?? ""} delay={0.1} reduced={reduced} active={inView} />
          <div className="flex items-center md:w-64 md:flex-col md:px-4">
            <motion.div initial={reduced ? false : { scaleX: 0 }} animate={inView ? { scaleX: 1 } : {}} transition={{ delay: 0.9, duration: 0.8 }}
              className="hidden h-[3px] w-full origin-left rounded md:block" style={{ background: "linear-gradient(90deg,#FF8A3D,#7CC8FF)", boxShadow: "0 0 18px #FF8A3D88, 0 0 18px #7CC8FF88" }} />
            <motion.p initial={reduced ? false : { opacity: 0 }} animate={inView ? { opacity: 1 } : {}} transition={{ delay: 1.3 }}
              className="mt-0 font-type text-sm uppercase tracking-[0.25em] text-paper md:mt-4">same cause,<br />opposite effects</motion.p>
          </div>
          <Side s={res.b} variable={res.variable!} words={res.words} label={res.label ?? ""} delay={0.5} reduced={reduced} active={inView} />
        </div>

        <motion.p initial={reduced ? false : { opacity: 0, y: 12 }} animate={inView ? { opacity: 1, y: 0 } : {}} transition={{ delay: 1.6, duration: 0.8 }}
          className="mx-auto mt-14 max-w-2xl font-type text-lg leading-8 text-paper/90">{res.sentence}</motion.p>
        <p className="mt-6 font-mono text-[11px] text-paper/40">
          {mock ? "⚠ SIMULATED · GET /twist not available yet · pair found from the simulated grid · " : ""}
          both trends are tested separately; correlation, not causation.
        </p>
      </div>
    </section>
  );
}
