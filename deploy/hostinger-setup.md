# Hostinger VPS setup — Grok Voice → OpenClaw

This guide assumes OpenClaw is already running on the VPS and reachable over Telegram.

## 1) Prerequisites on the VPS

```bash
# Confirm OpenClaw gateway is healthy
openclaw gateway status
openclaw channels status --probe

# Enable admin HTTP RPC (recommended for clean status/list APIs)
openclaw plugins enable admin-http-rpc
openclaw gateway restart

# Verify
curl -sS http://127.0.0.1:18789/api/v1/admin/rpc \
  -H "Authorization: Bearer $OPENCLAW_GATEWAY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"method":"health","params":{}}'
```

Also ensure gateway auth token is set (`OPENCLAW_GATEWAY_TOKEN` or `gateway.auth.token`).

## 2) Private networking (strongly recommended)

Install and log in to Tailscale on the VPS and on any admin devices.

Preferred OpenClaw exposure patterns:

- Keep OpenClaw on loopback and use Tailscale Serve, **or**
- Bind OpenClaw to Tailnet only (`gateway.bind: "tailnet"`)

Do **not** expose `/tools/invoke`, admin RPC, or this voice bridge to the public internet.

## 3) Install the voice bridge

```bash
sudo mkdir -p /opt/openclaw-voice-bridge /var/log/openclaw-voice-bridge
sudo chown "$USER":"$USER" /opt/openclaw-voice-bridge /var/log/openclaw-voice-bridge

cd /opt
git clone https://github.com/sprutz/OpenclawDev.git openclaw-voice-bridge
cd openclaw-voice-bridge
cp .env.example .env
# edit .env: BRIDGE_API_KEY, OPENCLAW_GATEWAY_TOKEN, etc.
python3 -m pip install --user -r bridge/requirements.txt
```

### Option A — systemd

```bash
sudo cp deploy/systemd/openclaw-voice-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now openclaw-voice-bridge
sudo systemctl status openclaw-voice-bridge
```

### Option B — Docker Compose

```bash
# Ensure OPENCLAW_BASE_URL points at the host gateway
# e.g. OPENCLAW_BASE_URL=http://host.docker.internal:18789
docker compose up -d --build
docker compose logs -f
```

## 4) Expose only the bridge over Tailscale

Example with Tailscale Serve to the local bridge:

```bash
# bridge listening on 127.0.0.1:8787
tailscale serve --bg --https=443 http://127.0.0.1:8787
tailscale serve status
```

Your MCP URL becomes:

`https://<vps-magicdns-name>.ts.net/mcp`

## 5) Create the Grok Voice agent

1. Open [xAI Voice Agent Builder](https://x.ai) / console Voice Agent Builder.
2. Create agent: **OpenClaw Voice Control**.
3. Paste instructions from `grok-voice/prompts/system.md`.
4. Attach MCP tool from `grok-voice/configs/voice-agent-mcp.json`:
   - `server_url`: `https://<your-tailscale-host>/mcp`
   - `authorization`: same value as `BRIDGE_API_KEY`
   - Start with read-only `allowed_tools` only.
5. Choose voice (`eve` recommended to start).
6. Add guardrail: require confirmation for state-changing actions.
7. Test in the playground:
   - “Check OpenClaw health”
   - “List agents”
   - “What’s the gateway status?”

## 6) Roll out writes safely

Only after read-only sessions look good:

1. Set `ENABLE_WRITE_TOOLS=true` in `.env` and restart the bridge.
2. Add write tools to the Voice Agent MCP `allowed_tools`.
3. Keep `REQUIRE_CONFIRMATION=true`.
4. Monitor `/var/log/openclaw-voice-bridge/audit.jsonl`.

## 7) Optional Telegram temporary path

If gateway HTTP is not ready yet:

```env
BACKEND_MODE=telegram
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...   # your private chat with the OpenClaw bot
ENABLE_WRITE_TOOLS=true
```

This lets `openclaw_assign_task` inject a message into the same Telegram conversation you already use. Prefer `BACKEND_MODE=gateway` once admin RPC + chat completions are verified.

## 8) Quick smoke tests

```bash
export BRIDGE=http://127.0.0.1:8787
export KEY=your-bridge-api-key

curl -sS "$BRIDGE/healthz"

curl -sS "$BRIDGE/v1/tools" -H "Authorization: Bearer $KEY" | jq .

curl -sS "$BRIDGE/v1/tools/invoke" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"openclaw_health","arguments":{}}' | jq .
```

## 9) Phone / Tesla usage

- Phone/desktop: Grok app → select **OpenClaw Voice Control** → talk.
- Tesla for now: phone over Bluetooth hands-free using the same agent.
