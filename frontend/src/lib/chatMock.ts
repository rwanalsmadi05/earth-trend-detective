import type { CaseResponse, VariableId, Witness } from "../api/types";
import { bigNumber } from "./format";

const KEYS: [VariableId, RegExp][] = [
  ["HOT_DAYS", /hot days?|35|extreme heat/i],
  ["T2M_MAX", /max(imum)? temp/i],
  ["T2M", /temperat|\bhot\b|warm|heat/i],
  ["PRECTOTCORR", /rain|precip|drought|dry up|drying/i],
  ["GWETTOP", /surface/i],
  ["GWETROOT", /root|soil|moist/i],
  ["NDVI", /ndvi|plant|veget|green/i],
  ["RH2M", /humid/i],
  ["ALLSKY_SFC_SW_DWN", /solar|sun|radiation/i],
];

const pTxt = (p: number) => (p < 0.0001 ? "p < 0.0001" : `p = ${p.toFixed(3)}`);

function describe(w: Witness, ctx: CaseResponse): string {
  const ex = ctx.expert?.[w.variable];
  const border = !!ex?.borderline && w.verdict === "CONFIRMED";
  const why = w.verdict === "CONFIRMED"
    ? (border ? "It only just passes the bar, so treat it as borderline." : "Chance alone would rarely draw a trend this clear.")
    : "The test cannot tell this wiggle from chance. That is not the same as saying nothing changed.";
  const b = bigNumber(w);
  void b;
  return `${w.label}: ${w.headline}. Verdict: ${w.verdict} (${pTxt(w.stats.p)}, tau ${w.stats.tau.toFixed(2)}, n = ${w.stats.n}). ${why}`;
}

// SIMULATED placeholder until POST /chat exists. It only rephrases numbers and verdicts already computed for this case.
export function mockReply(ctx: CaseResponse, message: string): string {
  const m = message.toLowerCase();
  const hit = KEYS.find(([v, re]) => ctx.witnesses.some((w) => w.variable === v) && re.test(m))?.[0];
  const w = hit ? ctx.witnesses.find((x) => x.variable === hit) : undefined;

  if (/strongest|most (solid|certain)/i.test(m)) {
    const s = [...ctx.witnesses].sort((a, b) => a.stats.p - b.stats.p)[0];
    return "The strongest witness here: " + describe(s, ctx);
  }
  if (/next|check|what should/i.test(m)) {
    const bl = ctx.witnesses.find((x) => ctx.expert?.[x.variable]?.borderline && x.verdict === "CONFIRMED");
    return `Try the Where map to see whether the trend repeats in nearby places, or pick other witnesses yourself.${bl ? ` Be careful with ${bl.label.toLowerCase()}: its result is borderline.` : ""}`;
  }
  if (/why|cause|because|reason/i.test(m)) {
    const link = ctx.chain[0];
    return `The statistics show that a change happened, not why. Correlation is not causation.${link ? ` For example ${link.from} moved about ${link.lag_months} month(s) before ${link.to} (r = ${link.r}).` : ""}`;
  }
  if (w) return describe(w, ctx);
  if (/noise|chance|real|confirm|sure|true/i.test(m)) {
    const parts = ctx.witnesses.map((x) => `${x.label}: ${x.verdict}`);
    return "The stamps come from the statistical test (p < 0.05), not from the AI. " + parts.join(" · ");
  }
  return `${ctx.verdict.confirmed} of ${ctx.verdict.total} witnesses show a significant change in ${ctx.place.name.split(",")[0]}. Ask me about a specific witness, a stamp or a number.`;
}
