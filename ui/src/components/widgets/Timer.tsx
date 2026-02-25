import { useEffect, useState } from "react";
import { parseDuration, formatCountdown } from "../../lib/format";

interface Props {
  duration: string;
  label?: string;
}

export function Timer({ duration, label }: Props) {
  const [remaining, setRemaining] = useState(() => parseDuration(duration));

  useEffect(() => {
    if (remaining <= 0) return;
    const id = setInterval(() => {
      setRemaining((r) => Math.max(0, r - 1));
    }, 1000);
    return () => clearInterval(id);
  }, [remaining > 0]);

  return (
    <div className={`widget-timer${remaining <= 0 ? " expired" : ""}`}>
      <span className="widget-timer-icon">&#9202;</span>
      <span className="widget-timer-display">{formatCountdown(remaining)}</span>
      {label && <span className="widget-timer-label">{label}</span>}
    </div>
  );
}
