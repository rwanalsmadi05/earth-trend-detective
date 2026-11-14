import { useRef } from "react";
import { motion, useInView, useReducedMotion } from "framer-motion";
import type { CaseResponse } from "../api/types";
import Dust from "./Dust";
import Stamp from "./Stamp";

export default function Verdict({ data }: { data: CaseResponse }) {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.45 });
  const reduced = !!useReducedMotion();
  const { confirmed, total, headline } = data.verdict;
  // case-level stamp: a plain majority of the witnesses' own (math-decided) verdicts
  const ok = confirmed * 2 > total;
  const color = ok ? "#ff4a3d" : "#a9b4c4";
  const borderline = data.witnesses.filter((w) => w.verdict === "CONFIRMED" && data.expert?.[w.variable]?.borderline);
  // the backend headline may already carry the borderline note; only add ours if it does not
  const needNote = borderline.length > 0 && !/borderline/i.test(headline);
  const IMPACT = reduced ? 0 : 0.42; // seconds until the stamp hits

  return (
    <section ref={ref} className="relative isolate flex min-h-screen items-center justify-center overflow-hidden bg-[#020305] px-5 py-24">
      {/* spotlight beam from above + pool of light on the floor */}
      <div className="pointer-events-none absolute inset-0" style={{ clipPath: "polygon(44% 0, 56% 0, 88% 100%, 12% 100%)", background: "linear-gradient(to bottom, rgba(255,243,215,.55), rgba(255,236,200,.14) 55%, rgba(255,236,200,.04))", filter: "blur(6px)" }} />
      <div className="pointer-events-none absolute left-1/2 top-[62%] h-[40vh] w-[70vw] -translate-x-1/2 rounded-[50%]" style={{ background: "radial-gradient(ellipse, rgba(255,226,170,.22), transparent 68%)" }} />
      <div className="pointer-events-none absolute inset-0" style={{ background: "radial-gradient(ellipse 75% 70% at 50% 45%, transparent 40%, #000 100%)" }} />
      <Dust />

      <motion.div className="relative z-10 flex max-w-3xl flex-col items-center text-center"
        animate={inView && !reduced ? { x: [0, -9, 8, -5, 3, 0], y: [0, 7, -6, 3, -1, 0] } : {}} transition={{ delay: IMPACT, duration: 0.55 }}>
        <p className="font-mono text-xs tracking-[0.5em] text-paper/50">THE VERDICT</p>

        <div className="relative my-10 flex items-center justify-center">
          {/* shock wave */}
          {!reduced && [0, 0.14].map((d) => (
            <motion.span key={d} className="pointer-events-none absolute h-40 w-40 rounded-full border-2"
              style={{ borderColor: color }} initial={{ scale: 0.2, opacity: 0 }}
              animate={inView ? { scale: [0.2, 9], opacity: [0.75, 0] } : {}} transition={{ delay: IMPACT + d, duration: 1.3, ease: "easeOut" }} />
          ))}
          <motion.div
            initial={reduced ? false : { scale: 3.6, opacity: 0, rotate: -22 }}
            animate={inView || reduced ? { scale: reduced ? 1 : [3.6, 0.93, 1], opacity: 1, rotate: reduced ? -7 : [-22, -7, -7] } : {}}
            transition={{ delay: 0.15, duration: IMPACT, times: [0, 0.75, 1], ease: "easeIn" }}
            className="select-none rounded-xl border-[6px] px-8 py-3 font-type font-bold uppercase tracking-[0.12em] sm:border-[10px] sm:px-14 sm:py-5"
            style={{ color, borderColor: color, fontSize: "clamp(2.6rem, 10vw, 8rem)", textShadow: `0 0 28px ${color}`, boxShadow: `0 0 50px ${color}55, inset 0 0 30px ${color}33` }}
            title={`${confirmed} of ${total} witnesses are individually CONFIRMED (p < 0.05)`}>
            {ok ? "CONFIRMED" : "NOT PROVEN"}
          </motion.div>
        </div>

        <motion.div initial={reduced ? false : { opacity: 0, y: 14 }} animate={inView || reduced ? { opacity: 1, y: 0 } : {}} transition={{ delay: IMPACT + 0.5, duration: 0.7 }}>
          <p className="font-type text-xl leading-8 text-paper sm:text-2xl">{headline}</p>
          {needNote && (
            <p className="mt-3 font-hand text-2xl text-heat">
              borderline: {borderline.map((w) => `${w.label.toLowerCase()} (p = ${w.stats.p.toFixed(3)})`).join(", ")}
            </p>
          )}
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            {data.witnesses.map((w) => (
              <div key={w.variable} className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 font-mono text-[11px] text-paper/70">
                {w.label}<Stamp dark verdict={w.verdict} p={w.stats.p} delay={IMPACT + 0.8} light={!!data.expert?.[w.variable]?.borderline && w.verdict === "CONFIRMED"} />
              </div>
            ))}
          </div>
          <p className="mt-6 font-mono text-[10px] text-paper/35">Stamps come from the statistics (modified Mann-Kendall, p &lt; 0.05), never from the AI.</p>
        </motion.div>
      </motion.div>
    </section>
  );
}
