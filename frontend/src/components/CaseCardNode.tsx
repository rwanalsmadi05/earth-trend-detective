import { forwardRef } from "react";
import type { CaseResponse } from "../api/types";
import { bigNumber, isOrange } from "../lib/format";

// Fixed 1080x1080 card for the PNG export. Inline px styles on purpose: it is rendered off-screen at full size.
const CaseCardNode = forwardRef<HTMLDivElement, { data: CaseResponse }>(function CaseCardNode({ data }, ref) {
  const ok = data.verdict.confirmed * 2 > data.verdict.total;
  const stamp = ok ? "#ff4a3d" : "#a9b4c4";
  const ws = data.witnesses.slice(0, 5);
  const sources = [...new Set(data.witnesses.map((w) => w.source))];
  const place = data.place.name.split(",")[0];
  const cols = [0, 1, 2, 3, 2, 3][ws.length] || 3;
  return (
    <div ref={ref} style={{ width: 1080, height: 1080, position: "relative", overflow: "hidden", background: "radial-gradient(ellipse at 50% 0%, #1b2330 0%, #05070B 62%)", color: "#F4F1EA", fontFamily: "Inter, sans-serif", padding: 64, boxSizing: "border-box" }}>
      <div style={{ position: "absolute", left: "50%", top: 0, width: 520, height: 1080, transform: "translateX(-50%)", clipPath: "polygon(40% 0, 60% 0, 100% 100%, 0 100%)", background: "linear-gradient(to bottom, rgba(255,236,200,.16), transparent 70%)" }} />
      <div style={{ position: "relative" }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "JetBrains Mono, monospace", fontSize: 20, letterSpacing: 5, color: "rgba(244,241,234,.55)" }}>
          <span>EARTH TREND DETECTIVE</span><span>CASE Nº {data.case_id.slice(0, 8).toUpperCase()}</span>
        </div>
        <h1 style={{ margin: "34px 0 0", fontFamily: "Unbounded, sans-serif", fontWeight: 900, fontSize: 88, lineHeight: 1.02 }}>{place}</h1>
        <p style={{ margin: "10px 0 0", fontFamily: "JetBrains Mono, monospace", fontSize: 22, color: "rgba(244,241,234,.6)" }}>{data.place.lat.toFixed(2)}°N · {data.place.lon.toFixed(2)}°E · {data.period.start}–{data.period.end}</p>
        <p style={{ margin: "18px 0 0", fontFamily: "Special Elite, monospace", fontSize: 32, color: "rgba(244,241,234,.9)" }}>“{data.cleaned_question?.trim() || data.question}”</p>

        <div style={{ display: "flex", alignItems: "center", gap: 28, margin: "34px 0 30px" }}>
          <div style={{ transform: "rotate(-6deg)", border: `8px solid ${stamp}`, color: stamp, padding: "6px 26px", borderRadius: 14, fontFamily: "Special Elite, monospace", fontWeight: 700, fontSize: 64, letterSpacing: 4, textShadow: `0 0 20px ${stamp}`, boxShadow: `0 0 36px ${stamp}55` }}>
            {ok ? "CONFIRMED" : "NOT PROVEN"}
          </div>
          <p style={{ margin: 0, fontFamily: "Special Elite, monospace", fontSize: 28, lineHeight: 1.25, color: "rgba(244,241,234,.85)" }}>{data.verdict.confirmed} of {data.verdict.total} witnesses confirm</p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 22 }}>
          {ws.map((w) => {
            const b = bigNumber(w), color = w.verdict !== "CONFIRMED" ? "#8f96a3" : isOrange(w.variable, w.direction === "up" ? 1 : -1) ? "#FF8A3D" : "#7CC8FF", conf = w.verdict === "CONFIRMED";
            return (
              <div key={w.variable} style={{ background: "rgba(255,255,255,.05)", border: "1px solid rgba(255,255,255,.1)", borderRadius: 12, padding: "18px 22px" }}>
                <div style={{ fontFamily: "Unbounded, sans-serif", fontWeight: 900, fontSize: ws.length >= 5 ? 54 : 64, color, lineHeight: 1, textShadow: w.verdict === "CONFIRMED" ? `0 0 24px ${color}88` : "none" }}>{b.sign}{b.value}<span style={{ fontSize: "0.5em" }}>{b.unit}</span></div>
                <div style={{ marginTop: 8, fontFamily: "Special Elite, monospace", fontSize: 22 }}>{w.label}</div>
                <div style={{ marginTop: 6, fontFamily: "JetBrains Mono, monospace", fontSize: 15, letterSpacing: 2, color: conf ? "#ff5a4d" : "#a9b4c4" }}>{w.verdict} · p {w.stats.p < 0.001 ? "< 0.001" : `= ${w.stats.p.toFixed(3)}`}</div>
              </div>
            );
          })}
        </div>
      </div>

      <div style={{ position: "absolute", left: 64, right: 64, bottom: 48, fontFamily: "JetBrains Mono, monospace", fontSize: 15, lineHeight: 1.5, color: "rgba(244,241,234,.5)" }}>
        Sources: {sources.join(" · ")}<br />
        Verdicts: modified Mann-Kendall on de-seasonalised anomalies, p &lt; 0.05. Computed from the data, not by the AI. Orange = warmer, drier, more heat. Blue = cooler, wetter.<br />
        {data.data_label.origin === "mock" ? "SIMULATED DEMO DATA · " : data.data_label.origin === "cache" ? "Cached data · " : "Live data · "}fetched {data.data_label.fetched}
      </div>
    </div>
  );
});

export default CaseCardNode;
