interface Props {
  values: number[];
  label?: string;
}

const COLORS = ["#569cd6", "#4ec94e", "#e0c040", "#c586c0", "#ce9178", "#9cdcfe"];

export function Chart({ values, label }: Props) {
  const max = Math.max(...values, 1);

  return (
    <>
      <div className="widget-chart">
        {values.map((v, i) => {
          const h = Math.round((v / max) * 36);
          return (
            <div
              key={i}
              className="widget-chart-bar"
              style={{ height: h, background: COLORS[i % COLORS.length] }}
              data-val={v}
            />
          );
        })}
      </div>
      {label && (
        <div className="widget-chart-label">
          <span>{label}</span>
        </div>
      )}
    </>
  );
}
