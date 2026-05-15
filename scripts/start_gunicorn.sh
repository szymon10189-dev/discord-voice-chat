#!/usr/bin/env bash
# Serwer WSGI (tylko HTTP, bez WebSocketów).
# Render: użyj tylko jeśli nie potrzebujesz Channels; w przeciwnym razie start_daphne.sh
set -euo pipefail
cd "$(dirname "$0")/.."
exec gunicorn -c gunicorn.conf.py discord_clone.wsgi:application
