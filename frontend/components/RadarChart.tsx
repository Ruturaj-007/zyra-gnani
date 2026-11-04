// Plain SVG radar chart for the three metrics. No chart library needed.

interface RadarProps {
  technical: number | null;
  problem: number | null;
  clarity: number | null;
}

const SIZE = 320;
const CENTER = SIZE / 2;
const RADIUS = 105;

// Three axes: top, bottom-right, bottom-left
const AXES = [
  { key: "technical", label: "Technical knowledge", angle: -90 },
  { key: "problem", label: "Problem solving", angle: 30 },
  { key: "clarity", label: "Communication clarity", angle: 150 },
] as const;

function point(angleDeg: number, fraction: number) {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: CENTER + Math.cos(rad) * RADIUS * fraction, y: CENTER + Math.sin(rad) * RADIUS * fraction };
}

const toPoints = (fractions: number[]) =>
  fractions.map((f, i) => point(AXES[i].angle, f)).map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

export default function RadarChart({ technical, problem, clarity }: RadarProps) {
  const values = [technical ?? 0, problem ?? 0, clarity ?? 0];
  const fractions = values.map((v) => Math.max(0, Math.min(100, v)) / 100);

  return (
    <svg
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      className="w-full max-w-sm mx-auto"
      role="img"
      aria-label={`Radar chart. Technical knowledge ${values[0]}, problem solving ${values[1]}, communication clarity ${values[2]}, each out of 100.`}
    >
      {/* Rings at 25, 50, 75 and 100 */}
      {[0.25, 0.5, 0.75, 1].map((ring) => (
        <polygon key={ring} points={toPoints([ring, ring, ring])} fill="none" stroke="#4f557d" strokeOpacity={0.5} />
      ))}

      {/* Axis lines */}
      {AXES.map((axis) => {
        const end = point(axis.angle, 1);
        return <line key={axis.key} x1={CENTER} y1={CENTER} x2={end.x} y2={end.y} stroke="#4f557d" strokeOpacity={0.5} />;
      })}

      {/* The candidate's shape */}
      <polygon points={toPoints(fractions)} fill="#cac5fe" fillOpacity={0.35} stroke="#cac5fe" strokeWidth={2} />
      {fractions.map((f, i) => {
        const p = point(AXES[i].angle, f);
        return <circle key={AXES[i].key} cx={p.x} cy={p.y} r={4} fill="#dddfff" />;
      })}

      {/* Labels with the score */}
      {AXES.map((axis, i) => {
        const p = point(axis.angle, 1.28);
        const anchor = axis.angle === -90 ? "middle" : axis.angle === 30 ? "start" : "end";
        const dy = axis.angle === -90 ? -4 : 6;
        return (
          <g key={axis.key}>
            <text x={p.x} y={p.y + dy} textAnchor={anchor} fill="#d6e0ff" fontSize={12} fontWeight={600}>
              {axis.label}
            </text>
            <text x={p.x} y={p.y + dy + 16} textAnchor={anchor} fill="#cac5fe" fontSize={14} fontWeight={700}>
              {technical === null && problem === null && clarity === null ? "–" : `${values[i]}/100`}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
