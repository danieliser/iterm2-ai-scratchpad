interface Props {
  content: string;
}

export function Diff({ content }: Props) {
  const lines = content.trim().split("\n");

  return (
    <div className="widget-diff">
      {lines.map((line, i) => {
        let cls = "widget-diff-line widget-diff-ctx";
        if (line.startsWith("+")) cls = "widget-diff-line widget-diff-add";
        else if (line.startsWith("-")) cls = "widget-diff-line widget-diff-del";
        return (
          <div key={i} className={cls}>
            {line}
          </div>
        );
      })}
    </div>
  );
}
