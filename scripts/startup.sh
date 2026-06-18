#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-autoclick-classifier}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

cd "$APP_DIR"

if [[ ! -x ".venv/bin/autoclick-classifier" ]]; then
    python3.11 -m venv .venv
    ./.venv/bin/python -m pip install -e .
fi

if [[ ! -f ".env" && -f ".env.example" ]]; then
    cp .env.example .env
fi

if [[ ! -f "$UNIT_PATH" ]]; then
    sudo bash "$SCRIPT_DIR/install-systemd-service.sh"
else
    sudo systemctl daemon-reload
    sudo systemctl enable --now "$SERVICE_NAME"
fi

systemctl --no-pager status "$SERVICE_NAME"
