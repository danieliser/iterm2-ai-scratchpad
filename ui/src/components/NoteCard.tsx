import React, { useState, useMemo, useCallback } from "react";
import { motion } from "motion/react";
import type { Note } from "../types";
import { formatTime } from "../lib/format";
import { parseNoteContent } from "../lib/markdown";
import { activateSession } from "../lib/api";

interface NoteWithStatus extends Note {
  status?: "active" | "done";
}

interface Props {
  note: NoteWithStatus;
  pinned: boolean;
  onTogglePin: () => void;
  onToggleDone?: () => void;
}

const springTransition = { type: "spring" as const, stiffness: 500, damping: 30 };

function NoteCardComponent({
  note,
  pinned,
  onTogglePin,
  onToggleDone,
}: Props) {
  const [copied, setCopied] = useState(false);
  const isDone = note.status === "done";

  const copy = useCallback(() => {
    navigator.clipboard.writeText(note.text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [note.text]);

  const handleSourceClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (note.session_id && note.session_id !== "default") {
      activateSession(note.session_id);
    }
  }, [note.session_id]);

  const hasSession = note.session_id && note.session_id !== "default";

  const content = useMemo(() => parseNoteContent(note.text), [note.text]);

  const preview = useMemo(() => {
    return note.text.replace(/\[.*?\]|\n/g, " ").slice(0, 120).trim();
  }, [note.text]);

  // Collapsed single-line for dismissed notes
  if (isDone) {
    return (
      <motion.div
        layout
        className="note dismissed"
        onClick={onToggleDone}
        title="Click to restore"
        initial={{ opacity: 0, height: 0 }}
        animate={{ opacity: 0.6, height: "auto" }}
        exit={{ opacity: 0, height: 0, marginBottom: 0 }}
        transition={springTransition}
      >
        {hasSession ? (
          <button className="note-source clickable" onClick={handleSourceClick} title="Jump to tab">
            {note.source || "unknown"}
          </button>
        ) : (
          <span className="note-source">{note.source || "unknown"}</span>
        )}
        <span className="note-preview">{preview}</span>
        <span className="note-time" title={note.timestamp}>
          {formatTime(note.timestamp)}
        </span>
        <button
          className="note-restore"
          onClick={(e) => {
            e.stopPropagation();
            onToggleDone?.();
          }}
          aria-label="Restore note"
        >
          ○
        </button>
      </motion.div>
    );
  }

  return (
    <motion.div
      layout
      className={`note${pinned ? " pinned" : ""}`}
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, height: 0, marginBottom: 0, overflow: "hidden" }}
      transition={springTransition}
    >
      <div className="note-meta">
        {hasSession ? (
          <button className="note-source clickable" onClick={handleSourceClick} title="Jump to tab">
            {note.source || "unknown"}
          </button>
        ) : (
          <span className="note-source">{note.source || "unknown"}</span>
        )}
        <span className="note-time" title={note.timestamp}>
          {formatTime(note.timestamp)}
        </span>
        <div className="note-actions">
          <button
            className={`note-action-btn${pinned ? " pinned" : ""}`}
            onClick={onTogglePin}
            title={pinned ? "Unpin" : "Pin to top"}
            aria-label={pinned ? "Unpin" : "Pin to top"}
          >
            {pinned ? "★" : "☆"}
          </button>
          {onToggleDone && (
            <button
              className="note-action-btn"
              onClick={onToggleDone}
              title="Dismiss"
              aria-label="Dismiss note"
            >
              ✓
            </button>
          )}
          <button
            className={`note-action-btn${copied ? " copied" : ""}`}
            onClick={copy}
            title={copied ? "Copied!" : "Copy"}
            aria-label="Copy note"
          >
            {copied ? "✓" : "⊕"}
          </button>
        </div>
      </div>
      <div className="note-text">{content}</div>
    </motion.div>
  );
}

export const NoteCard = React.memo(NoteCardComponent);
