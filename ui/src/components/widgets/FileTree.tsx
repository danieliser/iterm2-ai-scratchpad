interface Props {
  content: string;
}

export function FileTree({ content }: Props) {
  const lines = content.trim().split("\n");

  return (
    <div className="widget-tree">
      {lines.map((line, i) => {
        const isDir = /\/\s*$/.test(line);
        return (
          <span
            key={i}
            className={isDir ? "widget-tree-dir" : "widget-tree-file"}
          >
            {line}
            {"\n"}
          </span>
        );
      })}
    </div>
  );
}
