# Plan: iTerm2 AI Scratchpad

**Date:** 2026-02-22
**Tier:** Quick
**Status:** Approved

## Executive Summary

A persistent sidebar panel in iTerm2's Toolbelt where long-running AI agents can post notes for passive review. Built on a localhost aiohttp server with file-based JSON storage, SSE for live updates, and automatic Claude Code hooks. Four components: Python server (~80 lines), WebView frontend (~60 lines), CLI tool (~15 lines), Claude Code hook config (~10 lines). Installable in minutes, no external dependencies beyond pip packages in iTerm2's isolated Python environment.

## Specification

See [spec-v1.md](spec-v1.md) for the full specification, including:

- **Architecture:** AutoLaunch Full Environment Python → aiohttp server (localhost:9999) → JSON storage → WKWebView toolbelt panel with SSE live updates
- **Components:** Python server, WebView frontend, CLI tool, Claude Code PostToolUse hook, JSON storage format
- **API:** 5 endpoints (GET /, POST /api/notes, GET /api/notes, GET /events SSE, DELETE /api/notes)
- **Data model:** Note entries with id, timestamp, text, source, metadata — stored per session UUID
- **Installation:** Create AutoLaunch script → pip install aiohttp/watchdog → enable toolbelt panel

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Platform scope | iTerm2 only | Simpler build, native toolbelt integration |
| Update mechanism | SSE (not polling/WebSocket) | WKWebView supports EventSource; WebSockets broken in WKWebView |
| File monitoring | watchdog (FSEvents) | <50ms latency, native macOS support, no FD limits |
| Storage format | JSON per session UUID | Simple, human-readable, atomic writes prevent corruption |
| Python environment | Full Environment (iTerm2-managed) | Isolated pip, no system Python dependency |
| Agent integration | Generic HTTP + Claude Code hooks | Any process can POST; Claude Code gets automatic hooks |
| Session scoping | Per iTerm2 session UUID | Profile-based is too coarse (multiple sessions share profiles) |

## Implementation Phases

### Phase 1: MVP
- Python server with GET / and POST /api/notes
- Basic HTML UI with fetch() rendering
- JSON storage, append-only
- Manual testing with curl
- **Exit:** Notes post, persist, display in webview

### Phase 2: Live Updates
- watchdog FSEvents monitoring
- SSE /events endpoint
- WebView EventSource subscription
- Debounce at 100-200ms
- **Exit:** Notes auto-refresh without manual reload

### Phase 3: Session Awareness
- Query active iTerm2 session via API
- Notes stored per session UUID
- WebView shows current session only
- **Exit:** Multiple sessions have separate note streams

### Phase 4: Claude Code Hooks
- PostToolUse hook config for .claude/settings.json
- Async HTTP POST to scratchpad server
- Test with real Claude Code sessions
- **Exit:** Claude Code writes trigger automatic notes

### Phase 5: Polish
- Error logging, health endpoint
- CLI tool (scratchpad script)
- Delete individual notes
- README
- **Exit:** User-friendly, stable, easy to install

## Risk Register

| Risk | Severity | Mitigation | Owner |
|------|----------|-----------|-------|
| AutoLaunch crashes silently | High | Log to ~/iterm2_scratchpad.log; health endpoint | Dev |
| CORS blocks webview fetches | Medium | Access-Control-Allow-Origin: * on all responses | Dev |
| JSON corruption on crash | Medium | Atomic writes (temp + rename) | Dev |
| Claude hooks block if server down | Medium | async: true; 30s timeout | Dev |
| watchdog misses rapid updates | Low | Debounce at 100-200ms | Dev |
| Full Environment disk usage | Low | ~100MB acceptable; document | Docs |

## Follow-up Items

- Dark mode support for the webview UI
- Search/filter notes
- Export to markdown
- Multi-session view (show all sessions at once)
- Auto-archive old notes after N entries
- Consider packaging as a proper iTerm2 plugin for distribution

## Supporting Documents

- [intake.md](intake.md) — Project scoping and constraints
- [research.md](research.md) — Technical research on iTerm2 APIs, WebView capabilities, file monitoring
- [spec-v1.md](spec-v1.md) — Full specification with API definitions, data model, test strategy
