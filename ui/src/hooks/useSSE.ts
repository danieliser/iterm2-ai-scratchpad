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
  const retryCountRef = useRef(0);

  useEffect(() => {
    let es: EventSource | null = null;
    let retryTimeout: ReturnType<typeof setTimeout>;

    function connect() {
      es = new EventSource("/events");

      es.addEventListener("open", () => {
        setConnected(true);
        retryCountRef.current = 0;
      });

      es.addEventListener("note_added", (e) => {
        const note: Note = JSON.parse(e.data);
        cbRef.current.onNoteAdded(note);
      });

      es.addEventListener("note_updated", () => {
        cbRef.current.onNotesUpdated();
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
        // Exponential backoff with jitter: min 3s, max 30s
        const baseDelay = Math.min(3000 * Math.pow(2, retryCountRef.current), 30000);
        const jitter = Math.random() * 1000;
        const delay = baseDelay + jitter;
        retryCountRef.current++;
        retryTimeout = setTimeout(connect, delay);
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
