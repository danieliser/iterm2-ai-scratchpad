import { useCallback, useState } from "react";

export interface Toast {
  id: number;
  text: string;
  type?: "error" | "warning" | "";
}

let _nextId = 0;

export function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const showToast = useCallback(
    (text: string, type: Toast["type"] = "") => {
      const id = ++_nextId;
      setToasts((prev) => [...prev, { id, text, type }]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 3000);
    },
    [],
  );

  return { toasts, showToast };
}
