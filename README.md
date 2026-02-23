# iTerm2 AI Scratchpad

A persistent sidebar panel in iTerm2's Toolbelt where long-running AI agents (Claude Code, scripts, shell commands) can post notes for passive review without interrupting terminal workflow. Built on a localhost aiohttp server with file-based JSON storage, SSE for live updates, and automatic hooks for Claude Code session events.

## Architecture

```
AI Agents / CLI / Claude Code hooks
         │
         │ HTTP POST /api/notes
         ▼
┌─────────────────────────────────────┐
│ aiohttp Server (localhost:9999)     │
│ ├─ POST /api/notes  (accept note)   │
│ ├─ GET  /api/notes  (list notes)    │
│ ├─ GET  /events     (SSE stream)    │
│ ├─ DELETE /api/notes (clear)        │
│ ├─ GET  /health     (status)        │
│ └─ GET  /           (HTML UI)       │
├─────────────────────────────────────┤
│ watchdog FSEvents Monitor           │
│ (watch ~/.config/iterm2-scratchpad) │
└─────────────────────────────────────┘
         │ SSE events
         ▼
┌─────────────────────────────────────┐
│ iTerm2 Toolbelt WebView Panel       │
│ (WKWebView, localhost:9999)         │
│ ├─ Fetch initial notes              │
│ ├─ Listen to SSE /events            │
│ └─ Render reverse-chronological     │
└─────────────────────────────────────┘
         │
         ▼
  ~/.config/iterm2-scratchpad/
  └─ notes/by-session/{uuid}.json
```

## Prerequisites

- iTerm2 v3.4 or later (macOS)
- Python 3.9+
- pip (comes with Python)

## Installation

### 1. Create the AutoLaunch script

1. Open iTerm2 → **Scripts → Manage → New Python Script**
2. Name it `ai-scratchpad`
3. Select **Full Environment** (gives you an isolated pip)
4. When the file opens, replace its contents with `src/ai_scratchpad.py` from this repo

The script is saved to:
```
~/Library/Application Support/iTerm2/Scripts/AutoLaunch/ai-scratchpad/ai-scratchpad.py
```

### 2. Install dependencies in the Full Environment

Find the Full Environment Python binary:
```bash
find ~/.config/iterm2/AppSupport -name "python3" -type f 2>/dev/null | head -1
```

Install dependencies:
```bash
/path/to/iterm2_env_python3 -m pip install aiohttp watchdog
```

### 3. Restart iTerm2

The script runs automatically on startup. The Toolbelt panel registers itself — if it doesn't appear:

1. Right-click the iTerm2 Toolbelt → **Manage Tools**
2. Enable **AI Scratchpad**

### 4. Install the CLI tool (optional)

```bash
# Link into your PATH
ln -s "$(pwd)/bin/scratchpad" /usr/local/bin/scratchpad
# or copy it
cp bin/scratchpad /usr/local/bin/scratchpad
```

## Usage

### Standalone / development mode

Run without iTerm2 (uses "default" session, no toolbelt registration):

```bash
python3 src/ai_scratchpad.py
```

### CLI tool

```bash
# Post a note as an argument
scratchpad "Build finished successfully"

# Post via stdin
echo "Deploy complete" | scratchpad

# Custom source label
scratchpad -s myapp "Database migration done"

# Override server URL
SCRATCHPAD_URL=http://localhost:9999 scratchpad "hello"
```

### HTTP API

All endpoints accept and return JSON. CORS is open (`*`).

```bash
# Post a note
curl -s -X POST http://localhost:9999/api/notes \
  -H 'Content-Type: application/json' \
  -d '{"text": "Hello", "source": "curl"}'

# List notes
curl -s http://localhost:9999/api/notes | python3 -m json.tool

# List notes for a specific session
curl -s "http://localhost:9999/api/notes?session_id=abc-123"

# Clear all notes
curl -s -X DELETE http://localhost:9999/api/notes

# Health check
curl -s http://localhost:9999/health | python3 -m json.tool

# Current session
curl -s http://localhost:9999/api/session
```

### Claude Code hook

Add this to `.claude/settings.json` in any project to automatically post notes when Claude writes or edits files:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "curl -s -X POST http://localhost:9999/api/notes -H 'Content-Type: application/json' -d '{\"text\": \"Modified file\", \"source\": \"claude\"}'",
            "async": true
          }
        ]
      }
    ]
  }
}
```

`"async": true` ensures Claude isn't blocked waiting for the HTTP response.

You can also use the `scratchpad` CLI instead of a raw curl command:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "scratchpad -s claude \"Claude Code completed a tool use\"",
            "async": true
          }
        ]
      }
    ]
  }
}
```

## Multi-Terminal Behavior

