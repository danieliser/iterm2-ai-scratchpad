interface Props {
  value: number;
  label?: string;
}

export function ProgressBar({ value, label }: Props) {
  const v = Math.min(100, Math.max(0, value));
  const color =
    v >= 80 ? "var(--accent-green)" : v >= 50 ? "var(--accent-yellow)" : v >= 25 ? "var(--accent-blue)" : "var(--accent-red)";

  return (
    <div className="widget-progress">
      {label && <span style={{ fontSize: 10, color: "var(--text-primary)" }}>{label}</span>}
      <div className="widget-progress-bar">
        <div
          className="widget-progress-fill"
          style={{ width: `${v}%`, background: color }}
        />
      </div>
      <span className="widget-progress-label">{v}%</span>
    </div>
  );
}
