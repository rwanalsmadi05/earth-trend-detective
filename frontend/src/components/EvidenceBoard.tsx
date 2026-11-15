import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { motion, useInView } from "framer-motion";
import type { CaseResponse, ExpertItem, SatImage, Witness } from "../api/types";
import { bigNumber, isOrange } from "../lib/format";
import Stamp from "./Stamp";
import Detail from "./Detail";
import Chart from "./Chart";
import CountryMap from "./CountryMap";
import { Lamp, Magnifier } from "./Decor";

const MAX = 5;
const TILT = [-2.5, 1.8, -1.5, 2.5, -2];
const STAGGER = [0, 26, 6, 30, 4]; // px: slight vertical stagger so the row looks hand-pinned

// Where the case location falls inside a photo, as % of the displayed frame (which is cropped with object-cover).
// Uses the photo's own bbox [w,s,e,n] when the backend sends it; otherwise assumes the photo is centred on the place.
const FRAME = 6 / 5; // frame aspect (aspect-[6/5])
function placeInPhoto(bbox: SatImage["bbox"], lat: number, lon: number, natural: { w: number; h: number } | null) {
  const fx = bbox ? (lon - bbox[0]) / (bbox[2] - bbox[0]) : 0.5;
  const fy = bbox ? (bbox[3] - lat) / (bbox[3] - bbox[1]) : 0.5;
  const ia = natural ? natural.w / natural.h : FRAME;
  let x = fx, y = fy;
  if (ia > FRAME) x = 0.5 + (fx - 0.5) * (ia / FRAME);       // photo wider than the frame: cropped left/right
  else if (ia < FRAME) y = 0.5 + (fy - 0.5) * (FRAME / ia);  // photo taller than the frame: cropped top/bottom
  return { x: x * 100, y: y * 100, visible: x >= 0 && x <= 1 && y >= 0 && y <= 1 };
}

function Crosshair({ x, y }: { x: number; y: number }) {
  return (
    <svg className="pointer-events-none absolute h-9 w-9 -translate-x-1/2 -translate-y-1/2" style={{ left: `${x}%`, top: `${y}%` }} viewBox="-18 -18 36 36" fill="none" aria-label="case location">
      <title>Case location</title>
      {[["#000", 3.2, 0.55], ["#FF8A3D", 1.5, 1]].map(([c, w, o]) => (
        <g key={String(c)} stroke={c as string} strokeWidth={w as number} opacity={o as number} strokeLinecap="round">
          <circle r="9" />
          <path d="M-17 0H-12M12 0H17M0 -17V-12M0 12V17" />
        </g>
      ))}
      <circle r="1.4" fill="#FF8A3D" />
    </svg>
  );
}

// A photo that loaded but is blank (flat colour) or almost black is as useless as a missing one.
function looksEmpty(img: HTMLImageElement): boolean {
  try {
    const c = document.createElement("canvas"); c.width = 32; c.height = 27;
    const g = c.getContext("2d", { willReadFrequently: true })!; g.drawImage(img, 0, 0, 32, 27);
    const d = g.getImageData(0, 0, 32, 27).data; let sum = 0, sq = 0, dark = 0; const n = d.length / 4;
    for (let i = 0; i < d.length; i += 4) { const l = 0.3 * d[i] + 0.59 * d[i + 1] + 0.11 * d[i + 2]; sum += l; sq += l * l; if (l < 14) dark++; }
    const mean = sum / n, sd = Math.sqrt(Math.max(0, sq / n - mean * mean));
    return mean < 14 || dark / n > 0.9 || sd < 4;
  } catch { return false; } // cross-origin canvas: cannot inspect, assume fine
}

