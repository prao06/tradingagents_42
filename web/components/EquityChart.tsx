// Dependency-free responsive equity curve (inline SVG). Stretches to container
// width; fixed height keeps it compact on mobile.
export default function EquityChart({ points }: { points: { equity: number }[] }) {
  const vals = points
    .map((p) => p.equity)
    .filter((v) => typeof v === "number" && !Number.isNaN(v));
  if (vals.length < 2) return <div className="empty">Not enough data to plot.</div>;

  const W = 600;
  const H = 180;
  const pad = 10;
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  const x = (i: number) => pad + (i / (vals.length - 1)) * (W - 2 * pad);
  const y = (v: number) => H - pad - ((v - min) / span) * (H - 2 * pad);
  const d = vals.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const up = vals[vals.length - 1] >= vals[0];
  const color = up ? "var(--green)" : "var(--red)";

  return (
    <div style={{ width: "100%", height: 180 }}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        height="100%"
        preserveAspectRatio="none"
        role="img"
        aria-label="Equity curve"
      >
        <line x1={pad} y1={y(vals[0])} x2={W - pad} y2={y(vals[0])} stroke="var(--border)" strokeDasharray="4 4" />
        <path d={d} fill="none" stroke={color} strokeWidth={2} vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  );
}
