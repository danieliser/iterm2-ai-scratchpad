interface Props {
  label: string;
  url: string;
}

export function LinkCard({ label, url }: Props) {
  return (
    <a
      className="widget-link"
      href={url}
      target="_blank"
      rel="noopener noreferrer"
    >
      <span className="widget-link-icon">&#128279;</span>
      {label}
    </a>
  );
}
