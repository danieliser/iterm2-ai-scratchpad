import React, { useState, useMemo } from "react";
import type { Note } from "../types";
import { formatTime } from "../lib/format";
import { parseNoteContent } from "../lib/markdown";

interface NoteWithStatus extends Note {
  status?: "active" | "done";
}

interface Props {
  note: NoteWithStatus;
  pinned: boolean;
  onTogglePin: () => void;
  onToggleDone?: () => void;
}

function NoteCardComponent({
  note,
  pinned,
  onTogglePin,
  onToggleDone,
}: Props) {
  const [copied, setCopied] = useState(false);
  const isDone = note.status === "done";

  const copy = () => {
    navigator.clipboard.writeText(note.text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const content = useMemo(() => parseNoteContent(note.text), [note.text]);

  return (
    <div className={`note${pinned ? " pinned" : ""}${isDone ? " done" : ""}`}>
      <div className="note-meta">
        <span className="note-source">{note.source || "unknown"}</span>
        <span>
          <span className="note-time" title={note.timestamp}>
            {formatTime(note.timestamp)}
          </span>
          {onToggleDone && (
            <button
              className="note-done"
              onClick={onToggleDone}
              title={isDone ? "Mark as active" : "Mark as done"}
              aria-label={isDone ? "Mark as active" : "Mark as done"}
            >
              {isDone ? "\u2713" : "\u25cb"}
            </button>
          )}
          <button
            className="note-pin"
            onClick={onTogglePin}
            title={pinned ? "Unpin" : "Pin to top"}
            aria-label={pinned ? "Unpin" : "Pin to top"}
          >
            {pinned ? "\u2605" : "\u2606"}
          </button>
        </span>
      </div>
      <div className="note-text">{content}</div>
      <div className="note-actions">
        <button className="btn" onClick={copy}>
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
    </div>
  );
}

export const NoteCard = React.memo(NoteCardComponent);
