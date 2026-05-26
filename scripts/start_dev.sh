#!/usr/bin/env bash
# Start API + ngrok for Slack HTTP mode. Keep this terminal open.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

source .venv/bin/activate

if ! pgrep -f "uvicorn main:app" >/dev/null 2>&1; then
  echo "Starting uvicorn on :8000..."
  uvicorn main:app --reload --port 8000 &
  sleep 2
fi

if ! pgrep -f "ngrok http 8000" >/dev/null 2>&1; then
  echo "Starting ngrok..."
  ngrok http 8000 --log=stdout &
  sleep 2
fi

URL="$(curl -s http://127.0.0.1:4040/api/tunnels | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tunnels'][0]['public_url'])" 2>/dev/null || true)"
if [[ -z "$URL" ]]; then
  echo "ngrok tunnel not ready. Run: ngrok http 8000"
  exit 1
fi

echo ""
echo "=== Expert Network dev ==="
echo "Local:  http://localhost:8000/setup"
echo "Slack Request URL (paste in Mini Chiara app):"
echo "  ${URL}/slack/events"
echo ""
echo "Press Ctrl+C to stop (also stop uvicorn/ngrok in Activity Monitor if needed)."

wait
