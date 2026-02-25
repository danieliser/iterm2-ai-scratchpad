import { useCallback, useEffect, useRef, useState } from "react";

export interface Toast {
  id: number;
  text: string;
  type?: "error" | "warning" | "";
}

let _nextId = 0;

export function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timeoutsRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(
    new Map(),
  );

  const showToast = useCallback(
    (text: string, type: Toast["type"] = "") => {
      const id = ++_nextId;
      setToasts((prev) => [...prev, { id, text, type }]);
      const timeout = setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
        timeoutsRef.current.delete(id);
      }, 3000);
      timeoutsRef.current.set(id, timeout);
    },
    [],
  );

  useEffect(() => {
    return () => {
      // Clear all timeouts on unmount
      for (const timeout of timeoutsRef.current.values()) {
        clearTimeout(timeout);
      }
      timeoutsRef.current.clear();
    };
  }, []);

  return { toasts, showToast };
}
