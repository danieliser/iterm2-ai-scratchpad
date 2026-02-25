interface Props {
  type: "success" | "warning" | "error" | "info";
  label?: string;
}

export function Badge({ type, label }: Props) {
  return (
    <span className={`widget-badge widget-badge-${type}`}>
      {label || type}
    </span>
  );
}
