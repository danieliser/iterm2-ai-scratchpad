# iTerm2 AI Scratchpad — Specification v1

**Date:** 2026-02-22
**Status:** Ready for Implementation
**Tier:** Quick

---

## Executive Summary

A persistent sidebar panel in iTerm2's Toolbelt where long-running AI agents (Claude Code, scripts, etc.) can post notes for passive review without interrupting terminal workflow. Built on a localhost aiohttp server with file-based JSON storage, SSE for live updates, and automatic hooks for Claude Code session events. Single Python script, lightweight dependencies (aiohttp, watchdog), installable in minutes.

---

## Architecture Overview

```
┌──────────────────────────┐
│ AI Agent Sources         │
├──────────────────────────┤
│ • Claude Code (hooks)    │
│ • Any script (HTTP POST) │
│ • Any process (file API) │
└────────┬─────────────────┘
         │
         ├─ HTTP POST /api/notes
         ├─ File append ~/.config/iterm2/notes/
         │
         ▼
┌──────────────────────────────────────────┐
│ AutoLaunch Python Script                 │
│ (Full Environment, localhost:9999)       │
├──────────────────────────────────────────┤
│ aiohttp Server                           │
│ ├─ GET / (HTML UI)                       │
│ ├─ POST /api/notes (accept note)         │
│ ├─ GET /api/notes (list notes)           │
│ ├─ GET /events (SSE stream)              │
│ └─ DELETE /api/notes (clear)             │
├──────────────────────────────────────────┤
│ watchdog FSEvents Monitor                │
│ (watch ~/.config/iterm2/notes/)          │
├──────────────────────────────────────────┤
│ Session Manager                          │
│ (track active iTerm2 session UUID)       │
└────────┬─────────────────────────────────┘
         │
         ├─ Read/write JSON notes
         │
         ▼
┌──────────────────────────┐
│ File Storage             │
│ ~/.config/iterm2/notes/  │
│ └─ by-session/           │
│    └─ {uuid}.json        │
└──────────────────────────┘
         ▲
         │
         │ SSE update
         │ (from watchdog)
         │
┌──────────────────────────────────────────┐
│ iTerm2 Toolbelt WebView Panel            │
│ (WKWebView, localhost:9999)              │
├──────────────────────────────────────────┤
│ HTML/CSS/JavaScript UI                   │
│ ├─ Fetch initial notes                   │
│ ├─ Listen to SSE /events                 │
│ ├─ Render notes (reverse-chronological)  │
│ └─ Actions: copy, clear, view raw        │
└──────────────────────────────────────────┘
```

### Components

1. **Python Server** (`ai-scratchpad.py`)
   AutoLaunch Full Environment script running aiohttp on localhost:9999. Handles HTTP routes, SSE stream, file monitoring via watchdog, and session tracking.

2. **WebView Frontend** (`index.html`)
   Single-file HTML/CSS/JS UI served at `/`, fetches notes from server, subscribes to SSE updates, renders in reverse-chronological order.

3. **CLI Tool** (`scratchpad`)
   Optional shell script wrapper for posting notes from the command line or scripts.

4. **Claude Code Hook**
   PostToolUse hook that automatically posts tool execution events to the scratchpad.

5. **Storage Format**
   JSON files under `~/.config/iterm2/notes/by-session/`, keyed by session UUID.

---

## Components

### 1. Python Server (`ai-scratchpad.py`)

**Location:** `~/Library/ApplicationSupport/iTerm2/Scripts/AutoLaunch/ai-scratchpad.py`

**Runtime:** Full Environment Python (iTerm2-managed)

**Dependencies:** aiohttp, watchdog, iterm2 (already available)

**Key Responsibilities:**
- Start aiohttp server on `localhost:9999`
- Serve HTML UI at `GET /`
- Accept notes via `POST /api/notes`
- Stream updates via `GET /events` (Server-Sent Events)
- Monitor file changes with watchdog FSEvents
- Track active iTerm2 session UUID
- Set proper CORS headers on all responses

**Pseudo-code overview:**

