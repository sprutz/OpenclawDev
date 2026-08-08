#!/usr/bin/env bash
# Bring up Tailscale in userspace mode inside a Cursor Cloud Agent VM.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${ROOT}/lib.sh"

require_env TAILSCALE_AUTHKEY

SOCKS_PORT="${TAILSCALE_SOCKS_PORT:-1055}"
HTTP_PORT="${TAILSCALE_HTTP_PROXY_PORT:-1054}"
STATE_DIR="${TAILSCALE_STATE_DIR:-$HOME/.tailscale-openclaw}"
mkdir -p "$STATE_DIR"

if ! command -v tailscaled >/dev/null 2>&1; then
  echo "tailscaled not installed. Install Tailscale in the Cloud Agent environment first." >&2
  exit 3
fi

if pgrep -x tailscaled >/dev/null 2>&1; then
  echo "tailscaled already running"
else
  echo "Starting tailscaled (userspace networking)..."
  nohup tailscaled \
    --tun=userspace-networking \
    --socks5-server="localhost:${SOCKS_PORT}" \
    --outbound-http-proxy-listen="localhost:${HTTP_PORT}" \
    --statedir="$STATE_DIR" \
    >"$STATE_DIR/tailscaled.log" 2>&1 &
  sleep 2
fi

# Idempotent join/login
tailscale up \
  --authkey="$TAILSCALE_AUTHKEY" \
  --hostname="${TAILSCALE_HOSTNAME:-cursor-openclaw}" \
  --accept-routes=true \
  --accept-dns=true \
  --ssh=false

export ALL_PROXY="socks5h://localhost:${SOCKS_PORT}/"
export HTTP_PROXY="http://localhost:${HTTP_PORT}/"
export HTTPS_PROXY="http://localhost:${HTTP_PORT}/"
export TAILSCALE_SOCKS="localhost:${SOCKS_PORT}"

# Persist for sibling shells in this session directory
cat >"$STATE_DIR/proxy.env" <<EOF
export ALL_PROXY=${ALL_PROXY}
export HTTP_PROXY=${HTTP_PROXY}
export HTTPS_PROXY=${HTTPS_PROXY}
export TAILSCALE_SOCKS=${TAILSCALE_SOCKS}
EOF

echo "Tailscale status:"
tailscale status || true
echo "Proxy env written to ${STATE_DIR}/proxy.env"
echo "Source it before SSH/OpenClaw calls: source ${STATE_DIR}/proxy.env"
