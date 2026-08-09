#!/usr/bin/env bash
# Install OpenClaw cron job that writes one daily assistant-upgrade suggestion.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=lib.sh
source "${ROOT}/scripts/vps/lib.sh"

PROMPT_FILE="${ROOT}/deploy/templates/daily-upgrade-recommendation-prompt.md"
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

"${SCP[@]}" "${PROMPT_FILE}" \
  "${OPENCLAW_VPS_USER}@${OPENCLAW_VPS_HOST}:/tmp/daily-upgrade-recommendation-prompt.md"

"${SSH_CMD[@]}" 'bash -s' <<'REMOTE'
set -euo pipefail
install -d -m 755 /opt/openclaw-voice-bridge/data/assistant-upgrades
install -d -o stan -g stan -m 755 /home/stan/clawd/second-brain/docs/assistant-upgrades
install -d -o stan -g stan -m 755 /home/stan/clawd/second-brain/docs/templates
install -o stan -g stan -m 644 /tmp/daily-upgrade-recommendation-prompt.md \
  /home/stan/clawd/second-brain/docs/templates/daily-upgrade-recommendation-prompt.md
chown -R ubuntu:ubuntu /opt/openclaw-voice-bridge/data
# Let stan (OpenClaw) write suggestions the bridge can read/update.
setfacl -m u:stan:rwx /opt/openclaw-voice-bridge/data/assistant-upgrades || true
setfacl -d -m u:stan:rwx /opt/openclaw-voice-bridge/data/assistant-upgrades || true
setfacl -m u:ubuntu:rwx /opt/openclaw-voice-bridge/data/assistant-upgrades || true
setfacl -d -m u:ubuntu:rwx /opt/openclaw-voice-bridge/data/assistant-upgrades || true

# Remove prior job with same name if present (best-effort).
sudo -u stan -H bash -lc 'openclaw cron list 2>/dev/null | grep -i "Daily assistant upgrade" || true'

MSG=$(cat <<'EOF'
Daily OpenClaw assistant upgrade recommendation.

Follow /home/stan/clawd/second-brain/docs/templates/daily-upgrade-recommendation-prompt.md exactly.

Write one JSON suggestion to /opt/openclaw-voice-bridge/data/assistant-upgrades/YYYY-MM-DD.json (today's date), mirror .md beside it, and copy the markdown to /home/stan/clawd/second-brain/docs/assistant-upgrades/YYYY-MM-DD.md.

Then reply on Telegram with the title and spoken summary so Stan can approve by voice later ("what's today's upgrade suggestion?" / "approve it").
EOF
)

# Idempotent-ish: if a job with this exact name exists, leave it; otherwise add.
if sudo -u stan -H bash -lc 'openclaw cron list --json 2>/dev/null' | grep -q 'Daily assistant upgrade recommendation'; then
  echo "Cron job already present"
else
  sudo -u stan -H bash -lc "openclaw cron add \
    --name $(printf %q 'Daily assistant upgrade recommendation') \
    --cron '0 22 * * *' \
    --session isolated \
    --announce \
    --channel telegram \
    --to 8160051220 \
    --timeout-seconds 420 \
    --message $(printf %q "$MSG")"
  echo "Cron job added (22:00 UTC daily → Telegram)"
fi

sudo -u stan -H bash -lc 'openclaw cron list' | sed -n '1,80p'
REMOTE

echo "Done."
