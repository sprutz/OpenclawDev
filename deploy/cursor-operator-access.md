# Cursor as OpenClaw operator (Hostinger VPS)

Goal: every Cloud Agent working in `OpenclawDev` can safely reach and maintain your Hostinger OpenClaw install — without exposing the gateway to the public internet.

## Access model

```text
Cursor Cloud Agent VM
        │
        │ Tailscale userspace (SOCKS/HTTP proxy)
        ▼
   Your Tailnet
        │
        ▼
 Hostinger VPS (OpenClaw + optional voice bridge)
        │
        ├── SSH (operator shell / deploys)
        └── SSH tunnel → 127.0.0.1:18789 (gateway HTTP)
```

Cloud Agent VMs **cannot** use Tailscale's default TUN mode. Scripts in `scripts/vps/` start `tailscaled --tun=userspace-networking` and route SSH through the local SOCKS proxy.

## One-time setup (you)

### 1. Tailscale
1. Confirm the Hostinger VPS is logged into your tailnet.
2. Create an auth key for Cursor (reusable + ephemeral recommended, tagged e.g. `tag:cursor-cloud`).
3. ACL that tag so it can reach the VPS SSH port and (if desired) OpenClaw ports.

### 2. SSH
1. Generate a dedicated keypair for Cursor.
2. Install the public key on the VPS for your operator user.
3. Keep OpenClaw bound to loopback / Tailscale — not `0.0.0.0` public.

### 3. Cursor Secrets
Add these in [Cloud Agents secrets](https://cursor.com/dashboard/cloud-agents):

| Secret | Required | Purpose |
| --- | --- | --- |
| `TAILSCALE_AUTHKEY` | yes | Join Cursor VM to your tailnet |
| `OPENCLAW_VPS_HOST` | yes | MagicDNS name or `100.x` address |
| `OPENCLAW_VPS_USER` | yes | SSH user on the VPS |
| `OPENCLAW_VPS_SSH_PRIVATE_KEY` | yes | Private key PEM |
| `OPENCLAW_GATEWAY_TOKEN` | yes | Gateway bearer token |
| `BRIDGE_API_KEY` | optional | Voice bridge auth |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | optional | Telegram fallback path |
| `XAI_API_KEY` | optional | Direct Voice API experiments |

After secrets are saved, reply in the agent chat so setup can finish (environment snapshot/build + connectivity proof).

## Agent day-2 commands

```bash
# Join tailnet (userspace)
./scripts/vps/connect-tailscale.sh
source "$HOME/.tailscale-openclaw/proxy.env"

# SSH
./scripts/vps/ssh-vps.sh
./scripts/vps/remote-exec.sh 'openclaw gateway status'

# Health + tunnel to local 18789
./scripts/vps/openclaw-status.sh
```

## What Cursor will maintain once connected
- OpenClaw gateway health / channel probes
- Agent roster and task routing changes
- Voice bridge deploy/config (`bridge/`)
- Safe rollouts of new virtual-agent workforce definitions kept in this repo
- Audit of write-capable voice tools before enabling them

## What stays out of git
Never commit SSH keys, Tailscale auth keys, gateway tokens, Telegram tokens, or xAI keys. Use Cursor Secrets only.
