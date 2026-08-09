# OpenclawDev

Operator tooling and docs for Stan's Hostinger OpenClaw gateway (Telegram + Cursor via Tailscale).

## Quick start (Cloud Agent)

```bash
# Install Tailscale + netcat in the agent VM first, then:
./scripts/vps/connect-tailscale.sh
source "$HOME/.tailscale-openclaw/proxy.env"
./scripts/vps/openclaw-status.sh
```

## Docs

- [`deploy/cursor-operator-access.md`](deploy/cursor-operator-access.md) — Cursor ↔ VPS access model and secrets
- [`deploy/openclaw-vps-ops.md`](deploy/openclaw-vps-ops.md) — safe updates, Grok/xAI, security baseline

Live OpenClaw runs as user **`stan`**. Ignore/delete any `/root/.openclaw` leftovers.
