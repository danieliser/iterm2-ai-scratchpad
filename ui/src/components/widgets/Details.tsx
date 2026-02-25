import { useState } from "react";

interface Props {
  title: string;
  children: React.ReactNode;
}

export function Details({ title, children }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div className={`widget-details${open ? " open" : ""}`}>
      <button
        className="widget-details-toggle"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <span className="widget-details-arrow">&#9654;</span>
        {title}
      </button>
      <div className="widget-details-body">{children}</div>
    </div>
  );
}