```python
#!/usr/bin/env python3
import iterm2
import aiohttp
from aiohttp import web
import asyncio
import json
import os
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from datetime import datetime
import uuid

NOTES_DIR = Path.home() / ".config/iterm2/notes/by-session"
NOTES_DIR.mkdir(parents=True, exist_ok=True)
SSE_CLIENTS = set()

class NoteHandler(FileSystemEventHandler):
    async def on_modified(self, event):
        await asyncio.sleep(0.1)  # Debounce
        await broadcast_sse({"type": "update"})

async def handle_get_ui(request):
    """Serve HTML UI"""
    return web.Response(
        text=HTML_UI,
        content_type='text/html',
        headers=CORS_HEADERS
    )

async def handle_post_note(request):
    """Accept note POST"""
    data = await request.json()
    session_id = get_current_session_id()
    note_file = NOTES_DIR / f"{session_id}.json"

    note = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "text": data.get("text"),
        "source": data.get("source", "unknown"),
        "metadata": data.get("metadata", {})
    }

    notes = load_notes(note_file)
    notes.append(note)
    atomic_write(note_file, notes)

    await broadcast_sse({"type": "note_added"})
    return web.json_response(
        {"status": "ok", "id": note["id"]},
        headers=CORS_HEADERS
    )

async def main():
    app = web.Application()
    app.router.add_get('/', handle_get_ui)
    app.router.add_post('/api/notes', handle_post_note)
    app.router.add_get('/api/notes', handle_get_notes)
    app.router.add_get('/events', handle_sse)
    app.router.add_delete('/api/notes', handle_delete_notes)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 9999)
    await site.start()
```

**Critical Details:**
- Unset `PYTHONPATH=""` at script start to avoid conflicts with system Python
- All HTTP responses must include `Access-Control-Allow-Origin: *` for CORS
- SSE debounces file changes at 100-200ms to avoid flooding clients
- Session ID obtained via iTerm2 API or fallback to profile name
- Notes stored atomically (write to temp file, then rename) to avoid corruption

---

### 2. WebView Frontend (`index.html`)

**Location:** Served from `localhost:9999/`, embedded in Python script

**Dependencies:** None (vanilla HTML/CSS/JS)

**Key Responsibilities:**
- Render notes in reverse-chronological order
- Subscribe to SSE `/events` for live updates
- Display note metadata (timestamp, source)
- Actions: copy note text, clear all notes
- Refresh notes on load and when SSE fires

**Implementation notes:**

- Uses `fetch()` to `localhost:9999`, relies on server CORS headers
- EventSource for SSE: standard web API, fully supported by WKWebView
- Notes render in reverse-chronological order (newest at top)
- All user text escaped via `textContent` to prevent XSS
- Copy-to-clipboard via `navigator.clipboard.writeText()`
- HTML structure built with `createElement()` for safe DOM manipulation

**Sample structure (simplified):**

```html
<!DOCTYPE html>
<html>
<head>
    <title>iTerm2 AI Scratchpad</title>
    <style>
        body { font-family: -apple-system, monospace; padding: 10px; }
        .note { border: 1px solid #ddd; padding: 8px; margin-bottom: 8px; }
        .note-text { white-space: pre-wrap; word-break: break-word; }
    </style>
</head>
<body>
    <div class="header"><h2>AI Scratchpad</h2></div>
    <div id="notesContainer"></div>

    <script>
        const API = 'http://localhost:9999/api/notes';

        async function loadNotes() {
            const res = await fetch(API);
            const data = await res.json();
            renderNotes(data.notes || []);
        }

        function renderNotes(notes) {
            const container = document.getElementById('notesContainer');
            container.innerHTML = '';

            notes.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

            notes.forEach(note => {
                const noteEl = document.createElement('div');
                noteEl.className = 'note';

                const header = document.createElement('div');
                header.className = 'note-header';
                header.textContent = `${note.source} — ${formatTime(note.timestamp)}`;

                const text = document.createElement('div');
                text.className = 'note-text';
                text.textContent = note.text;

                noteEl.appendChild(header);
                noteEl.appendChild(text);
                container.appendChild(noteEl);
            });
        }

        loadNotes();

        const eventSource = new EventSource('http://localhost:9999/events');
        eventSource.onmessage = () => loadNotes();
    </script>
</body>
</html>
```

