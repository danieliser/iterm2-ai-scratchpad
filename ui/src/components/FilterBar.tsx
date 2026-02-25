interface Props {
  sources: string[];
  active: string;
  onSelect: (source: string) => void;
}

export function FilterBar({ sources, active, onSelect }: Props) {
  if (sources.length <= 1) return null;

  const all = ["all", ...sources];

  return (
    <div className="filters">
      {all.map((src) => (
        <button
          key={src}
          className={`filter-btn${active === src ? " active" : ""}`}
          onClick={() => onSelect(src)}
        >
          {src}
        </button>
      ))}
    </div>
  );
}
