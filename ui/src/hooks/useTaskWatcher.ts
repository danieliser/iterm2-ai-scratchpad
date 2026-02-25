import { useCallback, useEffect, useState } from "react";
import type { TodosResponse } from "../types";

export function useTaskWatcher() {
  const [data, setData] = useState<TodosResponse>({ sessions: [], teams: [] });

  const load = useCallback(async () => {
    try {
      const r = await fetch("/api/todos");
      const json: TodosResponse = await r.json();
      setData(json);
    } catch {
      // Server may not support this endpoint yet
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { ...data, reload: load };
}
