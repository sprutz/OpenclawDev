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
SOCKET="${TAILSCALE_SOCKET:-$STATE_DIR/tailscaled.sock}"
mkdir -p "$STATE_DIR"

if ! command -v tailscaled >/dev/null 2>&1; then
  echo "tailscaled not installed. Install Tailscale in the Cloud Agent environment first." >&2
  echo "Tip: curl -fsSL https://tailscale.com/install.sh | sudo bash && sudo apt-get install -y netcat-openbsd" >&2
  exit 3
fi

# Prefer our userspace daemon; stop a system TUN service if it owns the default socket.
if pgrep -x tailscaled >/dev/null 2>&1 && [[ ! -S "$SOCKET" ]]; then
  if systemctl is-active --quiet tailscaled 2>/dev/null; then
    echo "Stopping system tailscaled (TUN) so userspace mode can start..."
    sudo systemctl stop tailscaled 2>/dev/null || true
    sudo systemctl disable tailscaled 2>/dev/null || true
    sleep 1
  fi
fi

if [[ -S "$SOCKET" ]] && pgrep -x tailscaled >/dev/null 2>&1; then
  echo "tailscaled already running (socket: $SOCKET)"
else
  # Drop any prior daemon that is not using our userspace socket.
  pkill -x tailscaled 2>/dev/null || true
  sleep 1
  echo "Starting tailscaled (userspace networking)..."
  nohup tailscaled \
    --tun=userspace-networking \
    --socks5-server="localhost:${SOCKS_PORT}" \
    --outbound-http-proxy-listen="localhost:${HTTP_PORT}" \
    --statedir="$STATE_DIR" \
    --socket="$SOCKET" \
    >"$STATE_DIR/tailscaled.log" 2>&1 &
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    [[ -S "$SOCKET" ]] && break
    sleep 0.5
  done
  if [[ ! -S "$SOCKET" ]]; then
    echo "tailscaled failed to create socket. Last log lines:" >&2
    tail -n 40 "$STATE_DIR/tailscaled.log" >&2 || true
    exit 3
  fi
fi

TS=(tailscale --socket="$SOCKET")

# Idempotent join/login.
# accept-dns=false: userspace VMs often cannot rewrite host resolver config.
"${TS[@]}" up \
  --authkey="$TAILSCALE_AUTHKEY" \
  --hostname="${TAILSCALE_HOSTNAME:-cursor-openclaw}" \
  --accept-routes=true \
  --accept-dns=false \
  --ssh=false

export ALL_PROXY="socks5h://localhost:${SOCKS_PORT}/"
export HTTP_PROXY="http://localhost:${HTTP_PORT}/"
export HTTPS_PROXY="http://localhost:${HTTP_PORT}/"
export TAILSCALE_SOCKS="localhost:${SOCKS_PORT}"
export TS_SOCKET="$SOCKET"

# Persist for sibling shells in this session directory
cat >"$STATE_DIR/proxy.env" <<EOF
export ALL_PROXY=${ALL_PROXY}
export HTTP_PROXY=${HTTP_PROXY}
export HTTPS_PROXY=${HTTPS_PROXY}
export TAILSCALE_SOCKS=${TAILSCALE_SOCKS}
export TS_SOCKET=${TS_SOCKET}
alias tailscale='tailscale --socket=${TS_SOCKET}'
EOF

echo "Tailscale status:"
"${TS[@]}" status || true
echo "Proxy env written to ${STATE_DIR}/proxy.env"
echo "Source it before SSH/OpenClaw calls: source ${STATE_DIR}/proxy.env"
