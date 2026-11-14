import { useRef, useState } from "react";
import { motion } from "framer-motion";
import type { CaseResponse } from "../api/types";
import { downloadCardPng, downloadReportPdf } from "../lib/report";
import CaseCardNode from "./CaseCardNode";

export default function Report({ data }: { data: CaseResponse }) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState<"png" | "pdf" | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function run(kind: "png" | "pdf") {
    setBusy(kind); setErr(null);
    try {
      if (kind === "png") { if (cardRef.current) await downloadCardPng(cardRef.current, data); }
      else await downloadReportPdf(data);
    } catch (e) { setErr((e as Error).message || "Export failed"); }
    finally { setBusy(null); }
  }

  const btn = "-rotate-1 border-[3px] px-6 py-3 font-type text-lg font-bold tracking-[0.18em] transition disabled:opacity-50";
  return (
    <section className="relative overflow-hidden bg-gradient-to-b from-night to-[#020305] px-5 py-24">
      <div className="relative mx-auto flex max-w-5xl flex-col items-center gap-12 md:flex-row md:justify-between">
        <div className="max-w-md text-center md:text-left">
          <p className="font-mono text-xs tracking-[0.5em] text-paper/50">CASE CLOSED</p>
          <h2 className="mt-3 font-display text-[clamp(1.6rem,4vw,3rem)] font-black leading-tight">Take the case with you</h2>
          <p className="mt-3 font-hand text-2xl text-paper/70">A shareable card for the group chat, and a one-page report with the method, numbers, p-values and sources for the judges.</p>
          <div className="mt-8 flex flex-wrap justify-center gap-4 md:justify-start">
            <button onClick={() => run("png")} disabled={!!busy} className={`${btn} border-heat bg-heat text-night shadow-[0_6px_0_#9a4a14] hover:brightness-110`}>{busy === "png" ? "RENDERING…" : "DOWNLOAD CASE CARD"}</button>
            <button onClick={() => run("pdf")} disabled={!!busy} className={`${btn} border-paper/70 text-paper hover:bg-paper hover:text-night`}>{busy === "pdf" ? "WRITING…" : "DOWNLOAD REPORT (PDF)"}</button>
          </div>
          {err && <p className="mt-3 font-mono text-xs text-stamp">{err}</p>}
        </div>

        {/* scaled preview of the real card */}
        <motion.div initial={{ opacity: 0, rotate: 4, y: 30 }} whileInView={{ opacity: 1, rotate: 2, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.8 }}
          className="shrink-0 overflow-hidden rounded-md shadow-[0_25px_60px_rgba(0,0,0,.7)]" style={{ width: 324, height: 324 }}>
          <div style={{ transform: "scale(0.3)", transformOrigin: "top left", width: 1080, height: 1080 }}><CaseCardNode data={data} /></div>
        </motion.div>
      </div>
      {/* full-size, off-screen copy used for the PNG export */}
      <div aria-hidden style={{ position: "fixed", left: -12000, top: 0, pointerEvents: "none" }}><CaseCardNode ref={cardRef} data={data} /></div>
    </section>
  );
}
