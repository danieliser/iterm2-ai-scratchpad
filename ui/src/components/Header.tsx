import type { NoteScope } from "../hooks/useNotes";
import type { Theme } from "../hooks/useTheme";

interface Props {
  connected: boolean;
  onClear: () => void;
  scope: NoteScope;
  onScopeChange: (scope: NoteScope) => void;
  sessionId: string;
  noteCount: number;
  totalCount: number;
  theme: Theme;
  onToggleTheme: () => void;
  filtersVisible: boolean;
  onToggleFilters: () => void;
}

export function Header({
  connected,
  onClear,
  scope,
  onScopeChange,
  sessionId,
  noteCount,
  totalCount,
  theme,
  onToggleTheme,
  filtersVisible,
  onToggleFilters,
}: Props) {
  const sessionLabel = sessionId && sessionId !== "default"
    ? sessionId.slice(0, 7)
    : "default";

  return (
    <div className="header-group">
      {/* Title bar */}
      <div className="title-bar">
        <span className="title-text">AI Scratchpad</span>
        <div className="title-actions">
          <button
            className="icon-btn"
            onClick={onToggleTheme}
            title={`Theme: ${theme}`}
            aria-label="Toggle theme"
          >
            {theme === "cockpit" ? "◐" : "◑"}
          </button>
        </div>
      </div>

      {/* Toolbar row */}
      <div className="toolbar">
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
        <div className="toolbar-meta">
          <span className="meta-session" title={sessionId}>
            {scope === "tab" ? sessionLabel : "all sessions"}
          </span>
          <span className="meta-count">
            {noteCount}{noteCount !== totalCount ? ` / ${totalCount}` : ""} notes
          </span>
        </div>
        <span className={`status${connected ? "" : " disconnected"}`}>
          {connected ? "live" : "off"}
        </span>
        <button
          className={`icon-btn${filtersVisible ? " active" : ""}`}
          onClick={onToggleFilters}
          title={filtersVisible ? "Hide filters" : "Show filters"}
          aria-label="Toggle filters"
        >
          ⚙
        </button>
        <button className="btn" onClick={onClear}>
          Clear
        </button>
      </div>
    </div>
  );
}
