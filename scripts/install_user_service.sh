#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${HOME}/.config/systemd/user"
UNIT_FILE="${HOME}/.config/systemd/user/customer-service-agent.service"
ENV_FILE="${ROOT_DIR}/.env"
PYTHON_BIN="$(conda run -n customer-service-agent python -c 'import sys; print(sys.executable)')"

escape_sed_replacement() {
  printf '%s' "$1" | sed 's/[&|]/\\&/g'
}

mkdir -p "${UNIT_DIR}"
sed \
  -e "s|__WORKDIR__|$(escape_sed_replacement "${ROOT_DIR}")|g" \
  -e "s|__ENVFILE__|$(escape_sed_replacement "${ENV_FILE}")|g" \
  -e "s|__PYTHON__|$(escape_sed_replacement "${PYTHON_BIN}")|g" \
  "${ROOT_DIR}/systemd/customer-service-agent.service.template" > "${UNIT_FILE}"
systemctl --user daemon-reload
systemctl --user enable customer-service-agent.service
echo "Installed user service: customer-service-agent.service"
echo "Start with: systemctl --user start customer-service-agent.service"
