import { execCommand } from "../../lib/api";

interface Props {
  label: string;
  url: string;
}

export function LinkCard({ label, url }: Props) {
  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    execCommand(`open ${url}`, false, 5);
  };

  return (
    <a
      className="widget-link"
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      onClick={handleClick}
    >
      <span className="widget-link-icon">&#128279;</span>
      {label}
    </a>
  );
}