---

### 3. CLI Tool (`scratchpad`)

**Location:** `/usr/local/bin/scratchpad` (optional, user installs)

**Invocation:** `scratchpad "Note text here"` or via stdin

**Purpose:** Easy posting from shell scripts, cron jobs, or manual CLI

**Implementation:**

```bash
#!/bin/bash
API="http://localhost:9999/api/notes"

if [ $# -eq 0 ]; then
    TEXT=$(cat)
else
    TEXT="$@"
fi

if [ -z "$TEXT" ]; then
    echo "Usage: scratchpad 'note text' or echo 'text' | scratchpad"
    exit 1
fi

curl -s -X POST "$API" \
  -H "Content-Type: application/json" \
  -d "{\"text\": $(printf '%s\n' "$TEXT" | jq -Rs .), \"source\": \"cli\"}" 2>/dev/null

echo "Note posted."
```

---

### 4. Claude Code Hook Integration

**Location:** `.claude/settings.json` in project root

**Configuration:**

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "name": "post_to_scratchpad",
        "matcher": "Write|Edit",
        "enabled": true,
        "hooks": [
          {
            "type": "command",
            "command": "curl -s -X POST http://localhost:9999/api/notes -H 'Content-Type: application/json' -d '{\"text\": \"Wrote $tool_name to $file_path\", \"source\": \"claude\"}' && exit 0",
            "async": true
          }
        ]
      }
    ]
  }
}
```

**Hook Behavior:**
- Fires after every tool use (Write, Edit, etc.)
- `async: true` ensures Claude isn't blocked waiting for HTTP response
- Server receives JSON, parses, and appends to current session notes
- No feedback needed to Claude; exit 0 always

---

### 5. Storage Format

**Location:** `~/.config/iterm2/notes/by-session/`

**Filename:** `{session-uuid}.json`

**Schema:**

```json
[
  {
    "id": "uuid-v4-string",
    "timestamp": "2026-02-22T10:30:00.123456Z",
    "text": "Note content here\nCan be multiline",
    "source": "claude|cli|script|unknown",
    "metadata": {
      "tool_name": "Write",
      "file_path": "/path/to/file.js"
    }
  }
]
```

**Guarantees:**
- One file per session UUID
- Notes are append-only within session
- Atomic writes (temp + rename, never partial overwrites)
- Timestamp in UTC ISO 8601 format

---

## API Endpoints

### `GET /`

**Purpose:** Serve HTML UI

**Response:**
- `200 OK` with HTML content, `Content-Type: text/html`
- CORS headers: `Access-Control-Allow-Origin: *`

---

### `POST /api/notes`

**Purpose:** Add a note

**Request Body (JSON):**
```json
{
  "text": "Note content",
  "source": "claude|cli|script",
  "metadata": {}
}
```

**Response:**
```json
{
  "status": "ok",
  "id": "uuid-v4",
  "timestamp": "2026-02-22T10:30:00.123456Z"
}
```

**Status Code:** `201 Created` or `200 OK`

**Side Effects:**
- Appends to `{session-uuid}.json`
- Broadcasts SSE event to all connected clients

---

### `GET /api/notes`

**Purpose:** List all notes for current session

**Response:**
```json
{
  "notes": [
    {
      "id": "...",
      "timestamp": "...",
      "text": "...",
      "source": "...",
      "metadata": {}
    }
  ],
  "session_id": "current-session-uuid",
  "count": 5
}
```

**Status Code:** `200 OK`

---

### `GET /events`

**Purpose:** Server-Sent Events stream for live updates

**Response:** `text/event-stream` with CORS headers

**Message Format:**
```
data: {"type": "update"}
data: {"type": "note_added"}
```

**Connection:** Long-lived, kept alive by server; client reconnects on error

---

### `DELETE /api/notes`

**Purpose:** Clear all notes for current session

**Response:**
```json
{
  "status": "ok",
  "cleared": 5
}
```

**Status Code:** `200 OK`

**Side Effects:**
- Deletes `{session-uuid}.json` or truncates to `[]`
- Broadcasts SSE update event

---

## Installation & Setup

### Phase 1: Create AutoLaunch Script

1. **Open iTerm2 → Scripts → Manage → New Python Script**
2. **Name:** `ai-scratchpad`
3. **Environment:** Select "Full Environment"
4. **Paste the Python server code** (from Component 1)
5. **Create** — script appears in `~/Library/ApplicationSupport/iTerm2/Scripts/AutoLaunch/`

### Phase 2: Install Dependencies in Full Environment

1. Open iTerm2 terminal
2. Find the Full Environment Python path:
   ```bash
   find ~/.config/iterm2/AppSupport -name "python3" -type f 2>/dev/null | head -1
   ```
3. Install aiohttp and watchdog:
   ```bash
   /path/to/python3 -m pip install aiohttp watchdog
   ```
4. Restart iTerm2

### Phase 3: Register WebView in iTerm2

The Python script calls `iterm2.async_register_web_view_tool()` at startup. This automatically creates a Toolbelt panel. If it doesn't appear:

1. Right-click iTerm2 Toolbelt → Manage Tools
2. Look for "AI Scratchpad"
3. Enable it

### Phase 4: (Optional) Install CLI Tool

```bash
sudo curl -L https://github.com/user/iterm2-ai-scratchpad/releases/download/v1.0/scratchpad \
  -o /usr/local/bin/scratchpad && chmod +x /usr/local/bin/scratchpad
