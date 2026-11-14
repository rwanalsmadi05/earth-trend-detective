// API shape for POST /case. CLAUDE.md names the endpoint but not the JSON, so this
// is the contract the frontend assumes; the backend should match it (or tell us to adapt).
export type VariableId =
  | "T2M" | "T2M_MAX" | "PRECTOTCORR" | "GWETROOT" | "GWETTOP" | "RH2M" | "ALLSKY_SFC_SW_DWN" | "NDVI" | "HOT_DAYS";

export type Verdict = "CONFIRMED" | "NOT PROVEN";

export interface Witness {
  variable: VariableId;
  label: string;                 // "Rainfall"
  unit: string;                  // "mm/day"
  reason: string;                // partner's reasoning for picking it
  source: string;                // "NASA POWER (PRECTOTCORR)"
  source_url: string;
  start_year: number;            // NDVI = 2000
  images: { before: SatImage; after: SatImage };
  stats: {
    n: number;                   // months used
    tau: number;                 // Mann-Kendall (Hamed-Rao)
    p: number;
    sen_per_decade: number;      // real units
    total_change: number;        // real units over period
    pct_change: number;          // vs 1981-1990 baseline
  };
  verdict: Verdict;              // decided by math only
  headline: string;              // big plain-language result (template-generated)
  direction: "up" | "down";
  series: { year: number; value: number }[]; // annual mean of de-seasonalised anomalies
}
export interface ExpertItem {
  method: string;            // "hamed-rao" | "trend-free pre-whitening" ...
  reason: string | null;     // why a test failed, if it did
  n_months: number | null;
  n_tested: number;
  borderline: boolean;       // computed by the backend, never by the UI
  test_on: string;
  baseline: number;
  tau: number; p: number; sen_per_decade: number;
}
export interface SatImage { date: string; url: string; }

export interface CaseResponse {
  case_id: string;
  question: string;              // the text the user typed
  cleaned_question?: string;     // planner's tidied question; optional, falls back to `question`
  place: { name: string; name_ar: string; lat: number; lon: number };
  period: { start: number; end: number };
  witnesses: Witness[];
  chain: { from: VariableId; to: VariableId; lag_months: number; r: number }[]; // correlation, not causation
  hints: { after: VariableId; text: string }[];
  verdict: { confirmed: number; total: number; headline: string };
  expert?: Record<string, ExpertItem>; // from POST /case/expert (absent for mock data)
  data_label: { origin: "live" | "cache" | "mock"; fetched: string };
}

// GET /lifetime?place=<name>&birth_year=<yyyy>  (planned backend endpoint; the frontend falls back to a labelled mock until it exists)
export interface LifetimeItem {
  variable: VariableId;
  label: string;
  value: number;            // signed total change from birth_year to end_year, in display_unit
  display_unit: string;     // "°C" | "%" | " days"
  headline: string;         // plain-language sentence, e.g. "1.1 °C hotter since 2005"
  direction: "up" | "down";
  verdict: Verdict;         // decided by the statistics, never by the UI
  p: number;
  source: string;
}
export interface LifetimeResponse {
  place: { name: string; lat: number; lon: number };
  birth_year: number;       // as used (clamped to the data period)
  end_year: number;
  years: number;
  items: LifetimeItem[];    // three giant numbers
  data_label: { origin: "live" | "cache" | "mock"; fetched: string };
}

// GET /grid?variable=<VariableId>&bbox=<west>,<south>,<east>,<north>   (planned backend endpoint)
// One trend test per grid cell, Benjamini-Hochberg FDR-corrected; `significant` is the corrected decision.
export interface GridCell {
  lat: number; lon: number;       // cell centre
  value: number;                  // signed total change start_year -> end_year, in display_unit (Sen's slope * years)
  q: number;                      // FDR-adjusted p-value
  significant: boolean;           // q < 0.05
  verdict: Verdict;
  series: number[];               // annual anomaly in display_unit, aligned with `years` (drives the time slider)
}
export interface GridResponse {
  variable: VariableId;
  label: string;
  display_unit: string;           // "°C" | "%" | " days"
  words: { up: string; down: string }; // plain words for the legend/tooltip: "hotter"/"cooler", "more rain"/"less rain"
  bbox: [number, number, number, number]; // west, south, east, north
  step: number;                   // cell size in degrees
  years: number[];
  cells: GridCell[];
  fdr: "benjamini-hochberg";
  data_label: { origin: "live" | "cache" | "mock"; fetched: string };
}

// GET /twist?case_id=<id>   (planned backend endpoint). found=false -> the UI hides The Twist.
export interface TwistSide { name: string; lat: number; lon: number; value: number; display_unit: string; p: number; verdict: Verdict; }
export interface TwistResponse {
  found: boolean;
  variable?: VariableId;
  label?: string;
  words?: { up: string; down: string };
  a?: TwistSide;                  // the case place
  b?: TwistSide;                  // strongest significant trend of the opposite sign
  sentence?: string;              // one plain sentence from the backend
  data_label?: { origin: "live" | "cache" | "mock"; fetched: string };
}

// POST /case, manual mode: explicit place, variables and period instead of a question. No LLM involved.
// Field names match the backend's existing CaseRequest.
export interface ManualCaseRequest {
  question?: string;           // optional, "" for a manual case
  place?: string;              // display name
  lat: number; lon: number;
  variables: VariableId[];     // chosen from the fixed catalog
  start: number; end: number;  // 1981..latest full year (NDVI: 2000+)
}

// GET /game/round?case_id=<id>&want=<CONFIRMED|NOT PROVEN>&exclude=<VAR,VAR>   (planned backend endpoint)
// One round of "Real or noise?". The series is shown unlabeled; `verdict` is the real modified Mann-Kendall result.
export interface GameRound {
  variable: VariableId;
  label: string;
  unit: string;
  place: { name: string; lat: number; lon: number };
  period: { start: number; end: number };
  series: { year: number; value: number }[]; // annual mean of de-seasonalised anomalies
  verdict: Verdict;           // the real test result: the only source of "the answer"
  p: number; tau: number; sen_per_decade: number; n: number;
  borderline?: boolean;
  explanation: string;        // one plain line
  data_label: { origin: "live" | "cache" | "mock"; fetched: string };
}
