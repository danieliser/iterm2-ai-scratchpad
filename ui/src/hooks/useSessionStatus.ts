import { useEffect, useRef, useState } from "react";
import type { NoteScope } from "./useNotes";

export interface GitStatus {
  branch: string;
  dirty: number;
  ahead: number;
  behind: number;
}

export interface PanelStatus {
  session_id: string;
  cwd: string;
  job: string;
  git: GitStatus | null;
}

export interface SessionStatus {
  /** All panels share the same cwd — show single unified view */
  unified: boolean;
  /** The panels in this tab (1 for panel scope, N for tab scope) */
  panels: PanelStatus[];
}

const POLL_INTERVAL = 5000;

export function useSessionStatus(scope: NoteScope) {
  const [status, setStatus] = useState<SessionStatus | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval>>(undefined);

  useEffect(() => {
    if (scope !== "panel" && scope !== "tab") {
      setStatus(null);
      return;
    }

    let cancelled = false;

    const poll = async () => {
      try {
        const queryScope = scope === "tab" ? "tab" : "panel";
        const r = await fetch(`/api/session/status?scope=${queryScope}`);
        if (!r.ok) return;
        const data = await r.json();
        if (cancelled) return;

        let panels: PanelStatus[];
        if (data.panels) {
          panels = data.panels;
        } else {
          panels = [data];
        }

        // Unified if all panels share the same cwd
        const cwds = new Set(panels.map((p) => p.cwd).filter(Boolean));
        setStatus({
          unified: cwds.size <= 1,
          panels,
        });
      } catch {
        // silently ignore
      }
    };

    poll();
    timerRef.current = setInterval(poll, POLL_INTERVAL);

    return () => {
      cancelled = true;
      clearInterval(timerRef.current);
    };
  }, [scope]);

  return status;
}