```

### Phase 5: (Optional) Configure Claude Code Hooks

1. In any Claude Code project, create or edit `.claude/settings.json`
2. Add PostToolUse hook from Component 4
3. Save

---

## Data Model

### Note Entry

```typescript
interface Note {
  id: string;                    // UUID v4
  timestamp: string;             // ISO 8601 UTC
  text: string;                  // Plain text, newlines allowed
  source: string;                // "claude", "cli", "script", etc.
  metadata: Record<string, any>; // Tool-specific data
}
```

### Session File

- **Path:** `~/.config/iterm2/notes/by-session/{session-uuid}.json`
- **Content:** Array of Note objects
- **Encoding:** UTF-8, JSON
- **Typical size:** 1-10 KB per session (older notes can be archived manually)

---

## Open Questions

1. **Session UUID fallback:** If `iterm2.Session.unique_identifier` is unavailable, use profile name or hostname+PID?
   *Decision: Try UUID first, fallback to profile.*

2. **Note rotation:** Auto-archive after N notes or wait until user clears?
   *Decision (MVP): User-initiated clear only.*

3. **Cross-session filtering:** Show only current session or all?
   *Decision: Current session only in webview.*

4. **Hook JSON schema:** Strict validation or accept arbitrary JSON?
   *Decision: Accept arbitrary, parse what we need.*

5. **Auto-clear on session end:** Delete notes when session closes?
   *Decision: No; keep until user explicitly clears.*

---

## Implementation Phases

### Phase 1: MVP (Week 1)

- Implement Python server with GET / and POST /api/notes
- Serve basic HTML UI with fetch() rendering
- Store notes as JSON, append-only per session
- Manual testing with curl
- **Exit criteria:** Notes post and persist, display in webview

### Phase 2: Live Updates (Week 1-2)

- Add watchdog FSEvents monitoring
- Implement SSE `/events` endpoint
- Update webview to subscribe to EventSource
- Debounce file changes (100-200ms)
- **Exit criteria:** Notes auto-refresh without manual refresh

### Phase 3: Session Awareness (Week 2)

- Query active iTerm2 session via API
- Store notes per session UUID
- Webview shows current session only
- **Exit criteria:** Multiple sessions have separate note streams

### Phase 4: Claude Code Hooks (Week 2-3)

- Document hook format for PostToolUse
- Create example `.claude/settings.json`
- Test with Claude Code in real project
- **Exit criteria:** Claude Code writes trigger automatic notes

### Phase 5: Polish (Week 3)

- Error logging to file
- Health check endpoint (`GET /health`)
- Delete individual notes endpoint
- CLI tool (`scratchpad` script)
- README with setup
- **Exit criteria:** User-friendly, no crashes, easy to install

---

## Acceptance Criteria

### Must Have (MVP)

- [ ] Python server starts automatically via AutoLaunch on iTerm2 startup
- [ ] Toolbelt panel registers and displays HTML UI
- [ ] POST /api/notes accepts JSON and appends to session file
- [ ] Notes persist across iTerm2 restarts
- [ ] Webview fetches and renders notes in reverse-chronological order
- [ ] GET /events streams SSE updates when notes file changes
- [ ] Webview auto-refreshes on SSE (no manual F5)
- [ ] CORS works (fetch from WKWebView to localhost succeeds)

### Should Have (Phase 2-4)

- [ ] Session awareness: notes isolated per iTerm2 session UUID
- [ ] Claude Code hooks post tool use events automatically
- [ ] CLI tool posts notes from shell
- [ ] DELETE /api/notes clears all notes
- [ ] Copy-to-clipboard action in UI
- [ ] Timestamp and source displayed per note

### Nice to Have (Later)

- [ ] Search/filter notes
- [ ] Export to markdown
- [ ] Multi-session view
- [ ] Dark mode
- [ ] Auto-archive old notes

---

## Non-Goals

- **Rich text editing:** Plain text only; no markdown rendering in MVP
- **Two-way communication:** Write-only; agents don't read from scratchpad
- **Cross-terminal support:** iTerm2 only
- **Secure storage:** Plaintext JSON in ~/.config/; local-only access assumed
- **Offline mode:** Requires server running
- **Complex categorization:** No folder tree, tags, or nesting in MVP
- **Mobile/web access:** Localhost only

---

## Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|-----------|
| AutoLaunch script crashes silently | High | Log errors to `~/iterm2_scratchpad.log`; include health endpoint |
| CORS failures block webview fetches | Medium | Set `Access-Control-Allow-Origin: *` on all responses; test directly in iTerm2 |
| watchdog misses rapid file updates | Low | Debounce at 100-200ms; accumulate before SSE emit |
| Session UUID changes unpredictably | Low | Query active session on every request; cache in module var |
| Full Environment bloats disk | Low | ~100 MB acceptable; document in README |
| JSON file corruption on crash | Medium | Atomic writes (temp + rename); never truncate mid-write |
| SSE memory leak with many clients | Low | Timeout idle connections after 5 minutes |
| Claude hooks block agent if server down | Medium | Use `async: true`; set 30s timeout; document troubleshooting |

---

## Dependencies

### Required

- **iTerm2** v3.4+ (Python API v0.26+)
- **macOS** 10.14+
- **aiohttp** (pip install in Full Environment)
- **watchdog** (pip install in Full Environment)
- **iterm2** module (built-in with Full Environment)

### Optional

- **curl** — for CLI and hooks (pre-installed on macOS)
- **jq** — for hook JSON formatting (optional)

### Not Needed

- Homebrew, Node.js, Docker, or external APIs

---

## Test Strategy

### Unit Tests

1. Note JSON schema validation
2. Time formatting (ISO 8601 → human-readable)
3. CORS header injection on all responses

### Integration Tests

1. HTTP POST → JSON file write
2. File change → SSE broadcast
3. Session UUID resolution
4. Hook execution trigger

### Manual Tests in iTerm2

1. Webview appears in Toolbelt
2. Notes load on page open (no CORS errors)
3. Post via curl, see instant update in webview
4. Open 2 tabs, verify notes isolated per session
5. Run Claude Code with hook enabled, verify note posted
6. Run `scratchpad "test"`, verify in webview
7. Restart iTerm2, verify notes persist
8. Clear notes, verify removed

### Load Test

1. 100 notes render without lag
2. 10 posts/second for 10s, SSE keeps up
3. 10 KB note stores and renders correctly

---

## Version History

- **v1** (2026-02-22) — Initial spec, all components defined, architecture locked

