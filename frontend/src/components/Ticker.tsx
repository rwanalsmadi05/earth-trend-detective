const ITEMS = [
  "NASA POWER · monthly 1981 → 2025", "MODIS NDVI · from 2000", "Mann-Kendall (Hamed-Rao) · Sen's slope",
  "CONFIRMED means p < 0.05 — decided by math, never by the AI", "Blue = rising · Orange = falling",
  "Correlation is not causation", "POWER is reanalysis-based at ~0.5° resolution",
];
export default function Ticker() {
  const row = [...ITEMS, ...ITEMS];
  return (
    <div className="absolute inset-x-0 bottom-0 z-10 overflow-hidden border-t border-white/10 bg-black/40 py-2 backdrop-blur">
      <div className="ticker flex w-max gap-12 whitespace-nowrap font-mono text-[11px] tracking-wider text-paper/60">
        {row.map((t, i) => <span key={i}>◉ {t}</span>)}
      </div>
    </div>
  );
}
