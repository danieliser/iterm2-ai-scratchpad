import type { NoteScope } from "../hooks/useNotes";

interface Props {
  connected: boolean;
  onClear: () => void;
  scope: NoteScope;
  onScopeChange: (scope: NoteScope) => void;
  sessionId: string;
  noteCount: number;
  totalCount: number;
}

export function Header({
  connected,
  onClear,
  scope,
  onScopeChange,
  sessionId,
  noteCount,
  totalCount,
}: Props) {
  const sessionLabel = sessionId && sessionId !== "default"
    ? sessionId.slice(0, 8)
    : "default";

  return (
    <div className="header">
      <div className="header-top">
        <h1>AI Scratchpad</h1>
        <div className="scope-toggle">
          <button
            className={`scope-btn${scope === "all" ? " active" : ""}`}
            onClick={() => onScopeChange("all")}
            title="Show notes from all sessions"
          >
            All
          </button>
          <button
            className={`scope-btn${scope === "tab" ? " active" : ""}`}
            onClick={() => onScopeChange("tab")}
            title="Show notes from active session only"
          >
            Active
          </button>
        </div>
        <span className={`status${connected ? "" : " disconnected"}`}>
          {connected ? "live" : "disconnected"}
        </span>
        <button className="btn" onClick={onClear}>
          Clear All
        </button>
      </div>
      <div className="header-meta">
        <span className="meta-session" title={sessionId}>
          {scope === "tab" ? `session: ${sessionLabel}` : "all sessions"}
        </span>
        <span className="meta-count">
          {noteCount}{noteCount !== totalCount ? ` / ${totalCount}` : ""} notes
        </span>
      </div>
    </div>
  );
}
