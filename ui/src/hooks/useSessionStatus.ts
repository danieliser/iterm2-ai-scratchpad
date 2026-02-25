import { useEffect, useRef, useState } from "react";
import type { NoteScope } from "./useNotes";

export interface GitStatus {
  branch: string;
  dirty: number;
  ahead: number;
  behind: number;
}

export interface SessionStatus {
  cwd: string;
  job: string;
  git: GitStatus | null;
}

const POLL_INTERVAL = 5000;

export function useSessionStatus(scope: NoteScope) {
  const [status, setStatus] = useState<SessionStatus | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval>>();

  useEffect(() => {
    if (scope !== "panel") {
      setStatus(null);
      return;
    }

    let cancelled = false;

    const poll = async () => {
      try {
        const r = await fetch("/api/session/status");
        if (!r.ok) return;
        const data = await r.json();
        if (!cancelled) setStatus(data);
      } catch {
        // silently ignore — server may not support this yet
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
