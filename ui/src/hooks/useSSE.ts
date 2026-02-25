import { useEffect, useRef, useState } from "react";
import type { Note } from "../types";

type SSECallbacks = {
  onNoteAdded: (note: Note) => void;
  onNotesCleared: () => void;
  onNotesUpdated: () => void;
  onSessionChanged: () => void;
  onTodosUpdated?: (data: { path?: string }) => void;
};

export function useSSE(callbacks: SSECallbacks) {
  const [connected, setConnected] = useState(false);
  const cbRef = useRef(callbacks);
  cbRef.current = callbacks;

  useEffect(() => {
    let es: EventSource | null = null;
    let retryTimeout: ReturnType<typeof setTimeout>;

    function connect() {
      es = new EventSource("/events");

      es.addEventListener("open", () => setConnected(true));

      es.addEventListener("note_added", (e) => {
        const note: Note = JSON.parse(e.data);
        cbRef.current.onNoteAdded(note);
      });

      es.addEventListener("notes_cleared", () => {
        cbRef.current.onNotesCleared();
      });

      es.addEventListener("notes_updated", () => {
        cbRef.current.onNotesUpdated();
      });

      es.addEventListener("session_changed", () => {
        cbRef.current.onSessionChanged();
      });

      es.addEventListener("todos_updated", (e) => {
        const data = JSON.parse(e.data);
        cbRef.current.onTodosUpdated?.(data);
      });

      es.onerror = () => {
        setConnected(false);
        es?.close();
        retryTimeout = setTimeout(connect, 3000);
      };
    }

    connect();

    return () => {
      es?.close();
      clearTimeout(retryTimeout);
    };
  }, []);

  return connected;
}
