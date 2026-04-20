#!/usr/bin/env bash
# PyJHora launcher — picks Qt desktop UI or FastAPI web UI.
# Usage:
#   ./run.sh web     # FastAPI web UI on http://localhost:8000 (default)
#   ./run.sh qt      # PyQt6 desktop multi-tab UI (needs $DISPLAY)
#   ./run.sh qt panchangam | vedic_calendar | match_ui

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

if [[ ! -d venv ]]; then
  echo "Creating venv..."
  python3 -m venv venv
fi
# shellcheck source=/dev/null
source venv/bin/activate

if [[ ! -f venv/.deps-installed ]]; then
  echo "Installing dependencies (first run)..."
  pip install --quiet --upgrade pip
  pip install --quiet -r requirements.txt
  pip install --quiet python-dateutil scipy fastapi uvicorn jinja2 python-multipart
  touch venv/.deps-installed
fi

export PYTHONPATH="$HERE/src:${PYTHONPATH:-}"

MODE="${1:-web}"

case "$MODE" in
  web)
    PORT="${PORT:-8000}"
    echo "Starting PyJHora Web on http://localhost:$PORT"
    exec uvicorn web.main:app --host 0.0.0.0 --port "$PORT"
    ;;
  qt)
    UI="${2:-horo_chart_tabs}"
    : "${DISPLAY:=:1}"
    : "${XAUTHORITY:=/run/user/$(id -u)/gdm/Xauthority}"
    export DISPLAY XAUTHORITY
    echo "Launching Qt UI: jhora.ui.$UI (DISPLAY=$DISPLAY)"
    exec python3 -m "jhora.ui.$UI"
    ;;
  *)
    echo "Usage: $0 {web|qt} [qt-module]"
    echo "  web          → FastAPI web UI"
    echo "  qt           → Qt multi-tab UI (default: horo_chart_tabs)"
    echo "  qt <module>  → panchangam | vedic_calendar | match_ui | horo_chart_tabs"
    exit 1
    ;;
esac
