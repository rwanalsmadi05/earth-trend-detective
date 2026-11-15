import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import type { CaseResponse, GameRound } from "../api/types";
import { getGameRounds } from "../api/client";
import Stamp from "./Stamp";
import { isOrange, ORANGE_INK, BLUE_INK } from "../lib/format";

type Guess = "real" | "noise";

// An unlabeled series. After the reveal it gains the years and the Sen's slope line.
function RoundChart({ r, reveal }: { r: GameRound; reveal: boolean }) {
  const W = 560, H = 200, pad = 14;
  const xs = r.series.map((s) => s.year), ys = r.series.map((s) => s.value);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const X = (x: number) => pad + ((x - x0) / (x1 - x0)) * (W - 2 * pad);
  const Y = (y: number) => H - pad - ((y - y0) / (y1 - y0 || 1)) * (H - 2 * pad);
  const line = r.series.map((s, i) => `${i ? "L" : "M"}${X(s.year).toFixed(1)},${Y(s.value).toFixed(1)}`).join(" ");
  const mean = ys.reduce((a, b) => a + b, 0) / ys.length, mx = (x0 + x1) / 2, k = r.sen_per_decade / 10;
  const color = isOrange(r.variable, r.sen_per_decade) ? ORANGE_INK : BLUE_INK;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      <g stroke="#0b0f14" strokeOpacity=".08">{[0.25, 0.5, 0.75].map((t) => <line key={t} x1={pad} x2={W - pad} y1={pad + t * (H - 2 * pad)} y2={pad + t * (H - 2 * pad)} />)}</g>
      <path d={line} fill="none" stroke="#0b0f14" strokeWidth="2" strokeLinejoin="round" />
      {r.series.map((s) => <circle key={s.year} cx={X(s.year)} cy={Y(s.value)} r="2.6" fill="#0b0f14" />)}
      {reveal && (
        <>
          <motion.line x1={X(x0)} x2={X(x1)} y1={Y(mean + k * (x0 - mx))} y2={Y(mean + k * (x1 - mx))} stroke={color} strokeWidth="3.5" strokeLinecap="round" strokeDasharray={r.verdict === "CONFIRMED" ? undefined : "8 6"}
            initial={{ pathLength: 0, opacity: 0 }} animate={{ pathLength: 1, opacity: 1 }} transition={{ duration: 0.8 }} />
          <text x={pad} y={H - 1} fontSize="11" fill="#0b0f14" opacity=".55" fontFamily="JetBrains Mono">{x0}</text>
          <text x={W - pad} y={H - 1} fontSize="11" fill="#0b0f14" opacity=".55" textAnchor="end" fontFamily="JetBrains Mono">{x1}</text>
        </>
      )}
    </svg>
  );
}

const RANKS = ["Rookie", "Rookie", "Junior detective", "Detective", "Senior detective", "Chief inspector"];

