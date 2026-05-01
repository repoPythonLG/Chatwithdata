#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
CONFIG_PATH="${1:-$ROOT_DIR/cloudera_app_config.json}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
LOG_DIR="$ROOT_DIR/.data/logs"

"$ROOT_DIR/stop.sh" "$CONFIG_PATH"
mkdir -p "$LOG_DIR"

nohup "$PYTHON_BIN" "$ROOT_DIR/start_app.py" --config "$CONFIG_PATH" \
  >> "$LOG_DIR/supervisor.log" 2>&1 &

echo "Chat with Data restarted with supervisor PID $!."
echo "Frontend will be served on the configured host/port, default http://127.0.0.1:8090."
