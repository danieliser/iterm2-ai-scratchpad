interface Props {
  value: number;
  label?: string;
}

export function ProgressBar({ value, label }: Props) {
  const v = Math.min(100, Math.max(0, value));
  const color =
    v >= 80 ? "#4ec94e" : v >= 50 ? "#e0c040" : v >= 25 ? "#569cd6" : "#f44747";

  return (
    <div className="widget-progress">
      {label && <span style={{ fontSize: 10, color: "#d4d4d4" }}>{label}</span>}
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
