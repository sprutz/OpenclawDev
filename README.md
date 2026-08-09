# OpenclawDev — Grok Voice control for OpenClaw

Connect **Grok Voice** (xAI Voice Agent API / Builder) to your self-hosted **OpenClaw** orchestrator on a Hostinger VPS (currently used via Telegram).

```text
  Grok Voice (Realtime API or Builder)
            |
            | HTTPS MCP (Tailscale Funnel)
            v
  OpenClaw Voice Bridge (:8787)
            |
            v
  OpenClaw gateway (user stan)
```

Why MCP: Grok Voice has native **remote MCP** support, so xAI executes tools server-side against your bridge. That means the MCP URL must be **public HTTPS** (Tailscale Funnel in front of the loopback bridge).

## Operator path (Cursor updates everything)

Cursor Cloud Agents own:

1. Bridge code + systemd on the VPS
2. Prompt / MCP artifacts (`scripts/vps/sync-voice-artifacts.sh`)
3. Spoken unlock env (`VOICE_SPOKEN_PASSWORD`)
4. Pushing the saved xAI Voice Agent when the Agents API is enabled (`scripts/vps/update-xai-voice-agent.py`)

Artifacts live in `grok-voice/` and are mirrored on the VPS — operators should not need to hand-edit the xAI console.

```bash
# Sync prompt/MCP/docs + restart bridge
./scripts/vps/sync-voice-artifacts.sh

# Update saved Voice Agent via xAI Agents API (requires team enablement)
XAI_API_KEY=... BRIDGE_API_KEY=... MCP_PUBLIC_HOSTS=... \
  ./scripts/vps/update-xai-voice-agent.py
```

If `update-xai-voice-agent.py` exits 3, the team’s Agents API is still disabled (`/v1/agents` 403). That is the only xAI console gate; enable it once so agents can keep the Builder agent in sync without UI edits.

Bridge helpers:

- `GET /v1/voice-agent/session` — full `session.update` (prompt + MCP URL from `MCP_PUBLIC_HOSTS`)
- `POST /v1/voice-agent/client-secret` — short-lived realtime token (needs `XAI_API_KEY` on bridge)

## Quick start

1. Deploy OpenClaw on the VPS (user `stan`).
2. Install / restart the bridge — see [`deploy/hostinger-setup.md`](deploy/hostinger-setup.md).
3. Set `.env`:
   - `BRIDGE_API_KEY`
   - `OPENCLAW_GATEWAY_TOKEN`
   - `MCP_PUBLIC_HOSTS=<funnel-host>`
   - `VOICE_SPOKEN_PASSWORD=pursuewithenthusiasm` (speak “pursue with enthusiasm”)
   - optional `XAI_API_KEY` for client-secret minting
4. Publish MCP with Tailscale Funnel.
5. Run the sync + update scripts above (Cursor does this).
6. After clean read-only sessions, set `ENABLE_WRITE_TOOLS=true`.

## Safety defaults

- Write tools off until `ENABLE_WRITE_TOOLS`
- `confirmed=true` required for state changes
- Spoken unlock gate before other tools
- Bearer auth + rate limit + JSONL audit log
- Bridge on `127.0.0.1`; public only via Tailscale Funnel

## Cursor as operator (Hostinger VPS)

See [`deploy/cursor-operator-access.md`](deploy/cursor-operator-access.md) and [`deploy/openclaw-vps-ops.md`](deploy/openclaw-vps-ops.md). Live OpenClaw runs as **`stan`**.

## Company context

Configured for **QDS Systems** industrial control workflows.
