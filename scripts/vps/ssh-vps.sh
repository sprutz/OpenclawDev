#!/usr/bin/env bash
# Interactive or one-shot SSH into the Hostinger OpenClaw VPS via Tailscale.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${ROOT}/lib.sh"

PROXY_ENV="${TAILSCALE_STATE_DIR:-$HOME/.tailscale-openclaw}/proxy.env"
if [[ -f "$PROXY_ENV" ]]; then
  # shellcheck disable=SC1090
  source "$PROXY_ENV"
fi

if [[ $# -eq 0 ]]; then
  remote_ssh
else
  remote_ssh "$@"
fi
