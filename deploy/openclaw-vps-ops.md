# OpenClaw VPS ops (stan)

Live OpenClaw on the Hostinger VPS is owned by user **`stan`**. Do not use `/root/.openclaw`.

## Current baseline (2026-08-09)

| Item | Value |
| --- | --- |
| Package | `openclaw@2026.7.1-2` |
| Node | `v22.23.2` (NodeSource 22.x; OpenClaw requires `>=22.22.3`) |
| Service | `stan` user systemd: `openclaw-gateway.service` |
| Config | `/home/stan/.openclaw/openclaw.json` |
| Gateway bind | `loopback` (`127.0.0.1:18789`) |
| Telegram | `@QDS_Stan_bot`, `dmPolicy=pairing`, `groupPolicy=allowlist` |
| Default model | `xai/grok-4.5` with fallbacks `openai/gpt-5.4`, `minimax/MiniMax-M2.7` |

Root leftovers are archived under `/root/openclaw-backups/` and must stay inactive.

## Safe update procedure

Always operate with stan's runtime bus:

```bash
export XDG_RUNTIME_DIR=/run/user/$(id -u stan)
sudo -u stan -H bash -lc 'export XDG_RUNTIME_DIR=/run/user/1001; openclaw gateway status'
```

1. Backup:
   ```bash
   TS=$(date -u +%Y%m%dT%H%M%SZ)
   mkdir -p /root/openclaw-backups/$TS
   cp -a /home/stan/.openclaw /root/openclaw-backups/$TS/stan-openclaw
   cp -a /home/stan/.config/systemd/user/openclaw-gateway.service /root/openclaw-backups/$TS/
   ```
2. Stop gateway before a global npm package swap:
   ```bash
   sudo -u stan -H bash -lc 'export XDG_RUNTIME_DIR=/run/user/1001; systemctl --user stop openclaw-gateway.service'
   ```
3. Ensure Node meets OpenClaw `engines.node`, then update as root (global install lives in `/usr/lib/node_modules`):
   ```bash
   node -v
   npm install -g openclaw@latest
   ```
4. Repair + reinstall service as stan:
   ```bash
   sudo -u stan -H bash -lc 'export XDG_RUNTIME_DIR=/run/user/1001; openclaw doctor --fix --non-interactive; openclaw gateway install --force; systemctl --user daemon-reload; systemctl --user restart openclaw-gateway.service'
   ```
5. Verify:
   ```bash
   sudo -u stan -H bash -lc 'export XDG_RUNTIME_DIR=/run/user/1001; openclaw gateway status; openclaw channels status --probe'
   curl -sS http://127.0.0.1:18789/healthz
   ```

If startup reports a migration lock, wait for the stated expiry before restarting again.

## xAI / Grok

```bash
# Put key in service env + auth profile (stan)
printf '%s' "$XAI_API_KEY" | sudo -u stan -H openclaw models auth paste-api-key --provider xai --profile-id xai:default
sudo -u stan -H openclaw models set xai/grok-4.5
# Keep OPENAI_API_KEY in the systemd unit as fallback
```

Smoke test:

```bash
sudo -u stan -H bash -lc 'export XDG_RUNTIME_DIR=/run/user/1001; openclaw agent --agent main --session-key agent:main:grok-smoke --model xai/grok-4.5 --thinking off --message "Reply with exactly: GROK45_OK" --json'
```

## Security baseline (average)

- Gateway bound to **loopback only**; Cursor reaches it via Tailscale + SSH tunnel.
- UFW enabled: allow SSH + `tailscale0`, deny `18789/tcp` from WAN.
- SSH: password auth off, root login `prohibit-password`, pubkey only.
- Telegram DMs require pairing; groups are allowlisted.
- Cursor `OPENCLAW_GATEWAY_TOKEN` must match **stan** `gateway.auth.token` (not any old root token).
- Do not store gateway tokens in the systemd unit (`openclaw gateway install --force` clears embedded tokens).

## Cursor operator path

```bash
./scripts/vps/connect-tailscale.sh
source "$HOME/.tailscale-openclaw/proxy.env"
./scripts/vps/remote-exec.sh 'sudo -u stan -H bash -lc "export XDG_RUNTIME_DIR=/run/user/1001; openclaw gateway status"'
./scripts/vps/openclaw-status.sh
```

Required secrets: `TAILSCALE_AUTHKEY`, `OPENCLAW_VPS_HOST`, `OPENCLAW_VPS_USER`, `OPENCLAW_VPS_SSH_PRIVATE_KEY`, `OPENCLAW_GATEWAY_TOKEN`, and a valid `XAI_API_KEY` from https://console.x.ai for Grok.
