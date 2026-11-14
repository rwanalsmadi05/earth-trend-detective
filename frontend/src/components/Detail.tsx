import { motion, AnimatePresence } from "framer-motion";
import type { ExpertItem, Witness } from "../api/types";
import Chart from "./Chart";
import Stamp from "./Stamp";

const fmt = (n: number, d = 3) => (Math.abs(n) >= 1 ? n.toFixed(2) : n.toFixed(d));

export default function Detail({ w, ex, onClose }: { w: Witness | null; ex?: ExpertItem; onClose: () => void }) {
  return (
    <AnimatePresence>
      {w && (
        <motion.div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.div onClick={(e) => e.stopPropagation()} initial={{ y: 40, scale: 0.95 }} animate={{ y: 0, scale: 1 }} exit={{ y: 40 }}
            className="max-h-[92vh] w-full max-w-2xl overflow-auto rounded-xl border border-white/10 bg-[#0c1017] p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="font-mono text-[11px] tracking-widest text-cool/70">EXPERT VIEW · {w.variable}</p>
                <h3 className="font-display text-xl">{w.label}</h3>
              </div>
              <Stamp verdict={w.verdict} p={w.stats.p} />
            </div>
            <p className="mt-3 font-type text-lg text-paper/90">{w.headline}</p>
            <div className="mt-4 rounded-lg bg-black/40 p-3">
              <Chart w={w} />
              <p className="font-mono text-[10px] text-paper/50">annual mean of de-seasonalised monthly anomalies · line = Sen's slope</p>
            </div>
            <dl className="mt-4 grid grid-cols-2 gap-3 font-mono text-xs sm:grid-cols-3">
              {([
                ["tau", fmt(w.stats.tau)], ["p-value", w.stats.p < 0.0001 ? "<0.0001" : fmt(w.stats.p)], ["n (months)", String(w.stats.n)],
                ["Sen / decade", `${fmt(w.stats.sen_per_decade)} ${w.unit}`], ["Total change", `${fmt(w.stats.total_change)} ${w.unit}`],
                ["vs baseline", `${w.stats.pct_change > 0 ? "+" : ""}${w.stats.pct_change}%`],
              ] as const).map(([k, v]) => (
                <div key={k}><dt className="text-paper/40">{k}</dt><dd className="text-paper">{v}</dd></div>
              ))}
            </dl>
            {ex && <p className="mt-4 font-mono text-[11px] text-paper/60">Method: {ex.method} · tested on {ex.test_on} (n = {ex.n_tested}){ex.borderline ? " · BORDERLINE: p is close to the 0.05 line" : ""}{ex.reason ? ` · ${ex.reason}` : ""}</p>}
            <p className="mt-4 font-mono text-[11px] text-paper/50">
              Source: <a className="text-cool underline" href={w.source_url} target="_blank" rel="noreferrer">{w.source}</a> · from {w.start_year}
            </p>
            <button onClick={onClose} className="mt-5 rounded-full border border-white/20 px-4 py-1.5 font-mono text-xs hover:bg-white/10">CLOSE</button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
