import { useCallback, useEffect, useState } from "react";
import type { TodosResponse } from "../types";

export function useTaskWatcher(scope: "all" | "tab" | "panel" = "tab") {
  const [data, setData] = useState<TodosResponse>({ sessions: [], teams: [] });

  const load = useCallback(async () => {
    try {
      const params = scope === "all" ? "?scope=all" : "";
      const r = await fetch(`/api/todos${params}`);
      const json: TodosResponse = await r.json();
      setData(json);
    } catch {
      // Server may not support this endpoint yet
    }
  }, [scope]);

  useEffect(() => {
    load();
  }, [load]);

  return { ...data, reload: load };
}
