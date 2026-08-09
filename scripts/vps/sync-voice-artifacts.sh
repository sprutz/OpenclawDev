#!/usr/bin/env bash
# Sync voice agent prompt/MCP artifacts onto the OpenClaw VPS.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=lib.sh
source "${ROOT}/scripts/vps/lib.sh"

KEYPATH="$(ensure_ssh_key)"
build_ssh_cmd "$KEYPATH"

PROXY_CMD=""
if [[ -n "${TAILSCALE_SOCKS:-}" ]]; then
  PROXY_CMD="nc -X 5 -x ${TAILSCALE_SOCKS} %h %p"
elif [[ "${ALL_PROXY:-}" == socks5h://* || "${ALL_PROXY:-}" == socks5://* ]]; then
  socks="${ALL_PROXY#socks5h://}"
  socks="${socks#socks5://}"
  socks="${socks%/}"
  PROXY_CMD="nc -X 5 -x ${socks} %h %p"
fi

SCP=(scp -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new
  -o UserKnownHostsFile="${HOME}/.ssh/openclaw_known_hosts" -i "${KEYPATH}")
if [[ -n "${PROXY_CMD}" ]]; then
  SCP+=(-o "ProxyCommand=${PROXY_CMD}")
fi

echo "Syncing voice artifacts to ${OPENCLAW_VPS_USER}@${OPENCLAW_VPS_HOST}..."
"${SSH_CMD[@]}" 'mkdir -p /tmp/voice-artifacts/static/voice /tmp/voice-artifacts/bridge'
"${SCP[@]}" \
  "${ROOT}/grok-voice/prompts/system.md" \
  "${ROOT}/grok-voice/configs/voice-agent-mcp.json" \
  "${ROOT}/grok-voice/configs/tools.json" \
  "${ROOT}/grok-voice/examples/dialogues.md" \
  "${ROOT}/grok-voice/README.md" \
  "${ROOT}/bridge/src/openclaw_voice_bridge/app.py" \
  "${ROOT}/bridge/src/openclaw_voice_bridge/config.py" \
  "${ROOT}/bridge/src/openclaw_voice_bridge/voice_session.py" \
  "${ROOT}/bridge/src/openclaw_voice_bridge/tools.py" \
  "${ROOT}/bridge/src/openclaw_voice_bridge/mcp_server.py" \
  "${ROOT}/bridge/src/openclaw_voice_bridge/upgrades.py" \
  "${ROOT}/bridge/src/openclaw_voice_bridge/cursor_client.py" \
  "${OPENCLAW_VPS_USER}@${OPENCLAW_VPS_HOST}:/tmp/voice-artifacts/"
"${SCP[@]}" \
  "${ROOT}/bridge/src/openclaw_voice_bridge/static/voice/index.html" \
  "${OPENCLAW_VPS_USER}@${OPENCLAW_VPS_HOST}:/tmp/voice-artifacts/static/voice/index.html"

"${SSH_CMD[@]}" 'bash -s' <<'REMOTE'
set -euo pipefail
SRC=/tmp/voice-artifacts
PKG=/opt/openclaw-voice-bridge/bridge/src/openclaw_voice_bridge
install -d -m 755 /opt/openclaw-voice-bridge/grok-voice/prompts
install -d -m 755 /opt/openclaw-voice-bridge/grok-voice/configs
install -d -m 755 /opt/openclaw-voice-bridge/grok-voice/examples
install -d -m 755 "$PKG/static/voice"
install -d -m 700 /root/openclaw-backups
install -d -o stan -g stan -m 755 /home/stan/clawd/second-brain/docs

install -o ubuntu -g ubuntu -m 644 "$SRC/system.md" /opt/openclaw-voice-bridge/grok-voice/prompts/system.md
install -o ubuntu -g ubuntu -m 644 "$SRC/voice-agent-mcp.json" /opt/openclaw-voice-bridge/grok-voice/configs/voice-agent-mcp.json
install -o ubuntu -g ubuntu -m 644 "$SRC/tools.json" /opt/openclaw-voice-bridge/grok-voice/configs/tools.json
install -o ubuntu -g ubuntu -m 644 "$SRC/dialogues.md" /opt/openclaw-voice-bridge/grok-voice/examples/dialogues.md
install -o ubuntu -g ubuntu -m 644 "$SRC/README.md" /opt/openclaw-voice-bridge/grok-voice/README.md
install -o ubuntu -g ubuntu -m 644 "$SRC/app.py" "$PKG/app.py"
install -o ubuntu -g ubuntu -m 644 "$SRC/config.py" "$PKG/config.py"
install -o ubuntu -g ubuntu -m 644 "$SRC/voice_session.py" "$PKG/voice_session.py"
install -o ubuntu -g ubuntu -m 644 "$SRC/tools.py" "$PKG/tools.py"
install -o ubuntu -g ubuntu -m 644 "$SRC/mcp_server.py" "$PKG/mcp_server.py"
install -o ubuntu -g ubuntu -m 644 "$SRC/upgrades.py" "$PKG/upgrades.py"
install -o ubuntu -g ubuntu -m 644 "$SRC/cursor_client.py" "$PKG/cursor_client.py"
install -o ubuntu -g ubuntu -m 644 "$SRC/static/voice/index.html" "$PKG/static/voice/index.html"
install -d -m 755 /opt/openclaw-voice-bridge/data/assistant-upgrades
chown ubuntu:ubuntu /opt/openclaw-voice-bridge/data/assistant-upgrades || true

# Upgrade approvals + Cursor launch (key may be injected separately)
if grep -q '^ENABLE_UPGRADE_APPROVALS=' /opt/openclaw-voice-bridge/.env; then
  sed -i 's/^ENABLE_UPGRADE_APPROVALS=.*/ENABLE_UPGRADE_APPROVALS=true/' /opt/openclaw-voice-bridge/.env
else
  echo 'ENABLE_UPGRADE_APPROVALS=true' >> /opt/openclaw-voice-bridge/.env
fi
grep -q '^ASSISTANT_UPGRADES_ROOT=' /opt/openclaw-voice-bridge/.env || \
  echo 'ASSISTANT_UPGRADES_ROOT=/opt/openclaw-voice-bridge/data/assistant-upgrades' >> /opt/openclaw-voice-bridge/.env
grep -q '^CURSOR_REPO_URL=' /opt/openclaw-voice-bridge/.env || \
  echo 'CURSOR_REPO_URL=https://github.com/sprutz/OpenclawDev' >> /opt/openclaw-voice-bridge/.env
grep -q '^CURSOR_STARTING_REF=' /opt/openclaw-voice-bridge/.env || \
  echo 'CURSOR_STARTING_REF=main' >> /opt/openclaw-voice-bridge/.env
grep -q '^CURSOR_AUTO_CREATE_PR=' /opt/openclaw-voice-bridge/.env || \
  echo 'CURSOR_AUTO_CREATE_PR=true' >> /opt/openclaw-voice-bridge/.env

install -m 600 "$SRC/system.md" /root/openclaw-backups/voice-agent-system.md
install -m 600 "$SRC/voice-agent-mcp.json" /root/openclaw-backups/voice-agent-mcp.json
install -o stan -g stan -m 644 "$SRC/system.md" /home/stan/clawd/second-brain/docs/voice-agent-system.md

# Keep compacted spoken unlock password
if grep -q '^VOICE_SPOKEN_PASSWORD=' /opt/openclaw-voice-bridge/.env; then
  sed -i 's/^VOICE_SPOKEN_PASSWORD=.*/VOICE_SPOKEN_PASSWORD=pursuewithenthusiasm/' /opt/openclaw-voice-bridge/.env
else
  echo 'VOICE_SPOKEN_PASSWORD=pursuewithenthusiasm' >> /opt/openclaw-voice-bridge/.env
fi
grep -q '^VOICE_UNLOCK_TTL_SECONDS=' /opt/openclaw-voice-bridge/.env || echo 'VOICE_UNLOCK_TTL_SECONDS=28800' >> /opt/openclaw-voice-bridge/.env

# Operator note for OpenClaw workspace
if ! grep -q 'Voice spoken unlock' /home/stan/clawd/TOOLS.md 2>/dev/null; then
  cat >> /home/stan/clawd/TOOLS.md <<'EOF'

## Voice spoken unlock
- Bridge password (compact): `pursuewithenthusiasm`
- User may speak: “pursue with enthusiasm”
- Agent must call MCP `openclaw_voice_unlock` with no spaces
- Instruction copies: `second-brain/docs/voice-agent-system.md`
EOF
  chown stan:stan /home/stan/clawd/TOOLS.md
fi

systemctl reset-failed openclaw-voice-bridge 2>/dev/null || true
systemctl restart openclaw-voice-bridge
sleep 2
systemctl is-active openclaw-voice-bridge
echo "Synced:"
wc -l /opt/openclaw-voice-bridge/grok-voice/prompts/system.md \
  /root/openclaw-backups/voice-agent-system.md \
  /home/stan/clawd/second-brain/docs/voice-agent-system.md
grep '^VOICE_SPOKEN_PASSWORD=' /opt/openclaw-voice-bridge/.env
REMOTE

echo "Done."
