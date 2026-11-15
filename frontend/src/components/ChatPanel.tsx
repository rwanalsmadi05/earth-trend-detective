import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { CaseResponse, ChatMessage, ChatResponse } from "../api/types";
import { askPartner } from "../api/client";

interface Msg extends ChatMessage { source?: ChatResponse["source"]; local?: boolean }

const CHIPS = ["Which witness is the strongest?", "Is this really changing, or just noise?", "What should I check next?"];

export default function ChatPanel({ data }: { data: CaseResponse }) {
  const place = data.place.name.split(",")[0];
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([{
    role: "assistant", local: true,
    content: `I'm your partner on this case: ${place}. Ask me about a witness, a stamp or a number. I only explain what the statistics computed.`,
  }]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs, busy, open]);
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open]);

  async function send(text: string) {
    const msg = text.trim(); if (!msg || busy) return;
    const history = msgs.filter((m) => !m.local).map(({ role, content }) => ({ role, content }));
    setMsgs((m) => [...m, { role: "user", content: msg }]); setInput(""); setBusy(true); setErr(null);
    try {
      const r = await askPartner(data, msg, history);
      setMsgs((m) => [...m, { role: "assistant", content: r.reply, source: r.source }]);
    } catch (e) { setErr((e as Error).message || "Something went wrong."); }
    finally { setBusy(false); }
  }

  const fresh = msgs.length === 1;
  return (
    <>
      <AnimatePresence>
        {!open && (
          <motion.button key="tab" initial={{ x: 60 }} animate={{ x: 0 }} exit={{ x: 60 }} whileHover={{ x: -4 }} onClick={() => setOpen(true)}
            className="fixed right-0 top-1/2 z-[65] -translate-y-1/2 rounded-l-md border-y border-l border-night/30 bg-paper px-2.5 py-4 font-type text-xs font-bold tracking-[0.25em] text-night shadow-[-6px_6px_16px_rgba(0,0,0,.5)] [writing-mode:vertical-rl]"
            aria-label="Ask your partner">
            <span className="mb-2 inline-block h-3 w-3 rounded-full bg-stamp align-middle shadow" /> ASK YOUR PARTNER
          </motion.button>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {open && (
          <motion.aside key="panel" role="dialog" aria-label="Case partner"
            initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }} transition={{ type: "spring", damping: 28, stiffness: 260 }}
            className="fixed inset-y-0 right-0 z-[70] flex w-full flex-col bg-paper text-night shadow-[-20px_0_60px_rgba(0,0,0,.7)] sm:w-[26rem]"
            style={{ backgroundImage: "repeating-linear-gradient(transparent 0 31px, rgba(80,120,200,.13) 31px 32px)" }}>
            <div className="pointer-events-none absolute inset-y-0 left-12 w-px bg-stamp/40" />

            <header className="relative flex items-start justify-between gap-3 border-b-2 border-dashed border-night/25 px-5 pb-3 pt-5">
              <div>
                <p className="font-type text-[10px] tracking-[0.35em] text-night/50">CASE PARTNER</p>
                <h3 className="font-type text-xl leading-6">{place}</h3>
              </div>
              <button onClick={() => setOpen(false)} aria-label="Close" className="text-2xl leading-none text-night/50 hover:text-night">×</button>
            </header>

            <div className="relative flex-1 space-y-4 overflow-y-auto px-5 py-4">
              {msgs.map((m, i) => (
                <motion.div key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className={`max-w-[88%] ${m.role === "user" ? "ml-auto" : "mr-auto"}`}>
                  {m.role === "user" ? (
                    <div className="border border-night/25 bg-white/80 px-3 py-2 font-type text-[15px] leading-6 shadow-[0_3px_6px_rgba(0,0,0,.2)]">{m.content}</div>
                  ) : (
                    <div className="relative -rotate-[0.6deg] bg-[#f6e27a] px-3 py-2.5 shadow-[0_5px_10px_rgba(0,0,0,.3)]">
                      <span className="absolute -top-2 left-1/2 h-3.5 w-12 -translate-x-1/2 bg-white/45" />
                      <p className="whitespace-pre-wrap font-hand text-[1.3rem] leading-6 text-night/90">{m.content}</p>
                      {m.source === "mock" && <p className="mt-1.5 font-mono text-[9px] leading-3 text-night/55">⚠ SIMULATED REPLY · POST /chat not available yet</p>}
                    </div>
                  )}
                </motion.div>
              ))}
              {busy && <p className="mr-auto font-mono text-[11px] text-night/55">partner is thinking<span className="dots" /></p>}
              {err && <p className="font-mono text-[11px] text-stamp">{err}</p>}

              {fresh && (
                <div className="flex flex-wrap gap-2 pt-1">
                  {CHIPS.map((c) => (
                    <button key={c} onClick={() => send(c)} className="border border-dashed border-night/40 bg-paper/80 px-2.5 py-1.5 font-type text-[13px] leading-4 text-night/80 hover:bg-white">{c}</button>
                  ))}
                </div>
              )}
              <div ref={endRef} />
            </div>

            <footer className="relative border-t-2 border-dashed border-night/25 bg-paper/90 px-4 pb-3 pt-3">
              <form onSubmit={(e) => { e.preventDefault(); send(input); }} className="flex items-end gap-2">
                <textarea value={input} rows={1} onChange={(e) => setInput(e.target.value)} placeholder="Ask about a witness, a stamp, a number…"
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
                  className="max-h-28 min-h-[2.6rem] flex-1 resize-none border-b-2 border-night/40 bg-white/70 px-3 py-2 font-body text-[15px] outline-none focus:border-stamp" />
                <button disabled={busy || !input.trim()} className="-rotate-1 border-[3px] border-stamp bg-stamp px-4 py-2 font-type text-sm font-bold tracking-[0.18em] text-paper shadow-[0_4px_0_#7d140f] disabled:opacity-40">SEND</button>
              </form>
              <p className="mt-2 text-[10px] leading-3 text-night/50">The partner only explains numbers the statistics computed. It never decides a verdict.</p>
            </footer>
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  );
}
