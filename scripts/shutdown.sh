#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-autoclick-classifier}"

sudo systemctl stop "$SERVICE_NAME"
systemctl --no-pager status "$SERVICE_NAME" || true
