import type { Toast } from "../hooks/useToast";

interface Props {
  toasts: Toast[];
}

export function ToastContainer({ toasts }: Props) {
  if (toasts.length === 0) return null;

  return (
    <div className="toast-container">
      {toasts.map((t) => (
        <div key={t.id} className={`toast${t.type ? ` ${t.type}` : ""}`}>
          {t.text}
        </div>
      ))}
    </div>
  );
}
