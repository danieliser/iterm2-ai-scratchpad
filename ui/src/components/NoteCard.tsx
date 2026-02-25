import { useState } from "react";
import type { Note } from "../types";
import { formatTime } from "../lib/format";
import { parseNoteContent } from "../lib/markdown";

interface Props {
  note: Note;
  pinned: boolean;
  onTogglePin: () => void;
}

export function NoteCard({ note, pinned, onTogglePin }: Props) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard.writeText(note.text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className={`note${pinned ? " pinned" : ""}`}>
      <div className="note-meta">
        <span className="note-source">{note.source || "unknown"}</span>
        <span>
          <span className="note-time" title={note.timestamp}>
            {formatTime(note.timestamp)}
          </span>
          <span className="note-pin" onClick={onTogglePin} title={pinned ? "Unpin" : "Pin to top"}>
            {pinned ? "\u2605" : "\u2606"}
          </span>
        </span>
      </div>
      <div className="note-text">{parseNoteContent(note.text)}</div>
      <div className="note-actions">
        <button className="btn" onClick={copy}>
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
    </div>
  );
}
