# iTerm2 AI Scratchpad

A real-time sidebar panel for iTerm2 where AI agents post notes, status updates, and rich widgets without interrupting your terminal. Agents connect via MCP; the UI runs in iTerm2's Toolbelt or any browser.

## Quick Setup

### Prerequisites

- **iTerm2** 3.4+ (macOS) with Python API enabled
- **uv** (`brew install uv`) — runs the MCP server
- **pnpm** (`brew install pnpm`) — builds the React UI
- **Claude Code** (for MCP agent integration)

### 1. Clone and build the UI

```bash
git clone https://github.com/danieliser/iterm2-ai-scratchpad.git
cd iterm2-ai-scratchpad
cd ui && pnpm install && pnpm build && cd ..
```

### 2. Register with iTerm2

Enable the Python API: **iTerm2 → Settings → General → Magic → Enable Python API**

Install `aiohttp` in iTerm2's Python environment:

```bash
~/.config/iterm2/AppSupport/iterm2env/versions/*/bin/python3 -m pip install aiohttp
```

Symlink the launcher into AutoLaunch:

```bash
mkdir -p ~/.config/iterm2/AppSupport/Scripts/AutoLaunch
ln -sf "$(pwd)/src/launch.py" \
  ~/.config/iterm2/AppSupport/Scripts/AutoLaunch/ai_scratchpad.py
```

Restart iTerm2. The server starts automatically on port 9999.

Show the panel: **View → Show Toolbelt**, then right-click the Toolbelt and enable **AI Scratchpad**.

### 3. Register the MCP server (for Claude Code agents)

```bash
claude mcp add ai-scratchpad \
  -s user \
  -- uv run --with "mcp[cli]" python \
  "$(pwd)/src/mcp_server.py"
```

This gives all Claude Code sessions access to `post_note` and `update_note` tools. Agents can post markdown, status badges, progress bars, timers, checklists, and more.

### 4. Verify

```bash
# Check the server is running
curl -s http://localhost:9999/health | python3 -m json.tool

# Post a test note
curl -s -X POST http://localhost:9999/api/notes \
  -H 'Content-Type: application/json' \
  -d '{"text": "[status:success:Setup Complete]\nAI Scratchpad is working.", "source": "test"}'
```

You should see the note appear in the Toolbelt sidebar.

## How It Works

```
Claude Code / AI Agents
         │
         │ MCP (post_note / update_note)
         ▼
┌─────────────────────────────────────┐
│ MCP Server (src/mcp_server.py)      │
│ stdio ↔ Claude Code session         │
└────────────┬────────────────────────┘
             │ HTTP POST /api/notes
             ▼
┌─────────────────────────────────────┐
│ aiohttp Server (localhost:9999)     │
│ ├─ Notes API (CRUD + SSE)          │
│ ├─ Session tracking (FocusMonitor) │
│ ├─ Todo/task board API             │
│ ├─ Preferences API                 │
│ └─ React UI (single-file build)    │
└────────────┬────────────────────────┘
             │ SSE live updates
             ▼
┌─────────────────────────────────────┐
│ iTerm2 Toolbelt / Browser           │
│ React 19 + Motion animations        │
│ ├─ Note cards with rich widgets     │
│ ├─ Task board (Claude Code todos)   │
│ ├─ Source filters + search          │
│ ├─ Clickable sources → tab switch   │
│ └─ Theme: cockpit/refined × dark/light
└─────────────────────────────────────┘
```

Notes are stored per session at `~/.config/iterm2-scratchpad/notes/by-session/{uuid}.json`.

## Features

- **Rich widgets** — status badges, progress bars, sparkline charts, timers, checklists, diff views, mermaid diagrams, file trees, click-to-copy, executable commands
- **Session-scoped notes** — each iTerm2 tab gets its own note stream; switch tabs to see that tab's agent output
- **All/Active view** — toggle between all sessions or just the focused tab
- **Task board** — live view of Claude Code todo lists and team tasks
- **Clickable source labels** — click an agent's name to jump to its iTerm2 tab
- **Theme system** — two independent axes: style (Cockpit HUD / Refined Terminal) and scheme (dark / light / auto). Auto follows system preference.
- **Open in browser** — full UI at `http://localhost:9999` with "Focus iTerm2" button to jump back
- **Filters** — search, source filter, sort by time or source. Auto-shows when 2+ sources exist.
- **Pin and dismiss** — pin important notes to top, dismiss resolved ones

## CLI Tool

```bash
# Link to PATH (one-time)
ln -sf "$(pwd)/bin/scratchpad" /usr/local/bin/scratchpad

# Usage
scratchpad "Build finished"                    # text as argument
echo "Deploy complete" | scratchpad            # via stdin
scratchpad -s ci "Pipeline passed"             # custom source label
```

## Development

```bash
# Frontend dev (hot-reload)
cd ui && pnpm dev

# Run server standalone (no iTerm2 required)
python3 src/launch.py

# Build UI
cd ui && pnpm build

# MCP server (for testing outside Claude Code)
uv run --with "mcp[cli]" python src/mcp_server.py
```

## Troubleshooting

**Server not running**
```bash
curl -s http://localhost:9999/health    # check status
tail -f ~/iterm2_scratchpad.log         # check logs
python3 src/launch.py                   # start manually
```

**Toolbelt panel not showing**
1. iTerm2 → Settings → General → Magic → confirm Python API is enabled
2. View → Show Toolbelt
3. Right-click Toolbelt → enable "AI Scratchpad"
4. Check `~/iterm2_scratchpad.log` for errors
5. Restart iTerm2

**MCP tools not available in Claude Code**
```bash
claude mcp list    # verify ai-scratchpad is registered
```
If missing, re-run the `claude mcp add` command from step 3.

**Notes not scoped to session**
Session awareness requires the iTerm2 AutoLaunch integration. In standalone mode (`python3 src/launch.py`), all notes share a single "default" session.
