#!/usr/bin/env bash
# Full-stack dev mode: Python auto-restart + Vite HMR
# Usage: ./dev.sh
#   Toolbelt WebView at :9999 redirects to Vite at :5173
#   Vite proxies /api and /events back to :9999
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

cleanup() {
    echo "Shutting down..."
    kill $PY_PID $VITE_PID 2>/dev/null
    wait $PY_PID $VITE_PID 2>/dev/null
}
trap cleanup EXIT INT TERM

# Python server with auto-restart on src/ changes
echo "▸ Starting Python server with auto-reload..."
cd "$DIR"
PYTHONPATH="$DIR/src" SCRATCHPAD_DEV=1 uv run --with "watchfiles,aiohttp>=3.9" \
    watchfiles \
    --filter python \
    "python3 -m ai_scratchpad" \
    src/ai_scratchpad/ &
PY_PID=$!

# Wait for Python server
for i in $(seq 1 15); do
    if lsof -ti :9999 >/dev/null 2>&1; then
        echo "▸ Python server ready on :9999"
        break
    fi
    sleep 1
done

# Vite dev server with HMR (proxies API to :9999)
echo "▸ Starting Vite dev server..."
cd "$DIR/ui"
pnpm dev 2>/dev/null &
VITE_PID=$!

echo ""
echo "Dev mode running:"
echo "  Toolbelt loads :9999 → redirects to :5173 (Vite HMR)"
echo "  Vite proxies /api, /events → :9999 (Python)"
echo "  Python auto-restarts on src/ changes"
echo "  Ctrl+C to stop"
echo ""

wait
