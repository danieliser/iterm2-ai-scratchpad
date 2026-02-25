interface Props {
  level: "error" | "warn" | "info" | "debug";
  content: string;
}

export function Log({ level, content }: Props) {
  return (
    <div className={`widget-log widget-log-${level}`}>{content.trim()}</div>
  );
}
