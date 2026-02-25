import { useState } from "react";

interface Props {
  label: string;
  content: string;
}

export function Clipboard({ label, content }: Props) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="widget-clip">
      <span className="widget-clip-label">{label}</span>
      <span className="widget-clip-content">{content}</span>
      <button className="widget-clip-btn" onClick={copy}>
        {copied ? "Copied!" : "Copy"}
      </button>
    </div>
  );
}
