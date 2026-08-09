#!/usr/bin/env bash
# Shared helpers for Cursor Cloud Agent ↔ Hostinger OpenClaw operations.
set -euo pipefail

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required secret/env: ${name}" >&2
    echo "Add it in Cursor Cloud Agents → Secrets, then restart the agent." >&2
    exit 2
  fi
}

ensure_ssh_key() {
  require_env OPENCLAW_VPS_SSH_PRIVATE_KEY
  local key_path="${OPENCLAW_SSH_KEY_PATH:-$HOME/.ssh/openclaw_vps}"
  mkdir -p "$(dirname "$key_path")"
  chmod 700 "$(dirname "$key_path")"
  # Rewrite atomically; secrets may contain literal \n sequences from dashboards.
  python3 - "$key_path" <<'PY'
import os, pathlib, sys
path = pathlib.Path(sys.argv[1])
raw = os.environ["OPENCLAW_VPS_SSH_PRIVATE_KEY"]
key = raw.replace("\\n", "\n").strip() + "\n"
path.write_text(key)
path.chmod(0o600)
PY
  echo "$key_path"
}

# Populate global SSH_CMD array for ssh/scp invocations.
build_ssh_cmd() {
  local key_path="$1"
  require_env OPENCLAW_VPS_HOST
  require_env OPENCLAW_VPS_USER

  SSH_CMD=(
    ssh
    -i "$key_path"
    -o IdentitiesOnly=yes
    -o StrictHostKeyChecking=accept-new
    -o UserKnownHostsFile="$HOME/.ssh/openclaw_known_hosts"
  )

  local socks=""
  if [[ -n "${TAILSCALE_SOCKS:-}" ]]; then
    socks="$TAILSCALE_SOCKS"
  elif [[ "${ALL_PROXY:-}" == socks5h://* || "${ALL_PROXY:-}" == socks5://* ]]; then
    socks="${ALL_PROXY#socks5h://}"
    socks="${socks#socks5://}"
    socks="${socks%/}"
  fi

  if [[ -n "$socks" ]]; then
    if command -v nc >/dev/null 2>&1; then
      SSH_CMD+=(-o "ProxyCommand=nc -X 5 -x ${socks} %h %p")
    else
      echo "netcat (nc) is required for Tailscale userspace SSH proxying." >&2
      exit 3
    fi
  fi

  SSH_CMD+=("${OPENCLAW_VPS_USER}@${OPENCLAW_VPS_HOST}")
}

remote_ssh() {
  local key_path
  key_path="$(ensure_ssh_key)"
  build_ssh_cmd "$key_path"
  "${SSH_CMD[@]}" "$@"
}

remote_bash() {
  local script="$1"
  remote_ssh "bash -lc $(printf '%q' "$script")"
}