function Polaroid({ w, i, ex, compact, place, onOpen }: { w: Witness; i: number; ex?: ExpertItem; compact: boolean; place: { lat: number; lon: number }; onOpen: () => void }) {
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [after, setAfter] = useState(true);
  const [bad, setBad] = useState<Record<string, boolean>>({});
  const img = after ? w.images?.after : w.images?.before;
  const hasImg = !!img?.url && !bad[img.url]; // no photo, failed to load, or blank/dark -> show the series instead of an empty frame
  const borderline = !!ex?.borderline && w.verdict === "CONFIRMED"; // flag comes from the backend (POST /case/expert)
  const big = bigNumber(w);
  const pos = placeInPhoto(img?.bbox, place.lat, place.lon, natural);
  // NOT PROVEN never gets a direction colour: a muted grey number cannot be mistaken for a confirmed result
  const tone = w.verdict !== "CONFIRMED" ? "text-[#8a8f98]" : isOrange(w.variable, w.direction === "up" ? 1 : -1) ? "text-[#d4560e]" : "text-[#1f78b4]";
  return (
    <motion.button type="button" onClick={onOpen}
      initial={{ y: -120, opacity: 0, rotate: TILT[i] * 3 }} whileInView={{ y: 0, opacity: 1, rotate: TILT[i] }} viewport={{ once: true, margin: "-80px" }}
      transition={{ type: "spring", stiffness: 260, damping: 14, delay: 0.3 + i * 0.3 }}
      whileHover={{ y: -10, scale: 1.03, rotate: 0, zIndex: 30, boxShadow: "0 30px 40px rgba(0,0,0,.55)" }}
      className="relative flex w-full flex-col rounded-sm bg-paper p-3 text-left shadow-[0_10px_18px_rgba(0,0,0,.45)]">
      <span className="absolute -top-2 left-1/2 h-4 w-4 -translate-x-1/2 rounded-full bg-stamp shadow-[0_3px_4px_rgba(0,0,0,.5)] lg:hidden" />
      <div className="relative aspect-[6/5] overflow-hidden bg-slate-800">
        {hasImg ? (
          <>
            <img src={img!.url} alt={`${w.label} satellite ${img!.date}`} loading="lazy" className="h-full w-full object-cover" onLoad={(e) => { const el = e.currentTarget; setNatural({ w: el.naturalWidth, h: el.naturalHeight }); if (looksEmpty(el)) setBad((b) => ({ ...b, [img!.url]: true })); }} onError={() => setBad((b) => ({ ...b, [img!.url]: true }))} />
            <span className="absolute bottom-1 left-1 rounded bg-black/60 px-1 font-mono text-[9px] text-paper">NASA GIBS · {img!.date}</span>
            <span role="button" onClick={(e) => { e.stopPropagation(); setAfter(!after); }}
              className="absolute right-1 top-1 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[9px] text-paper hover:bg-black/80">{after ? "NOW" : "THEN"} ⇄</span>
            {pos.visible && <Crosshair x={pos.x} y={pos.y} />}
          </>
        ) : (
          <div className="flex h-full flex-col justify-center bg-[#0c1017] p-2"><Chart w={w} /><span className="font-mono text-[9px] text-paper/50">{w.label} · yearly anomaly, no photo</span></div>
        )}
      </div>

      {/* the number, huge */}
      <p className={`mt-3 font-display font-black leading-none tracking-tight ${tone} ${compact ? "text-[clamp(1.4rem,2.1vw,2.2rem)]" : "text-[clamp(1.6rem,2.6vw,2.9rem)]"}`}>
        {big.sign}{big.value}<span className="ml-0.5 text-[0.5em] font-bold">{big.unit}</span>
      </p>
      <p className="mt-1 font-hand text-[1.4rem] leading-6 text-night/85">{w.headline}</p>

      {/* footer lives inside the card, so nothing is ever laid over it */}
      <div className="mt-2 border-t border-night/10 pt-2">
        <p className="truncate whitespace-nowrap font-mono text-[8px] leading-3 text-night/60" title={`${w.label} · ${w.source}${w.variable === "NDVI" ? ` · starts ${w.start_year}` : ""}`}>
          {w.label} · {w.source}{w.variable === "NDVI" ? ` · starts ${w.start_year}` : ""}
        </p>
        <div className="mt-1.5 flex justify-end pr-1"><Stamp verdict={w.verdict} p={w.stats.p} delay={1 + i * 0.3} light={borderline} /></div>
      </div>
      {borderline && (
        <p className="mt-1 -rotate-1 font-hand text-xl leading-5 text-stamp" title={ex?.test_on}>borderline · p = {w.stats.p.toFixed(3)}</p>
      )}
    </motion.button>
  );
}

function Sticky({ text, i }: { text: string; i: number }) {
  return (
    <motion.div initial={{ scale: 0, rotate: -10 }} whileInView={{ scale: 1, rotate: i % 2 ? 2.5 : -2.5 }} viewport={{ once: true }} transition={{ delay: 2, type: "spring" }}
      className="relative w-[210px] bg-[#f6e27a] p-4 pt-5 font-hand text-xl leading-5 text-night/85 shadow-[0_8px_12px_rgba(0,0,0,.4)]">
      <span className="absolute -top-2 left-1/2 h-4 w-14 -translate-x-1/2 bg-white/40" />
      {text}
    </motion.div>
  );
}

