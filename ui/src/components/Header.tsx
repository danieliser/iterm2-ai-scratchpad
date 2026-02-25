import type { NoteScope } from "../hooks/useNotes";

interface Props {
  connected: boolean;
  onClear: () => void;
  scope: NoteScope;
  onScopeChange: (scope: NoteScope) => void;
}

export function Header({ connected, onClear, scope, onScopeChange }: Props) {
  return (
    <div className="header">
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
          title="Show notes from current tab only"
        >
          Tab
        </button>
      </div>
      <span className={`status${connected ? "" : " disconnected"}`}>
        {connected ? "live" : "disconnected"}
      </span>
      <button className="btn" onClick={onClear}>
        Clear All
      </button>
    </div>
  );
}
