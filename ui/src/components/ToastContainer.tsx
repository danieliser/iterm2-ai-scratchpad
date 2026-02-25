import { AnimatePresence, motion } from "motion/react";
import type { Toast } from "../hooks/useToast";

interface Props {
  toasts: Toast[];
}

export function ToastContainer({ toasts }: Props) {
  return (
    <div className="toast-container" role="status" aria-live="polite">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.div
            key={t.id}
            className={`toast${t.type ? ` ${t.type}` : ""}`}
            initial={{ opacity: 0, x: 40 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 40 }}
            transition={{ type: "spring", stiffness: 400, damping: 25 }}
          >
            {t.text}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
