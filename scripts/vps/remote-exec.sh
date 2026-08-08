#!/usr/bin/env bash
# Run an arbitrary remote command on the OpenClaw VPS.
# Usage: remote-exec.sh 'openclaw gateway status'
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${ROOT}/lib.sh"

PROXY_ENV="${TAILSCALE_STATE_DIR:-$HOME/.tailscale-openclaw}/proxy.env"
if [[ -f "$PROXY_ENV" ]]; then
  # shellcheck disable=SC1090
  source "$PROXY_ENV"
fi

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 '<remote command>'" >&2
  exit 1
fi

remote_bash "$1"
