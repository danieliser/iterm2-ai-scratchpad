import { useEffect, useState } from "react";

interface Props {
  ports: number[];
}

type PortStatus = "checking" | "up" | "down";

export function PortMonitor({ ports }: Props) {
  const [statuses, setStatuses] = useState<Record<number, PortStatus>>(() =>
    Object.fromEntries(ports.map((p) => [p, "checking" as PortStatus])),
  );

  useEffect(() => {
    ports.forEach((port) => {
      fetch(`http://localhost:${port}/`, { mode: "no-cors" })
        .then(() => {
          setStatuses((prev) => ({ ...prev, [port]: "up" }));
        })
        .catch(() => {
          fetch(`http://localhost:${port}/health`, { mode: "no-cors" })
            .then(() => {
              setStatuses((prev) => ({ ...prev, [port]: "up" }));
            })
            .catch(() => {
              setStatuses((prev) => ({ ...prev, [port]: "down" }));
            });
        });
    });
  }, [ports.join(",")]);

  return (
    <div className="widget-ports">
      {ports.map((port) => (
        <span key={port} className="widget-port">
          <span className={`widget-port-dot ${statuses[port] || "checking"}`} />
          {port}
        </span>
      ))}
    </div>
  );
}
