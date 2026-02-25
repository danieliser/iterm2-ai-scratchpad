#!/usr/bin/env bash
# install.sh — Set up AI Scratchpad for iTerm2 + Claude Code
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/danieliser/iterm2-ai-scratchpad/master/install.sh | bash
#   # or after cloning:
#   ./install.sh

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}▸${NC} $*"; }
ok()    { echo -e "${GREEN}✓${NC} $*"; }
warn()  { echo -e "${YELLOW}!${NC} $*"; }
fail()  { echo -e "${RED}✗${NC} $*"; exit 1; }

echo -e "\n${BOLD}AI Scratchpad — iTerm2 + Claude Code installer${NC}\n"

# ── Locate or clone the repo ────────────────────────────────────────

REPO_DIR=""

# If run locally (not piped), check if we're inside the repo
if [[ -n "${BASH_SOURCE[0]:-}" ]] && [[ "${BASH_SOURCE[0]}" != "bash" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
    if [[ -f "$SCRIPT_DIR/src/launch.py" ]]; then
        REPO_DIR="$SCRIPT_DIR"
        info "Using local repo at $REPO_DIR"
    fi
fi

# Otherwise, clone or update
if [[ -z "$REPO_DIR" ]]; then
    REPO_DIR="$HOME/.local/share/ai-scratchpad"
    if [[ -d "$REPO_DIR/.git" ]]; then
        info "Updating existing install at $REPO_DIR"
        git -C "$REPO_DIR" pull --quiet
    else
        info "Cloning to $REPO_DIR"
        git clone --quiet https://github.com/danieliser/iterm2-ai-scratchpad.git "$REPO_DIR"
    fi
fi

# ── Check iTerm2 ────────────────────────────────────────────────────

if [[ ! -d "/Applications/iTerm.app" ]]; then
    fail "iTerm2 not found. Install it from https://iterm2.com"
fi
ok "iTerm2 found"

# ── Find iTerm2's Python ────────────────────────────────────────────

ITERM_PYTHON=""
for py in ~/.config/iterm2/AppSupport/iterm2env/versions/*/bin/python3; do
    if [[ -x "$py" ]]; then
        ITERM_PYTHON="$py"
        break
    fi
done

if [[ -z "$ITERM_PYTHON" ]]; then
    warn "iTerm2 Python environment not found."
    echo "  Enable the Python API: iTerm2 → Settings → General → Magic → Enable Python API"
    echo "  Then restart iTerm2 and re-run this installer."
    fail "Cannot continue without iTerm2 Python environment"
fi
ok "iTerm2 Python: $ITERM_PYTHON"

# ── Install aiohttp ─────────────────────────────────────────────────

if "$ITERM_PYTHON" -c "import aiohttp" 2>/dev/null; then
    ok "aiohttp already installed"
else
    info "Installing aiohttp in iTerm2 Python environment..."
    "$ITERM_PYTHON" -m pip install --quiet aiohttp
    ok "aiohttp installed"
fi

# ── Create AutoLaunch symlink ───────────────────────────────────────

AUTOLAUNCH_DIR="$HOME/.config/iterm2/AppSupport/Scripts/AutoLaunch"
SYMLINK_PATH="$AUTOLAUNCH_DIR/ai_scratchpad.py"
LAUNCH_SCRIPT="$REPO_DIR/src/launch.py"

mkdir -p "$AUTOLAUNCH_DIR"

if [[ -L "$SYMLINK_PATH" ]] && [[ "$(readlink "$SYMLINK_PATH")" == "$LAUNCH_SCRIPT" ]]; then
    ok "AutoLaunch symlink already correct"
elif [[ -e "$SYMLINK_PATH" ]]; then
    warn "Replacing existing AutoLaunch entry"
    ln -sf "$LAUNCH_SCRIPT" "$SYMLINK_PATH"
    ok "AutoLaunch symlink updated"
else
    ln -sf "$LAUNCH_SCRIPT" "$SYMLINK_PATH"
    ok "AutoLaunch symlink created"
fi

# ── Register MCP server for Claude Code ─────────────────────────────

MCP_SCRIPT="$REPO_DIR/src/mcp_server.py"

if command -v claude &>/dev/null; then
    # Check if already registered
    if claude mcp list 2>/dev/null | grep -q "ai-scratchpad"; then
        ok "MCP server already registered"
    else
        if command -v uv &>/dev/null; then
            claude mcp add ai-scratchpad \
                -s user \
                -- uv run --with "mcp[cli]" python "$MCP_SCRIPT" 2>/dev/null
            ok "MCP server registered (ai-scratchpad)"
        else
            warn "uv not found — install it (brew install uv) then run:"
            echo "  claude mcp add ai-scratchpad -s user -- uv run --with 'mcp[cli]' python $MCP_SCRIPT"
        fi
    fi
else
    warn "Claude Code CLI not found. After installing it, run:"
    echo "  claude mcp add ai-scratchpad -s user -- uv run --with 'mcp[cli]' python $MCP_SCRIPT"
fi

# ── Optional: CLI tool ──────────────────────────────────────────────

CLI_SOURCE="$REPO_DIR/bin/scratchpad"
CLI_TARGET="/usr/local/bin/scratchpad"

if [[ -L "$CLI_TARGET" ]] || [[ -f "$CLI_TARGET" ]]; then
    ok "CLI tool already at $CLI_TARGET"
elif [[ -w "$(dirname "$CLI_TARGET")" ]]; then
    ln -sf "$CLI_SOURCE" "$CLI_TARGET"
    ok "CLI tool linked to $CLI_TARGET"
else
    info "To install the CLI tool: sudo ln -sf $CLI_SOURCE $CLI_TARGET"
fi

# ── Done ────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}${BOLD}Setup complete!${NC}"
echo ""
echo "  Next steps:"
echo "    1. Restart iTerm2 (the server starts automatically)"
echo "    2. View → Show Toolbelt"
echo "    3. Right-click Toolbelt → enable \"AI Scratchpad\""
echo ""
echo "  The scratchpad is also available at http://localhost:9999"
echo ""
echo "  Verify:  curl -s http://localhost:9999/health | python3 -m json.tool"
echo ""