The scratchpad server runs as a **single process** on `localhost:9999`. Multiple iTerm2 windows, tabs, and split panes all connect to the same server.

**Session isolation:** In iTerm2 AutoLaunch mode, each terminal session gets its own note stream identified by the session UUID. When you switch tabs, the toolbelt panel automatically shows notes for the active session. The server tracks the active session via iTerm2's `LayoutChangeMonitor`.

**Standalone mode:** Without iTerm2 integration (e.g., during development), all terminals share a single `"default"` session. Notes from any source appear in one stream.

**What this means in practice:**
- You can have Claude Code running in Tab 1 and a build script in Tab 2 — each gets its own notes
- The toolbelt sidebar updates live when you switch between tabs
- The CLI tool (`scratchpad`) and HTTP API always post to whatever session is currently active
- To post to a specific session: `curl "http://localhost:9999/api/notes?session_id=<uuid>"`
- To read another session's notes: `curl "http://localhost:9999/api/notes?session_id=<uuid>"`

**Multiple iTerm2 windows:** All windows share the same server. The active session is whichever session most recently gained focus across all windows.

## Rich Note Formatting

Notes support basic markdown-style formatting:

- `**bold**` → **bold**
- `*italic*` → *italic*
- `` `inline code` `` → inline code
- Triple backtick code blocks
- `### headers`
- `- bullet lists`
- `---` horizontal rules
- Double newlines for paragraphs

All content is HTML-escaped before formatting is applied — no XSS risk.

## Quick Setup (Copy-Paste Later)

If you want to set this up later after a restart, here's the condensed version:

```bash
# 1. Kill any stale server
lsof -i :9999 -P -n | awk 'NR>1{print $2}' | xargs kill 2>/dev/null

# 2. Start standalone (no iTerm2 integration)
cd ~/Projects/iterm2-ai-scratchpad
python3 src/ai_scratchpad.py &

# 3. Open the UI
open http://localhost:9999/

# 4. Post a test note
bin/scratchpad "Server is running"

# 5. Link CLI to PATH (one-time)
ln -sf "$(pwd)/bin/scratchpad" ~/dotfiles/bin/scratchpad
```

### Full iTerm2 Setup (one-time)

```bash
# 1. Enable Python API: iTerm2 → Settings → General → Magic → Enable Python API

# 2. Create AutoLaunch script directory
mkdir -p ~/Library/Application\ Support/iTerm2/Scripts/AutoLaunch

# 3. Copy the server script
cp src/ai_scratchpad.py \
   ~/Library/Application\ Support/iTerm2/Scripts/AutoLaunch/ai_scratchpad.py

# 4. Install deps in system Python (or iTerm2's Full Environment Python)
pip3 install aiohttp watchdog

# 5. Restart iTerm2 — script auto-launches

# 6. Show toolbelt: View → Show Toolbelt
# 7. Enable panel: right-click toolbelt → check "AI Scratchpad"
```

### Hook Setup for Claude Code (one-time)

Add to `~/.claude/settings.json` for all projects:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "scratchpad -s claude 'Modified a file'",
            "async": true
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "scratchpad -s claude 'Turn complete'",
            "async": true
          }
        ]
      }
    ]
  }
}
```

## Data model

Each note is a JSON object:

```json
{
  "id": "uuid-v4",
  "timestamp": "2026-02-22T10:30:00.123456+00:00",
  "text": "Note content",
  "source": "claude",
  "metadata": {}
}
```

Notes are stored per iTerm2 session UUID at:
```
~/.config/iterm2-scratchpad/notes/by-session/{session-uuid}.json
```

## Troubleshooting

**Server not running / CLI gets "server unavailable"**
```bash
# Check if it's running
curl -s http://localhost:9999/health

# Start manually
python3 src/ai_scratchpad.py

# Check the log
tail -f ~/iterm2_scratchpad.log
```

**Toolbelt panel not appearing**
1. Confirm the AutoLaunch script is in the correct location
2. Check `~/iterm2_scratchpad.log` for startup errors
3. Right-click Toolbelt → Manage Tools → enable AI Scratchpad
4. Restart iTerm2

**CORS errors in the webview**
The server sets `Access-Control-Allow-Origin: *` on all responses. If you see CORS errors, confirm the server is running on port 9999 and the webview URL matches.

**watchdog not installed**
The server runs without watchdog — you just won't get SSE updates from direct file writes. Install it:
```bash
/path/to/iterm2_env_python3 -m pip install watchdog
```
Or for standalone mode:
```bash
pip3 install watchdog
```

**Notes not scoped to session (all sessions share notes)**
This happens when running in standalone mode (no iTerm2 API). Session awareness requires the script to run as an iTerm2 AutoLaunch Full Environment script.
