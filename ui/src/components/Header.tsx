import { useState, useEffect } from "react";
import type { NoteScope } from "../hooks/useNotes";
import type { Style, Scheme } from "../hooks/useTheme";
import { openInBrowser, isInToolbelt } from "../lib/api";

interface Props {
  connected: boolean;
  onClear: () => void;
  scope: NoteScope;
  onScopeChange: (scope: NoteScope) => void;
  sessionId: string;
  noteCount: number;
  totalCount: number;
  style: Style;
  scheme: Scheme;
  onCycleStyle: () => void;
  onCycleScheme: () => void;
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
  style,
  scheme,
  onCycleStyle,
  onCycleScheme,
  filtersVisible,
  onToggleFilters,
}: Props) {
  const [inToolbelt, setInToolbelt] = useState(true);
  useEffect(() => { setInToolbelt(isInToolbelt()); }, []);
  const sessionLabel = sessionId && sessionId !== "default"
    ? sessionId.slice(0, 7)
    : "default";

  return (
    <div className="header-group">
      {/* Title bar */}
      <div className="title-bar">
        <span className="title-text">AI Scratchpad</span>
        <div className="title-actions">
          {inToolbelt ? (
            <button
              className="icon-btn"
              onClick={openInBrowser}
              title="Open in browser"
              aria-label="Open in browser"
            >
              ↗
            </button>
          ) : (
            <button
              className="icon-btn"
              onClick={() => {
                // Use osascript via exec endpoint to activate iTerm2
                fetch("/api/exec", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ command: "open -a iTerm", timeout: 5 }),
                });
              }}
              title="Focus iTerm2"
              aria-label="Focus iTerm2"
            >
              ⌘
            </button>
          )}
          <button
            className="icon-btn"
            onClick={onCycleScheme}
            title={`Scheme: ${scheme}`}
            aria-label="Cycle color scheme"
          >
            {scheme === "auto" ? "◎" : scheme === "light" ? "☀" : "☾"}
          </button>
          <button
            className="icon-btn"
            onClick={onCycleStyle}
            title={`Style: ${style}`}
            aria-label="Cycle style"
          >
            {style === "cockpit" ? "◐" : "◑"}
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
