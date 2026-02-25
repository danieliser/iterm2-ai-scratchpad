# AI Scratchpad

iTerm2 toolbelt sidebar for AI agent output. Posts notes via MCP, renders in a React WebView.

## Architecture

- `src/ai_scratchpad.py` — aiohttp server (port 9999), SSE broadcast, iTerm2 toolbelt registration, todo board API
- `src/mcp_server.py` — FastMCP stdio server exposing `post_note` tool
- `ui/` — React 19 + Vite frontend, built to single file via vite-plugin-singlefile
- AutoLaunch symlink at `~/.config/iterm2/AppSupport/Scripts/AutoLaunch/ai_scratchpad.py`

## AI Scratchpad MCP

The `ai-scratchpad` MCP server is registered at user scope. It provides a `post_note` tool.

### When to use it

- **Status updates** — post progress on multi-step tasks so the user can glance at the sidebar
- **Build/deploy results** — badges and progress bars for pipeline status
- **Data summaries** — key-value pairs, metrics, charts for quick reference
- **Architecture notes** — mermaid diagrams, file trees when explaining structure
- **Runnable commands** — give the user clickable run buttons for common operations
- **Task tracking** — todo checklists for complex work

### When NOT to use it

- Don't post every minor action — it's a dashboard, not a log stream
- Don't duplicate what's already visible in the terminal output
- If the scratchpad server isn't running, the tool returns a graceful error — just continue without it

### Source labels

Use the `source` parameter to categorize notes for filtering:
- `"agent"` — general agent output (default)
- `"ci"` — build/deploy/pipeline status
- `"monitor"` — health checks, metrics, port status
- `"debug"` — debugging sessions, error analysis

### Widget syntax

Two forms: inline `[type:arg1:arg2]` and block `[type]content[/type]`.

**Inline widgets:**
- `[status:success:Label]` — badge (success|warning|error|info)
- `[progress:75:Building...]` — progress bar 0-100
- `[metric:42ms:Latency:down]` — big number with trend (up|down|flat)
- `[timer:5m:Label]` — countdown (5m, 1h30m, 90s)
- `[deadline:2026-03-01T00:00:00:Label]` — date countdown
- `[chart:10,45,30,80:Label]` — sparkline
- `[link:Title:https://url]` — clickable link card
- `[ports:3000,5432]` — live port status

**Block widgets:**
- `[kv]Key=Value\nKey2=Value2[/kv]` — key-value pairs
- `[log:info]lines[/log]` — log block (error|warn|info|debug)
- `[diff]-removed\n+added[/diff]` — diff view
- `[todo]Item\n[x]Done item[/todo]` — interactive checklist
- `[details:Title]content[/details]` — collapsible
- `[clip:Label]text[/clip]` — click-to-copy
- `[tree]src/\n  src/main.ts[/tree]` — file tree
- `[mermaid]graph LR\n  A-->B[/mermaid]` — diagram
- `[run:Label]shell command[/run]` — executable command

Widget syntax inside backticks is protected from parsing.

## Development

```bash
# Frontend dev
cd ui && pnpm dev          # Vite dev server with proxy to :9999

# Build (single-file HTML)
cd ui && pnpm build        # outputs ui/dist/index.html

# Run server standalone (without iTerm2)
python3 src/ai_scratchpad.py --standalone

# MCP server (registered globally via claude mcp add)
# Uses: uv run --with mcp[cli] python src/mcp_server.py
```

## Notes

- iTerm2 autolaunch uses Python 3.14 from `~/.config/iterm2/AppSupport/iterm2env/` — watchdog doesn't build on 3.14 (graceful fallback)
- Server serves React UI from `ui/dist/index.html` if it exists, falls back to embedded HTML
- The embedded `build_html()` fallback is legacy — prefer the React build
