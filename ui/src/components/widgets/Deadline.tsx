import { useEffect, useState } from "react";

interface Props {
  target: string;
  label?: string;
}

function formatRemaining(diff: number): string {
  if (diff <= 0) {
    const ago = Math.abs(diff);
    const mins = Math.floor(ago / 60000);
    return mins < 60
      ? `${mins}m overdue`
      : `${Math.floor(mins / 60)}h ${mins % 60}m overdue`;
  }
  const days = Math.floor(diff / 86400000);
  const hrs = Math.floor((diff % 86400000) / 3600000);
  const mins = Math.floor((diff % 3600000) / 60000);
  if (days > 0) return `${days}d ${hrs}h`;
  if (hrs > 0) return `${hrs}h ${mins}m`;
  return `${mins}m`;
}

export function Deadline({ target, label }: Props) {
  const [now, setNow] = useState(Date.now);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(id);
  }, []);

  const targetMs = new Date(target).getTime();
  const diff = targetMs - now;
  const past = diff <= 0;
  const urgent = !past && diff < 3600000;

  return (
    <div
      className={`widget-deadline${past ? " past" : ""}${urgent ? " urgent" : ""}`}
    >
      <span className="widget-deadline-time">{formatRemaining(diff)}</span>
      {label && <span className="widget-deadline-label">{label}</span>}
    </div>
  );
}
