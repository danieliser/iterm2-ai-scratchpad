interface Props {
  value: string;
  label: string;
  trend?: "up" | "down" | "flat";
}

const ARROWS = { up: "\u25B2", down: "\u25BC", flat: "\u2584" };

export function Metric({ value, label, trend = "flat" }: Props) {
  return (
    <div className="widget-metric">
      <span className="widget-metric-value">{value}</span>
      <span className="widget-metric-label">{label}</span>
      <span className={`widget-metric-trend ${trend}`}>{ARROWS[trend]}</span>
    </div>
  );
}