export default function Game({ data }: { data: CaseResponse }) {
  const reduced = !!useReducedMotion();
  const [rounds, setRounds] = useState<GameRound[] | null>(null);
  const [idx, setIdx] = useState(0);
  const [guess, setGuess] = useState<Guess | null>(null);
  const [score, setScore] = useState(0);
  const [results, setResults] = useState<boolean[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    let stale = false; setLoading(true); setRounds(null); setIdx(0); setGuess(null); setScore(0); setResults([]);
    getGameRounds(data).then((r) => !stale && setRounds(r)).catch(() => !stale && setRounds([])).finally(() => !stale && setLoading(false));
    return () => { stale = true; };
  }, [data]);
  useEffect(() => load(), [load]);

  const round = rounds?.[idx];
  const done = !!rounds && rounds.length > 0 && idx >= rounds.length;
  const truth: Guess | null = round ? (round.verdict === "CONFIRMED" ? "real" : "noise") : null;

  function answer(g: Guess) {
    if (!round || guess) return;
    const ok = g === truth;
    setGuess(g); setResults((r) => [...r, ok]); if (ok) setScore((s) => s + 1);
  }

  return (
    <section className="relative overflow-hidden bg-night px-4 py-24 sm:px-8">
      <div className="pointer-events-none absolute left-1/2 top-1/2 h-[60vh] w-[70vw] -translate-x-1/2 -translate-y-1/2 rounded-full bg-heat/5 blur-3xl" />
      <div className="relative mx-auto max-w-3xl text-center">
        <p className="font-mono text-xs tracking-[0.5em] text-paper/50">THE GAME</p>
        <h2 className="mt-3 font-display text-[clamp(1.6rem,4vw,3rem)] font-black leading-tight">Real or noise?</h2>
        <p className="mx-auto mt-3 max-w-xl font-hand text-2xl text-paper/70">Real NASA series from this case. Can you tell a trend from chance before the statistics do?</p>

        {loading && <p className="mt-12 font-mono text-xs tracking-widest text-paper/50">PULLING REAL SERIES…</p>}
        {rounds && rounds.length === 0 && (
          <p className="mt-12 font-mono text-sm text-paper/55">The game only uses real test results, so it needs real data. {data.data_label.origin === "mock" ? "Start the backend to play." : "No usable series came back for this case."}</p>
        )}

        {rounds && rounds.length > 0 && (
          <>
            <div className="mt-8 flex items-center justify-center gap-2" aria-label="progress">
              {rounds.map((_, i) => (
                <span key={i} className={`h-2.5 w-10 rounded-full ${i < results.length ? (results[i] ? "bg-cool" : "bg-heat") : i === idx && !done ? "bg-paper/60" : "bg-white/15"}`} />
              ))}
            </div>

            <AnimatePresence mode="wait">
              {!done && round && (
                <motion.div key={idx} initial={reduced ? false : { opacity: 0, y: 30, rotate: -2 }} animate={{ opacity: 1, y: 0, rotate: idx % 2 ? 0.8 : -0.8 }} exit={reduced ? undefined : { opacity: 0, x: -60 }} transition={{ duration: 0.45 }}
                  className="relative mx-auto mt-8 max-w-2xl bg-paper p-5 text-left text-night shadow-[0_20px_50px_rgba(0,0,0,.6)] sm:p-7"
                  style={{ backgroundImage: "repeating-linear-gradient(transparent 0 31px, rgba(80,120,200,.12) 31px 32px)" }}>
                  <span className="absolute -top-2 left-1/2 h-4 w-4 -translate-x-1/2 rounded-full bg-stamp shadow-[0_3px_4px_rgba(0,0,0,.5)]" />
                  <p className="font-type text-[11px] tracking-[0.3em] text-night/50">EXHIBIT {idx + 1} OF {rounds.length}</p>
                  <p className="mt-1 font-type text-lg">{guess ? <>{round.label} <span className="text-night/50">·</span> {round.place.name}, {round.period.start}–{round.period.end}</> : "Yearly anomalies. Place and variable: classified."}</p>
                  <div className="mt-3 rounded bg-white/60 p-2"><RoundChart r={round} reveal={!!guess} /></div>

                  {!guess ? (
                    <div className="mt-5 grid grid-cols-2 gap-3">
                      <button onClick={() => answer("real")} className="border-[3px] border-[#1f78b4] bg-[#1f78b4]/10 px-3 py-3 font-type text-lg font-bold tracking-widest text-[#1f78b4] transition hover:bg-[#1f78b4] hover:text-paper">REAL TREND</button>
                      <button onClick={() => answer("noise")} className="border-[3px] border-night/60 bg-night/5 px-3 py-3 font-type text-lg font-bold tracking-widest text-night/80 transition hover:bg-night hover:text-paper">JUST NOISE</button>
                    </div>
                  ) : (
                    <div className="mt-5">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <Stamp key={`s${idx}`} big verdict={round.verdict} p={round.p} />
                        <p className={`font-hand text-3xl ${guess === truth ? "text-[#1f78b4]" : "text-[#d4560e]"}`}>{guess === truth ? "You called it ✓" : "Not this time ✗"}</p>
                      </div>
                      <p className="mt-3 font-type text-base leading-6">{round.explanation}</p>
                      <p className="mt-2 font-mono text-[10px] text-night/50">modified Mann-Kendall · tau {round.tau.toFixed(2)} · {pTxt(round.p)} · Sen {round.sen_per_decade.toFixed(3)} {round.unit}/decade · n = {round.n}</p>
                      <button onClick={() => { setIdx((i) => i + 1); setGuess(null); }} className="mt-4 -rotate-1 border-[3px] border-stamp bg-stamp px-5 py-2 font-type text-base font-bold tracking-[0.2em] text-paper shadow-[0_5px_0_#7d140f]">
                        {idx + 1 < rounds.length ? "NEXT EXHIBIT →" : "SEE MY SCORE →"}
                      </button>
                    </div>
                  )}
                </motion.div>
              )}

              {done && (
                <motion.div key="score" initial={reduced ? false : { opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} className="mt-10">
                  <p className="font-display text-[clamp(3rem,10vw,7rem)] font-black leading-none text-heat" style={{ textShadow: "0 0 40px rgba(255,138,61,.6)" }}>{score}<span className="text-paper/40">/{rounds.length}</span></p>
                  <p className="mt-3 font-type text-xl">{RANKS[Math.round((score / rounds.length) * 5)]}</p>
                  <div className="mx-auto mt-6 grid max-w-xl gap-2 text-left">
                    {rounds.map((r, i) => (
                      <div key={i} className="flex items-center justify-between gap-3 rounded border border-white/10 bg-white/5 px-3 py-2 font-mono text-[11px] text-paper/75">
                        <span>{results[i] ? "✓" : "✗"} {r.label} · {r.place.name}</span><Stamp dark verdict={r.verdict} p={r.p} light={!!r.borderline} />
                      </div>
                    ))}
                  </div>
                  <button onClick={load} className="mt-8 -rotate-1 border-[3px] border-heat px-6 py-2.5 font-type font-bold tracking-[0.2em] text-heat transition hover:bg-heat hover:text-night">PLAY AGAIN</button>
                </motion.div>
              )}
            </AnimatePresence>
            <p className="mt-8 font-mono text-[10px] text-paper/35">Every answer is the real test result (modified Mann-Kendall, p &lt; 0.05) for that series. Source: {data.data_label.origin === "cache" ? "cached " : ""}NASA POWER.</p>
          </>
        )}
      </div>
    </section>
  );
}

const pTxt = (p: number) => (p < 0.0001 ? "p < 0.0001" : `p = ${p.toFixed(3)}`);
