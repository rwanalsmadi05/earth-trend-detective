import type { Witness } from "../api/types";

export interface Big { sign: "+" | "−" | ""; value: string; unit: string; }

export const digitsFor = (unit: string, v: number) => (unit.trim() === "days" || (unit === "%" && Math.abs(v) >= 1) ? 0 : 1);

export function formatBig(v: number, unit: string): Big {
  return { sign: v > 0 ? "+" : v < 0 ? "−" : "", value: Math.abs(v).toFixed(digitsFor(unit, v)), unit };
}

// The huge number on each polaroid, taken straight from the computed stats (never invented):
// temperature -> total °C change, hot days -> total extra days/yr, everything else -> % vs the 1981-1990 baseline.
export function bigNumber(w: Witness): Big {
  const absolute = w.variable === "T2M" || w.variable === "T2M_MAX" || w.variable === "HOT_DAYS";
  const v = absolute ? w.stats.total_change : w.stats.pct_change;
  return formatBig(v, w.variable === "HOT_DAYS" ? " days" : absolute ? "°C" : "%");
}
