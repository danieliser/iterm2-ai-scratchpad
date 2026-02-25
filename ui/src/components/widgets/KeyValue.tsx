interface Props {
  content: string;
}

export function KeyValue({ content }: Props) {
  const pairs = content
    .trim()
    .split("|")
    .map((pair) => {
      const idx = pair.indexOf(":");
      if (idx === -1) return null;
      return { key: pair.slice(0, idx).trim(), val: pair.slice(idx + 1).trim() };
    })
    .filter(Boolean) as { key: string; val: string }[];

  return (
    <div className="widget-kv">
      {pairs.map((p, i) => (
        <span key={i} style={{ display: "contents" }}>
          <span className="widget-kv-key">{p.key}</span>
          <span className="widget-kv-val">{p.val}</span>
        </span>
      ))}
    </div>
  );
}
