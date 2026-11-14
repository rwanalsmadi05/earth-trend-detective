import { motion } from "framer-motion";
import type { Verdict } from "../api/types";

export default function Stamp({ verdict, p, delay = 0, big = false, light = false, dark = false }: { verdict: Verdict; p?: number; delay?: number; big?: boolean; light?: boolean; dark?: boolean }) {
  const ok = verdict === "CONFIRMED";
  const color = dark ? (ok ? "#ff5a4d" : "#a9b4c4") : ok ? "#C8261E" : "#5b6573";
  return (
    <motion.div
      initial={{ scale: 3, opacity: 0, rotate: -25 }} whileInView={{ scale: 1, opacity: light ? 0.5 : 0.92, rotate: ok ? -9 : 6 }}
      viewport={{ once: true }} transition={{ type: "spring", stiffness: 380, damping: 18, delay }}
      title={p !== undefined ? `Modified Mann-Kendall p = ${p < 0.0001 ? "<0.0001" : p.toFixed(3)} (CONFIRMED if p < 0.05)` : undefined}
      className={`pointer-events-auto select-none ${light ? "border-dashed border-2" : "border-[3px]"} ${big ? "px-5 py-2 text-3xl" : "px-2 py-0.5 text-sm"} rounded-md font-type font-bold uppercase tracking-widest`}
      style={{ color, borderColor: color, mixBlendMode: dark ? "normal" : "multiply", textShadow: dark ? "0 0 10px currentColor" : "0 0 1px currentColor" }}>
      {verdict}
    </motion.div>
  );
}