// One continuous sagging curve from pin to pin: control points sit along the chord, pushed down by gravity.
function sagPath(a: { x: number; y: number }, b: { x: number; y: number }) {
  const dist = Math.hypot(b.x - a.x, b.y - a.y);
  const c = Math.min(95, 28 + dist * 0.16) / 0.75; // cubic mid-depth = 0.75 * control offset
  return `M${a.x} ${a.y} C${a.x + (b.x - a.x) * 0.25} ${a.y + (b.y - a.y) * 0.25 + c} ${a.x + (b.x - a.x) * 0.75} ${a.y + (b.y - a.y) * 0.75 + c} ${b.x} ${b.y}`;
}

// torn note that opens the manual "pick the witnesses yourself" form
function NextNote({ onPick }: { onPick?: () => void }) {
  if (!onPick) return null;
  return (
    <motion.button type="button" onClick={onPick} initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: 2.4 }} whileHover={{ y: -4, rotate: 0 }}
      className="relative -rotate-2 bg-paper px-5 py-3 text-left font-type text-night shadow-[0_8px_14px_rgba(0,0,0,.5)] [clip-path:polygon(0_6%,4%_0,9%_8%,15%_0,100%_0,100%_92%,94%_100%,88%_92%,80%_100%,0_100%)]">
      <span className="block text-[10px] tracking-[0.3em] text-night/50">NEXT</span>
      <span className="block text-base">Pick your own witnesses →</span>
    </motion.button>
  );
}

