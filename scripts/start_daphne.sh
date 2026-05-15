#!/usr/bin/env bash
# Serwer ASGI: HTTP + WebSockety (Django Channels).
# Render: ustaw Start Command na: bash scripts/start_daphne.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8000}"
exec daphne -b 0.0.0.0 -p "$PORT" discord_clone.asgi:application
