interface Props {
  content: string;
}

export function KeyValue({ content }: Props) {
  // Support both formats: "K=V\nK2=V2" (documented) and "K:V|K2:V2" (legacy)
  const usesNewlines = content.includes("\n");
  const lines = usesNewlines ? content.trim().split("\n") : content.trim().split("|");
  const pairs = lines
    .map((pair) => {
      // Try = first (documented), fall back to : (legacy)
      let idx = pair.indexOf("=");
      if (idx === -1) idx = pair.indexOf(":");
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