export default function EvidenceBoard({ data, onPick }: { data: CaseResponse; onPick?: () => void }) {
  const [open, setOpen] = useState<Witness | null>(null);
  const shown = data.witnesses.slice(0, MAX);
  const n = shown.length;
  const compact = n >= 5;

  const boardRef = useRef<HTMLDivElement>(null);
  const slotRefs = useRef<(HTMLDivElement | null)[]>([]);
  const inView = useInView(boardRef, { once: true, margin: "-120px" });
  const [geo, setGeo] = useState<{ w: number; h: number; pins: { x: number; y: number }[] }>({ w: 0, h: 0, pins: [] });

  // pin positions are measured from the real DOM, so the strings always meet the pins at any width / witness count
  useLayoutEffect(() => {
    const measure = () => {
      const b = boardRef.current; if (!b) return;
      const br = b.getBoundingClientRect();
      const pins = slotRefs.current.slice(0, n).map((el) => {
        const r = el?.getBoundingClientRect();
        return r ? { x: r.left - br.left + r.width / 2, y: r.top - br.top + 2 } : { x: 0, y: 0 };
      });
      setGeo({ w: br.width, h: br.height, pins });
    };
    measure();
    const ro = new ResizeObserver(measure); if (boardRef.current) ro.observe(boardRef.current);
    window.addEventListener("resize", measure);
    document.fonts?.ready.then(measure);
    return () => { ro.disconnect(); window.removeEventListener("resize", measure); };
  }, [n]);
  useEffect(() => { const t = setTimeout(() => window.dispatchEvent(new Event("resize")), 600); return () => clearTimeout(t); }, [n]);

  const idx = (v: string) => shown.findIndex((w) => w.variable === v);
  const strings = data.chain.map((c) => [idx(c.from), idx(c.to), c] as const).filter(([a, b]) => a >= 0 && b >= 0);
  
  // sticky notes: the partner's hints, plus one note per remaining chain link, worded only from computed numbers
  const label = (v: string) => data.witnesses.find((w) => w.variable === v)?.label ?? v;
  const chainNotes = data.chain
    .filter((c) => !data.hints.some((h) => h.after === c.from))
    .map((c) => `${label(c.from)} and ${label(c.to).toLowerCase()} moved ${c.r < 0 ? "in opposite directions" : "together"} (r = ${c.r}, ${c.lag_months === 0 ? "same month" : `${c.lag_months}-month lag`}). Correlation, not proof.`);
  const notes = [...data.hints.map((h) => h.text), ...chainNotes].slice(0, 3);

  return (
    <section className="relative bg-night px-3 py-10 sm:px-8">
      <div className="mx-auto max-w-[1300px]">
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2 font-mono text-[11px] text-paper/50">
          <span>CASE {data.case_id.toUpperCase()} · {data.period.start}–{data.period.end}</span>
          <span title="Origin of the numbers on this board">{data.data_label.origin === "mock" ? "⚠ SIMULATED DEMO DATA · " : data.data_label.origin === "cache" ? "cached data · " : "live NASA data · "}fetched {data.data_label.fetched}</span>
        </div>

        {/* dark wood frame */}
        <div className="relative overflow-hidden rounded-lg border-[14px] border-[#3b2414] shadow-[0_0_80px_rgba(0,0,0,.8),inset_0_0_30px_rgba(0,0,0,.6)]">
          <div ref={boardRef} className="cork relative">
            {/* ---------- atmosphere ---------- */}
            <Lamp />
            <div className="flicker pointer-events-none absolute inset-0 z-[15] hidden lg:block"
              style={{ clipPath: "polygon(46.5% 0, 53.5% 0, 100% 100%, 0 100%)", background: "linear-gradient(to bottom, rgba(255,214,150,.55), rgba(255,196,120,.22) 45%, rgba(255,190,110,.05) 85%, transparent)" }} />
            <div className="flicker pointer-events-none absolute inset-0 z-[15]"
              style={{ background: "radial-gradient(ellipse 55% 45% at 50% 38%, rgba(255,205,130,.30), transparent 70%)" }} />
            <div className="pointer-events-none absolute inset-0 z-[16]"
              style={{ background: "radial-gradient(ellipse 80% 75% at 50% 40%, transparent 45%, rgba(0,0,0,.72) 100%)", boxShadow: "inset 0 0 120px 30px rgba(0,0,0,.65)" }} />

            {/* ---------- desktop board: three rows, nothing absolutely positioned over a polaroid ---------- */}
            <div className="relative z-[2] hidden px-10 pb-12 pt-8 lg:block">
              {/* row 1: case card · verdict strip · map */}
              <div className="flex items-start justify-between gap-6">
                <div className="w-[26%] -rotate-1 bg-paper p-4 font-type text-night shadow-[0_10px_18px_rgba(0,0,0,.45)]"
                  style={{ backgroundImage: "repeating-linear-gradient(transparent 0 23px, rgba(80,120,200,.25) 23px 24px)" }}>
                  <p className="text-[10px] tracking-widest">CASE FILE Nº {data.case_id.slice(0, 6).toUpperCase()}</p>
                  <p className="mt-1 text-lg leading-6">“{data.cleaned_question?.trim() || data.question}”</p>
                  <p className="mt-2 text-xs leading-5">Location: {data.place.name}<br />{data.place.lat}°N, {data.place.lon}°E<br />Period: {data.period.start}–{data.period.end}</p>
                  <p className="mt-2 text-xs text-stamp">Witnesses called: {data.witnesses.length}</p>
                </div>

                <motion.div initial={{ x: 120, opacity: 0 }} whileInView={{ x: 0, opacity: 1 }} viewport={{ once: true }} transition={{ delay: 2.6, duration: 0.6 }}
                  className="mt-24 -rotate-2 bg-paper px-5 py-3 text-center font-type text-night shadow-[0_8px_14px_rgba(0,0,0,.5)] [clip-path:polygon(0_10%,5%_0,11%_9%,19%_0,100%_0,100%_100%,0_100%)]">
                  <p className="text-[10px] tracking-[0.3em] text-night/60">VERDICT</p>
                  <p className="text-xl">{data.verdict.confirmed} of {data.verdict.total} witnesses confirm</p>
                </motion.div>

                <div className="relative w-[22%] rotate-2 bg-[#e8dcc0] p-2 pb-1 shadow-[0_10px_18px_rgba(0,0,0,.45)]">
                  <span className="absolute -top-2 left-1/2 h-4 w-4 -translate-x-1/2 rounded-full bg-stamp shadow-[0_3px_4px_rgba(0,0,0,.5)]" />
                  <CountryMap lat={data.place.lat} lon={data.place.lon} name={data.place.name} />
                  <p className="font-mono text-[9px] text-night/50">Outline: Natural Earth</p>
                </div>
              </div>

              {/* row 2: the witnesses */}
              <div className="mx-auto mt-10 grid items-start gap-5 xl:gap-7"
                style={{ gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))`, maxWidth: n < 4 ? n * 300 : undefined }}>
                {shown.map((w, i) => (
                  <div key={w.variable} ref={(el) => { slotRefs.current[i] = el; }} style={{ marginTop: STAGGER[i] }}>
                    <Polaroid w={w} i={i} compact={compact} place={data.place} ex={data.expert?.[w.variable]} onOpen={() => setOpen(w)} />
                  </div>
                ))}
              </div>

              {/* row 3: partner's notes and props, in flow below the polaroids */}
              <div className="relative mt-12 flex items-end justify-between gap-6">
                <div className="flex flex-1 flex-wrap items-start justify-center gap-6">{notes.map((t, i) => <Sticky key={i} text={t} i={i} />)}<NextNote onPick={onPick} /></div>
                <div className="relative h-32 w-40">
                  <div className="absolute left-2 top-4 h-16 w-16 rounded-full border-[3px] border-[#5b3517]/45" style={{ boxShadow: "inset 0 0 6px rgba(60,30,10,.35)" }} />
                  <div className="absolute left-0 top-2 h-20 w-20 rounded-full border-[2px] border-[#5b3517]/25" />
                  <Magnifier className="absolute -top-6 right-0 z-[3] h-40 w-40 -rotate-12" />
                </div>
              </div>
            </div>

            {/* ---------- strings: one continuous sagging curve per link, with a soft shadow ---------- */}
            {geo.w > 0 && (
              <svg className="pointer-events-none absolute left-0 top-0 z-[10] hidden lg:block" width={geo.w} height={geo.h} viewBox={`0 0 ${geo.w} ${geo.h}`}>
                <defs>
                  <filter id="strShadow" x="-10%" y="-10%" width="120%" height="140%"><feGaussianBlur stdDeviation="3" /></filter>
                  <radialGradient id="pinHead" cx=".35" cy=".3"><stop offset="0" stopColor="#ff8d84" /><stop offset=".55" stopColor="#C8261E" /><stop offset="1" stopColor="#6e0f0b" /></radialGradient>
                </defs>
                {strings.map(([a, b, c], k) => {
                  const pa = geo.pins[a], pb = geo.pins[b]; if (!pa || !pb) return null;
                  const d = sagPath(pa, pb);
                  const anim = { initial: { pathLength: 0 }, animate: { pathLength: inView ? 1 : 0 }, transition: { delay: 1.9 + k * 0.7, duration: 1.1 } };
                  return (
                    <g key={k}>
                      <motion.path d={d} fill="none" stroke="rgba(0,0,0,.55)" strokeWidth="4" strokeLinecap="round" filter="url(#strShadow)" transform="translate(5 11)" {...anim} />
                      <motion.path d={d} fill="none" stroke="#C8261E" strokeWidth="2.6" strokeLinecap="round" {...anim}>
                        <title>{`${c.from} → ${c.to}: lag ${c.lag_months} mo, r = ${c.r} (correlation, not causation)`}</title>
                      </motion.path>
                      <motion.path d={d} fill="none" stroke="rgba(255,170,160,.55)" strokeWidth=".8" strokeLinecap="round" transform="translate(0 -1)" {...anim} />
                    </g>
                  );
                })}
                {geo.pins.map((p, i) => (
                  <motion.g key={i} initial={{ opacity: 0 }} animate={{ opacity: inView ? 1 : 0 }} transition={{ delay: 1.6 }}>
                    <circle cx={p.x + 2} cy={p.y + 4} r="7" fill="rgba(0,0,0,.45)" />
                    <circle cx={p.x} cy={p.y} r="7" fill="url(#pinHead)" />
                  </motion.g>
                ))}
              </svg>
            )}

            {/* ---------- mobile: swipeable stack ---------- */}
            <div className="relative z-[2] flex snap-x snap-mandatory gap-4 overflow-x-auto p-6 pt-12 lg:hidden">
              {shown.map((w, i) => (
                <div key={w.variable} className="w-[78%] shrink-0 snap-center"><Polaroid w={w} i={i} compact={false} place={data.place} ex={data.expert?.[w.variable]} onOpen={() => setOpen(w)} /></div>
              ))}
            </div>
            <div className="relative z-[2] px-6 pb-8 lg:hidden"><NextNote onPick={onPick} /></div>
          </div>
        </div>

        <p className="mt-4 text-center font-mono text-[11px] text-paper/40">Tap a polaroid for the expert view · hover a stamp for the p-value · red string = lagged correlation, not causation</p>
      </div>
      <Detail w={open} ex={open ? data.expert?.[open.variable] : undefined} onClose={() => setOpen(null)} />
    </section>
  );
}
