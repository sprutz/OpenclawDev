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

echo "=== token fingerprint (local Cursor secret) ==="
python3 - <<'PY'
import hashlib, os
token = os.environ["OPENCLAW_GATEWAY_TOKEN"]
print(f"cursor_sha12={hashlib.sha256(token.encode()).hexdigest()[:12]} len={len(token)}")
PY

echo "=== remote host / live gateway (stan) ==="
# The live gateway on this Hostinger box runs as stan. Root has a separate,
# inactive OpenClaw install — probing as root produces a misleading token-mismatch.
# Timeouts avoid hanging the operator script on slow channel probes.
remote_bash 'set -euo pipefail
hostname
uptime
echo
echo "--- listener ---"
ss -ltnp 2>/dev/null | grep 18789 || true
echo
echo "--- stan gateway status ---"
timeout 40 sudo -u stan -H openclaw gateway status || true
echo
echo "--- stan channels (probe, 45s cap) ---"
timeout 45 sudo -u stan -H openclaw channels status --probe 2>/dev/null || echo "(channels probe timed out or unavailable)"
echo
echo "--- token match (sha12 only) ---"
python3 - <<'"'"'PY'"'"'
import hashlib, json, os
stan = json.load(open("/home/stan/.openclaw/openclaw.json"))["gateway"]["auth"]["token"]
root = json.load(open("/root/.openclaw/openclaw.json"))["gateway"]["auth"]["token"]
print("stan_sha12", hashlib.sha256(stan.encode()).hexdigest()[:12])
print("root_sha12", hashlib.sha256(root.encode()).hexdigest()[:12])
PY
'

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
# Note: /healthz does not validate the bearer token — use stan RPC probe above for auth.
curl_common=(--max-time 10 --connect-timeout 5 -fsS)
if curl "${curl_common[@]}" "http://127.0.0.1:${LOCAL_PORT}/healthz" \
  -H "Authorization: Bearer ${OPENCLAW_GATEWAY_TOKEN}"; then
  echo
elif curl "${curl_common[@]}" "http://127.0.0.1:${LOCAL_PORT}/health" \
  -H "Authorization: Bearer ${OPENCLAW_GATEWAY_TOKEN}"; then
  echo
elif curl "${curl_common[@]}" "http://127.0.0.1:${LOCAL_PORT}/api/v1/admin/rpc" \
  -H "Authorization: Bearer ${OPENCLAW_GATEWAY_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"method":"health","params":{}}'; then
  echo
else
  echo "health endpoints unavailable; raw root probe:"
  curl --max-time 10 -sS -o /dev/null -w "GET / -> %{http_code}\n" \
    -H "Authorization: Bearer ${OPENCLAW_GATEWAY_TOKEN}" \
    "http://127.0.0.1:${LOCAL_PORT}/" || true
fi

echo "=== auth check (Cursor secret vs stan config) ==="
# Compare without printing tokens. Exit non-zero on mismatch so CI/agents notice.
TOKEN_B64="$(python3 -c 'import os,base64; print(base64.b64encode(os.environ["OPENCLAW_GATEWAY_TOKEN"].encode()).decode())')"
remote_bash "python3 - <<'PY'
import base64, hashlib, json, sys
token = base64.b64decode('${TOKEN_B64}').decode()
stan = json.load(open('/home/stan/.openclaw/openclaw.json'))['gateway']['auth']['token']
cursor_sha = hashlib.sha256(token.encode()).hexdigest()[:12]
stan_sha = hashlib.sha256(stan.encode()).hexdigest()[:12]
print(f'MATCH_STAN={token == stan}')
print(f'cursor_sha12={cursor_sha}')
print(f'stan_sha12={stan_sha}')
sys.exit(0 if token == stan else 1)
PY"
