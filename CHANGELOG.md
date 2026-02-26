# Changelog

## [0.3.0] - 2026-02-25

### Added

- **Polling fallback** — when watchdog is unavailable (iTerm2's Python 3.14), notes and todo directories are polled every 2 seconds for live updates.
- **Note lifecycle** — dismiss notes to collapsed single-line ghosts, restore with one click, toggle dismissed visibility. Persisted to prefs.
- **Animated transitions** — spring-based layout animations for note cards, filter bar, and todo panels via Motion (framer-motion).
- **Clickable source labels** — click a note's source to jump to that session's tab in iTerm2.
- **Tab + Panel scope** — three-way scope toggle (All / Tab / Panel) for viewing notes across all sessions, current tab's panes, or just the active panel.
- **Theme system** — two independent axes: style (Cockpit / Refined) and scheme (Dark / Light / Auto). Cockpit is amber/mono with CRT scanlines; Refined is Catppuccin with softer radius.
- **Status bar** — shows cwd, git branch, dirty state, ahead/behind counts, and foreground process for active session.
- **Multi-panel layout** — when a tab has splits in different directories, shows compact stacked rows with clickable jump-to-panel buttons.
- **Filter bar toggle** — collapsible filter row with search, source dropdown, and sort. Auto-shows when multiple sources present.
- **Run widget "Done" feedback** — commands that succeed with no output now show "✓ Done" instead of blank.

### Changed

- Header redesigned — title bar with theme/browser controls, compact toolbar below.
- Filter bar uses `<select>` dropdowns instead of pill button rows.
- Note actions (pin, dismiss, copy) are hover-to-show with opacity transitions.
- Copy button moved inline to note meta row.
- IBM Plex Sans replaces DM Sans as default UI font in cockpit style.

## [0.2.1] - 2026-02-25

### Fixed

- **Link widget clicks now work in toolbelt** — routes through server-side `open` command instead of relying on WKWebView navigation, which was blocked in the sandboxed WebView.

### Added

- **Editor deeplinks** — `[link:Open in Cursor:cursor://file/path/to/file]` opens files directly in Cursor (or VS Code, etc). Any URL scheme supported via macOS `open`.
- Documented deeplink syntax in MCP tool docstring and project CLAUDE.md.

## [0.2.0] - 2026-02-25

### Added

- **MCP usage guidance** — the MCP server now includes full instructions for when/how to use the scratchpad, source labels, and the update workflow. Claude picks this up automatically — no CLAUDE.md configuration needed for end users.

### Changed

- Moved usage docs from project CLAUDE.md into MCP server `instructions` field for zero-config onboarding.

## [0.1.0] - 2026-02-25

Initial release of AI Scratchpad for iTerm2.

### Features

- **iTerm2 Toolbelt integration** — registers as a WebView panel in iTerm2's sidebar
- **MCP server** — `post_note` and `update_note` tools for Claude Code and other AI agents
- **Rich widget system** — status badges, progress bars, metrics, sparkline charts, timers, deadlines, diffs, key-value pairs, log blocks, file trees, mermaid diagrams, click-to-copy, executable run commands, interactive todo checklists
- **Markdown rendering** — full markdown support in notes with code highlighting
- **Dual-theme system** — Cockpit (amber/mono, CRT scanlines) and Refined (Catppuccin) styles, each with dark and light schemes
- **Session awareness** — tracks active iTerm2 session, routes notes to correct pane
- **Scope filtering** — All / Tab / Panel scope toggle to view notes across sessions or focused on a single pane
- **Session status bar** — shows cwd, git branch, dirty/ahead/behind counts, and foreground process for active session (Panel/Tab scope)
- **Multi-panel tab view** — when tab has panes in different directories, shows compact stacked rows with clickable jump-to-panel links
- **Todo board** — aggregates Claude Code todo lists and team tasks with progress bars
- **Note management** — pin, dismiss/restore, filter by source, text search, sort by time or source
- **SSE live updates** — real-time streaming of new notes, session changes, and todo updates
- **File watcher** — watchdog-based monitoring for external note and todo file changes
- **One-line installer** — `curl -fsSL ... | bash` with tarball download and MCP auto-registration
- **Standalone mode** — runs without iTerm2 for browser-based use
- **Dev mode** — Vite HMR with proxy to backend for frontend development
