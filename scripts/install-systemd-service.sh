#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-autoclick-classifier}"
SERVICE_USER="${SERVICE_USER:-${SUDO_USER:-$USER}}"
SERVICE_GROUP="${SERVICE_GROUP:-}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8765}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
APP_DIR="${APP_DIR:-$(cd "$SCRIPT_DIR/.." && pwd -P)}"
WORKING_DIRECTORY="${WORKING_DIRECTORY:-$APP_DIR}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
EXECUTABLE="${EXECUTABLE:-$APP_DIR/.venv/bin/autoclick-classifier}"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

quote_systemd_value() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    printf '"%s"' "$value"
}

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this installer with sudo so it can write ${UNIT_PATH}." >&2
    exit 1
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    echo "Service user '${SERVICE_USER}' does not exist." >&2
    exit 1
fi

if [[ -z "$SERVICE_GROUP" ]]; then
    SERVICE_GROUP="$(id -gn "$SERVICE_USER")"
fi

if [[ ! -x "$EXECUTABLE" ]]; then
    cat >&2 <<EOF
Cannot execute ${EXECUTABLE}.

Create the virtual environment and install the project first:
  python3.11 -m venv .venv
  ./.venv/bin/python -m pip install -e .
EOF
    exit 1
fi

mkdir -p "$APP_DIR/data"
chown "$SERVICE_USER:$SERVICE_GROUP" "$APP_DIR/data"

cat >"$UNIT_PATH" <<EOF
[Unit]
Description=AutoClick n8n job classifier API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
WorkingDirectory=$(quote_systemd_value "$WORKING_DIRECTORY")
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-$(quote_systemd_value "$ENV_FILE")
ExecStart=$(quote_systemd_value "$EXECUTABLE") --host ${HOST} --port ${PORT}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"

cat <<EOF
Installed and started ${SERVICE_NAME}.

Useful commands:
  sudo systemctl status ${SERVICE_NAME}
  sudo journalctl -u ${SERVICE_NAME} -f
  curl http://${HOST}:${PORT}/health
EOF
