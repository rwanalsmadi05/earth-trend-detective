import type { CaseResponse } from "../api/types";
import { bigNumber } from "./format";

const slug = (d: CaseResponse) => d.place.name.split(",")[0].toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "case";

function save(url: string, name: string) {
  const a = document.createElement("a"); a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
}

export async function downloadCardPng(node: HTMLElement, d: CaseResponse) {
  const { toPng } = await import("html-to-image");
  await document.fonts?.ready;
  const url = await toPng(node, { width: 1080, height: 1080, pixelRatio: 1, cacheBust: true });
  save(url, `case-card-${slug(d)}.png`);
}

// jsPDF's built-in fonts are Latin-1 only, so swap the few characters outside it.
const L1 = (s: string) => s.replace(/·/g, "-").replace(/−/g, "-").replace(/→/g, "->").replace(/…/g, "...").replace(/[“”]/g, '"').replace(/[’]/g, "'").replace(/≥/g, ">=").replace(/[^\x00-\xFF]/g, "");
const pf = (p: number) => (p < 0.0001 ? "<0.0001" : p.toFixed(4));

export async function downloadReportPdf(d: CaseResponse) {
  const { jsPDF } = await import("jspdf");
  const doc = new jsPDF({ unit: "pt", format: "a4" });
  const M = 40, W = 595 - 2 * M;
  let y = 46;
  const text = (s: string, size = 9.5, style: "normal" | "bold" | "italic" = "normal", gap = 3, indent = 0) => {
    doc.setFont("helvetica", style); doc.setFontSize(size);
    const lines = doc.splitTextToSize(L1(s), W - indent) as string[];
    for (const ln of lines) { doc.text(ln, M + indent, y); y += size * 1.28; }
    y += gap;
  };
  const head = (s: string) => { y += 4; doc.setDrawColor(200, 38, 30); doc.setLineWidth(1); doc.line(M, y - 9, M + 18, y - 9); text(s.toUpperCase(), 8.5, "bold", 3); };

  const place = d.place.name.split(",")[0];
  const ok = d.verdict.confirmed * 2 > d.verdict.total;

  doc.setFont("helvetica", "bold"); doc.setFontSize(8); doc.setTextColor(120);
  doc.text("EARTH TREND DETECTIVE  -  CASE REPORT  -  NASA SPACE APPS 2026", M, y); y += 20;
  doc.setTextColor(10, 14, 20);
  doc.setFont("helvetica", "bold"); doc.setFontSize(24); doc.text(L1(place), M, y); y += 8;
  // verdict stamp, top right
  doc.setDrawColor(ok ? 200 : 90, ok ? 38 : 100, ok ? 30 : 115); doc.setTextColor(ok ? 200 : 90, ok ? 38 : 100, ok ? 30 : 115); doc.setLineWidth(2.2);
  doc.rect(595 - M - 150, 38, 150, 34, "S"); doc.setFontSize(15); doc.text(ok ? "CONFIRMED" : "NOT PROVEN", 595 - M - 75, 60, { align: "center" });
  doc.setTextColor(10, 14, 20); y += 8;
  text(`${d.place.lat.toFixed(2)} N, ${d.place.lon.toFixed(2)} E  -  ${d.period.start}-${d.period.end}  -  question: "${d.cleaned_question?.trim() || d.question}"`, 9.5, "normal", 2);
  text(`${d.verdict.confirmed} of ${d.verdict.total} witnesses confirm. ${d.verdict.headline}`, 10, "bold", 4);

  // ---- numbers table ----
  head("Results");
  const cols = [0, 128, 196, 312, 356, 404, 436]; // x offsets
  doc.setFont("helvetica", "bold"); doc.setFontSize(8); doc.setTextColor(110);
  ["Variable", "Change*", "Sen / decade", "tau", "p-value", "n", "Verdict"].forEach((h, i) => doc.text(h, M + cols[i], y));
  y += 5; doc.setDrawColor(190); doc.setLineWidth(0.5); doc.line(M, y, M + W, y); y += 11;
  doc.setTextColor(10, 14, 20);
  for (const w of d.witnesses) {
    const b = bigNumber(w);
    const change = `${b.sign}${b.value}${b.unit === "°C" ? " C" : b.unit === "%" ? " %" : b.unit}`;
    const ex = d.expert?.[w.variable];
    doc.setFont("helvetica", "normal"); doc.setFontSize(9);
    const row = [L1(w.label), L1(change), `${w.stats.sen_per_decade.toPrecision(3)} ${L1(w.unit)}`, w.stats.tau.toFixed(3), pf(w.stats.p), String(ex?.n_tested ?? w.stats.n), w.verdict + (ex?.borderline && w.verdict === "CONFIRMED" ? " (b)" : "")];
    row.forEach((c, i) => doc.text(c, M + cols[i], y, { maxWidth: (cols[i + 1] ?? W) - cols[i] - 4 }));
    y += 14;
  }
  y += 2;
  text("* Temperature and hot days: total change over the period. Other variables: percent change against the 1981-1990 baseline.  (b) = borderline: p is close to 0.05.", 7.5, "italic", 4);
  for (const w of d.witnesses) {
    const ex = d.expert?.[w.variable];
    text(`${w.label}: ${w.headline}${ex ? `  [${ex.method}, tested on ${ex.test_on}]` : ""}`, 8, "italic", 1);
  }

  // ---- method ----
  head("Method");
  text("1. Seasonality removed: each calendar month's long-term mean is subtracted from the monthly values, leaving anomalies.", 9, "normal", 1);
  text("2. Trend test: modified Mann-Kendall with the Hamed-Rao autocorrelation correction (lag cap 12) on the monthly anomalies; tau and p are reported. Annual-count variables (very hot days) are tested on annual values.", 9, "normal", 1);
  text("3. How much: Sen's slope, reported per decade and as total change over the period in real units, plus percent change against the 1981-1990 baseline.", 9, "normal", 1);
  text("4. Verdict: CONFIRMED when p < 0.05, otherwise NOT PROVEN. The verdict comes from this arithmetic only. The AI partner only chooses variables from a fixed catalog and explains results; it never invents numbers or decides significance.", 9, "normal", 1);
  text("5. Maps: the same test is run in every grid cell and Benjamini-Hochberg false-discovery-rate correction is applied before a cell is coloured as significant.", 9, "normal", 1);
  text("6. Chain of evidence: lagged cross-correlation (0-6 months) between anomaly series shows which variable moved first. It is correlation, not causation.", 9, "normal", 2);

  // ---- sources ----
  head("Data sources");
  const seen = new Set<string>();
  for (const w of d.witnesses) {
    if (seen.has(w.source)) continue; seen.add(w.source);
    let u = w.source_url; try { const x = new URL(w.source_url); u = x.origin + x.pathname; } catch { /* keep */ }
    text(`${w.source.replace(/·/g, "-")}  -  ${u}`, 8.5, "normal", 1);
  }
  text("Satellite photos: NASA Worldview / GIBS snapshot API (https://wvs.earthdata.nasa.gov/)", 8.5, "normal", 2);
  text(`${d.data_label.origin === "mock" ? "SIMULATED DEMO DATA" : d.data_label.origin === "cache" ? "Cached data" : "Live data"}, fetched ${d.data_label.fetched}.`, 8.5, "normal", 2);

  // ---- limitations ----
  head("Limitations");
  text("NASA POWER is model/reanalysis-based at about 0.5 degree resolution, so it describes the area, not a single point. NDVI starts in 2000. A significant trend shows that a change happened, not why. Borderline results (p close to 0.05) deserve extra caution.", 8.5, "normal", 0);

  doc.setFontSize(7.5); doc.setTextColor(130); doc.setFont("helvetica", "normal");
  doc.text(`Generated ${new Date().toISOString().slice(0, 10)} by Earth Trend Detective`, M, 818);
  doc.save(`case-report-${slug(d)}.pdf`);
}
