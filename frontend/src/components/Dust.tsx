import { useMemo } from "react";
import { useReducedMotion } from "framer-motion";

const r = (i: number, s: number) => { const x = Math.sin(i * 91.7 + s * 17.3) * 43758.5453; return x - Math.floor(x); };

// floating dust in the spotlight; not rendered at all when the user prefers reduced motion
export default function Dust({ count = 46 }: { count?: number }) {
  const reduced = useReducedMotion();
  const motes = useMemo(() => Array.from({ length: count }, (_, i) => ({
    left: 12 + r(i, 1) * 76, top: 25 + r(i, 2) * 70, size: 1 + r(i, 3) * 2.6,
    d: 10 + r(i, 4) * 14, delay: -r(i, 5) * 20, dx: (r(i, 6) - 0.5) * 70, o: 0.25 + r(i, 7) * 0.5,
  })), [count]);
  if (reduced) return null;
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      {motes.map((m, i) => (
        <span key={i} className="dust" style={{ left: `${m.left}%`, top: `${m.top}%`, width: m.size, height: m.size, ["--d" as string]: `${m.d}s`, ["--delay" as string]: `${m.delay}s`, ["--dx" as string]: `${m.dx}px`, ["--o" as string]: m.o }} />
      ))}
    </div>
  );
}
