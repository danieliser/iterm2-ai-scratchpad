# AI Scratchpad for iTerm2

A real-time sidebar for iTerm2 where your AI agents post notes, status updates, and rich widgets — without interrupting your terminal.

Works with Claude Code out of the box via MCP. Also supports any tool that can make HTTP requests.

## Install

```bash
git clone https://github.com/danieliser/iterm2-ai-scratchpad.git
cd iterm2-ai-scratchpad
./install.sh
```

The installer:
- Detects your iTerm2 Python environment
- Installs the `aiohttp` dependency
- Registers the AutoLaunch script (starts automatically with iTerm2)
- Registers the MCP server with Claude Code (if installed)
- Links the optional `scratchpad` CLI tool

After install, restart iTerm2, then **View → Show Toolbelt** and enable **AI Scratchpad**.

### Requirements

- macOS with [iTerm2](https://iterm2.com) 3.4+
- iTerm2 Python API enabled (Settings → General → Magic → Enable Python API)
- [uv](https://docs.astral.sh/uv/) for the MCP server (`brew install uv`)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) for agent integration

### Manual MCP setup

If you installed Claude Code after running the installer, register the MCP server:

```bash
claude mcp add ai-scratchpad -s user \
  -- uv run --with "mcp[cli]" python \
  "$(pwd)/src/mcp_server.py"
```

## What it does

Once running, any Claude Code session can post to the sidebar:

- Status badges, progress bars, sparkline charts
- Timers, countdowns, checklists
- Diff views, file trees, mermaid diagrams
- Code blocks, key-value tables, log output
- Click-to-copy snippets, executable commands

Notes are scoped per terminal tab — switch tabs to see that tab's agent output. Use the **All** / **Active** toggle to view everything or just the focused session.

Click any agent's source label to jump to its iTerm2 tab. Open `http://localhost:9999` in a browser for a full-window view.

### Themes

Two independent controls in the title bar:
- **Scheme** (◎ auto / ☾ dark / ☀ light) — follows system preference by default
- **Style** (◐ Cockpit HUD / ◑ Refined Terminal) — different fonts, border radius, visual effects

## CLI tool

```bash
scratchpad "Build finished"                  # post a note
echo "Deploy complete" | scratchpad          # via stdin
scratchpad -s ci "Pipeline green"            # custom source label
```

## HTTP API

Any tool can post notes:

```bash
curl -X POST http://localhost:9999/api/notes \
  -H 'Content-Type: application/json' \
  -d '{"text": "Hello from curl", "source": "my-script"}'
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Server not running | `curl http://localhost:9999/health` — if no response, restart iTerm2 or run `python3 src/launch.py` manually |
| Panel not in Toolbelt | View → Show Toolbelt, right-click → enable "AI Scratchpad" |
| MCP tools missing | `claude mcp list` — if not listed, re-run `claude mcp add` (see Manual MCP setup above) |
| Logs | `tail -f ~/iterm2_scratchpad.log` |

## Development

```bash
cd ui && pnpm install && pnpm dev    # React dev server with hot-reload
python3 src/launch.py                # standalone server (no iTerm2 required)
cd ui && pnpm build                  # rebuild the UI
```
