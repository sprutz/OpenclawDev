#!/usr/bin/env bash
# Pull a concise OpenClaw health report from the Hostinger VPS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${ROOT}/lib.sh"

PROXY_ENV="${TAILSCALE_STATE_DIR:-$HOME/.tailscale-openclaw}/proxy.env"
if [[ -f "$PROXY_ENV" ]]; then
  # shellcheck disable=SC1090
  source "$PROXY_ENV"
fi

require_env OPENCLAW_GATEWAY_TOKEN

echo "=== remote host / openclaw CLI ==="
remote_bash 'hostname; uptime; echo; command -v openclaw >/dev/null && openclaw gateway status || echo "openclaw CLI missing"; openclaw channels status --probe 2>/dev/null || true'

KEY_PATH="$(ensure_ssh_key)"
LOCAL_PORT="${OPENCLAW_LOCAL_TUNNEL_PORT:-18789}"
REMOTE_PORT="${OPENCLAW_REMOTE_GATEWAY_PORT:-18789}"

# Drop any stale local listener on the tunnel port.
if ss -ltn 2>/dev/null | grep -q ":${LOCAL_PORT} "; then
  echo "Local port ${LOCAL_PORT} already in use; reusing existing tunnel if present."
else
  echo "Opening SSH tunnel localhost:${LOCAL_PORT} -> 127.0.0.1:${REMOTE_PORT} on VPS"
  build_ssh_cmd "$KEY_PATH"
  # Insert -fN -L before destination host argument.
  TUNNEL_CMD=("${SSH_CMD[@]}")
  # ssh [opts] user@host  ->  ssh -fN -L ... [opts] user@host
  TUNNEL_CMD=(ssh -fN -L "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" "${SSH_CMD[@]:1}")
  "${TUNNEL_CMD[@]}"
  sleep 1
fi

echo "=== gateway via tunnel ==="
# Prefer the live health endpoints; admin-http-rpc is optional and often not enabled.
if curl -fsS "http://127.0.0.1:${LOCAL_PORT}/healthz" \
  -H "Authorization: Bearer ${OPENCLAW_GATEWAY_TOKEN}"; then
  echo
elif curl -fsS "http://127.0.0.1:${LOCAL_PORT}/health" \
  -H "Authorization: Bearer ${OPENCLAW_GATEWAY_TOKEN}"; then
  echo
elif curl -fsS "http://127.0.0.1:${LOCAL_PORT}/api/v1/admin/rpc" \
  -H "Authorization: Bearer ${OPENCLAW_GATEWAY_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"method":"health","params":{}}'; then
  echo
else
  echo "health endpoints unavailable; raw root probe:"
  curl -sS -o /dev/null -w "GET / -> %{http_code}\n" \
    -H "Authorization: Bearer ${OPENCLAW_GATEWAY_TOKEN}" \
    "http://127.0.0.1:${LOCAL_PORT}/" || true
fi
