#!/usr/bin/env bash
# CLU Daemon - Unix Launcher with auto-restart
# Usage: ./run_daemon.sh [--verbose]

set -e
cd "$(dirname "$0")"

VENV="venv/bin/python"
if [ ! -f "$VENV" ]; then
    echo "Error: Virtual environment not found. Run: python -m venv venv && pip install -r requirements.txt"
    exit 1
fi

echo "CLU Daemon"
echo "Press Ctrl+C to stop"
echo ""

while true; do
    "$VENV" -m daemon.daemon "$@"
    echo ""
    echo "Daemon exited. Restarting in 5 seconds... (Ctrl+C to stop)"
    sleep 5
done
