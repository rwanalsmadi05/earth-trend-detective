import type { VariableId, Witness } from "../api/types";

// Colour by meaning, not by sign: warming, less rain, drier soil, less humidity, less green, more hot days = ORANGE;
// cooling, more rain, wetter soil = BLUE. (Orange is the "stress" direction for the place.)
const WARM_UP = new Set<VariableId>(["T2M", "T2M_MAX", "HOT_DAYS", "ALLSKY_SFC_SW_DWN"]);
export const isOrange = (variable: VariableId, signed: number) => (WARM_UP.has(variable) ? signed > 0 : signed < 0);
export const ORANGE_HEX = "#FF8A3D", BLUE_HEX = "#7CC8FF"; // on dark backgrounds
export const ORANGE_INK = "#d4560e", BLUE_INK = "#1f78b4"; // on paper

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
