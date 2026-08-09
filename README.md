# OpenclawDev — Grok Voice control for OpenClaw

Connect **Grok Voice** (xAI Voice Agent Builder / Voice Agent API) to your self-hosted **OpenClaw** orchestrator on a Hostinger VPS (currently used via Telegram).

## Recommended architecture

```text
Phone / Desktop / Tesla(BT)
        │
        ▼
  Grok Voice Agent
        │  Remote MCP (HTTPS over Tailscale)
        ▼
 OpenClaw Voice Bridge  ← this repo
        │  Gateway token on loopback/tailnet
        ▼
   OpenClaw Gateway
        │
   Telegram / agents / tools
```

Why MCP: Grok Voice has native **remote MCP** support, so xAI executes tools server-side against your bridge. No custom WebSocket function-call loop required for the Voice Agent Builder path.

## Repo layout

| Path | Contents |
| --- | --- |
| `bridge/` | FastAPI + MCP bridge service |
| `grok-voice/` | Ready-to-paste system prompt, tool JSON, MCP agent config, dialogue examples |
| `deploy/` | Hostinger/VPS + systemd notes |
| `docker-compose.yml` | Container deploy for the bridge |
| `.env.example` | Required secrets/config |

## Quick start (VPS)

1. Keep OpenClaw on private networking (Tailscale Serve or tailnet bind).
2. Enable OpenClaw admin HTTP RPC:
   ```bash
   openclaw plugins enable admin-http-rpc
   openclaw gateway restart
   ```
3. Copy `.env.example` → `.env` and set:
   - `BRIDGE_API_KEY`
   - `OPENCLAW_GATEWAY_TOKEN`
4. Start the bridge (`systemd` or `docker compose`) — see [`deploy/hostinger-setup.md`](deploy/hostinger-setup.md).
5. In Voice Agent Builder:
   - Paste [`grok-voice/prompts/system.md`](grok-voice/prompts/system.md)
   - Attach MCP from [`grok-voice/configs/voice-agent-mcp.json`](grok-voice/configs/voice-agent-mcp.json)
   - Start **read-only** (`allowed_tools` without assign/control)
6. After a few clean sessions, set `ENABLE_WRITE_TOOLS=true` and add write tools.

## Ready-to-paste artifacts

- System prompt: `grok-voice/prompts/system.md`
- Function schemas: `grok-voice/configs/tools.json`
- Voice Agent MCP config: `grok-voice/configs/voice-agent-mcp.json`
- Confirmation dialogues: `grok-voice/examples/dialogues.md`

## Safety defaults

- Write tools off until you flip `ENABLE_WRITE_TOOLS`
- `confirmed=true` required for state changes
- Bearer auth + rate limit + JSONL audit log
- Bind bridge to `127.0.0.1` and publish only via Tailscale

## Cursor as operator (Hostinger VPS)

To make Cursor Cloud Agents the main way you maintain OpenClaw:

1. Add Tailscale + SSH + gateway secrets (see [`deploy/cursor-operator-access.md`](deploy/cursor-operator-access.md))
2. Use `scripts/vps/*` from a Cloud Agent to join your tailnet and operate the VPS
3. Keep OpenClaw private (loopback/Tailscale only)

Live OpenClaw runs as user **`stan`**. Ops baseline (updates, Grok/xAI, security): [`deploy/openclaw-vps-ops.md`](deploy/openclaw-vps-ops.md).

## Company context

Configured for **QDS Systems** industrial control workflows. Edit company/agent names in the system prompt and `.env` as needed.
