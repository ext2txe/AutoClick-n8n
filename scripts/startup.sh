#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-autoclick-classifier}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"

cd "$APP_DIR"

if [[ ! -x ".venv/bin/autoclick-classifier" ]]; then
    python3.11 -m venv .venv
    ./.venv/bin/python -m pip install -e .
fi

if [[ ! -f ".env" && -f ".env.example" ]]; then
    cp .env.example .env
fi

sudo bash "$SCRIPT_DIR/install-systemd-service.sh"

systemctl --no-pager status "$SERVICE_NAME"
