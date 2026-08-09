#!/usr/bin/env bash
# Copy CURSOR_API_KEY from this environment into the VPS bridge .env and restart.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=lib.sh
source "${ROOT}/scripts/vps/lib.sh"

require_env CURSOR_API_KEY
KEYPATH="$(ensure_ssh_key)"
build_ssh_cmd "$KEYPATH"

# Pass key via env on the remote python rewrite (not argv).
export CURSOR_API_KEY
"${SSH_CMD[@]}" 'bash -s' <<'REMOTE'
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
import os
env_path = Path("/opt/openclaw-voice-bridge/.env")
text = env_path.read_text() if env_path.exists() else ""
key = os.environ["CURSOR_API_KEY"].strip()
if not key:
    raise SystemExit("empty CURSOR_API_KEY")
lines = [ln for ln in text.splitlines() if not ln.startswith("CURSOR_API_KEY=")]
lines.append(f"CURSOR_API_KEY={key}")
# Ensure related defaults exist
defaults = {
    "ENABLE_UPGRADE_APPROVALS": "true",
    "ASSISTANT_UPGRADES_ROOT": "/opt/openclaw-voice-bridge/data/assistant-upgrades",
    "CURSOR_REPO_URL": "https://github.com/sprutz/OpenclawDev",
    "CURSOR_STARTING_REF": "main",
    "CURSOR_AUTO_CREATE_PR": "true",
    "CURSOR_API_BASE": "https://api.cursor.com",
}
for name, value in defaults.items():
    if not any(ln.startswith(f"{name}=") for ln in lines):
        lines.append(f"{name}={value}")
env_path.write_text("\n".join(lines) + "\n")
env_path.chmod(0o600)
print("CURSOR_API_KEY installed:", bool(key), "len", len(key))
PY
systemctl restart openclaw-voice-bridge
sleep 2
systemctl is-active openclaw-voice-bridge
# Auth check against Cursor API (does not create an agent)
python3 - <<'PY'
import os, urllib.request, json
key = os.environ["CURSOR_API_KEY"].strip()
req = urllib.request.Request(
    "https://api.cursor.com/v1/repositories",
    headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
    method="GET",
)
# Basic auth style also supported: use urlopen with password mgr
import base64
req = urllib.request.Request(
    "https://api.cursor.com/v1/repositories",
    headers={
        "Authorization": "Basic " + base64.b64encode(f"{key}:".encode()).decode(),
        "Accept": "application/json",
    },
)
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        print("cursor_api_status", resp.status)
except Exception as exc:
    # Fallback bearer
    req2 = urllib.request.Request(
        "https://api.cursor.com/v1/repositories",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req2, timeout=60) as resp:
            print("cursor_api_status_bearer", resp.status)
    except Exception as exc2:
        print("cursor_api_check_failed", exc2)
REMOTE

echo "Done."
