# OpenClaw Voice Bridge

HTTP + MCP bridge that lets **Grok Voice** control an **OpenClaw** gateway.

## What it exposes

| Surface | Path | Purpose |
| --- | --- | --- |
| Health | `GET /healthz` | Liveness |
| Tool catalog | `GET /v1/tools` | Function schemas for Voice Agent Builder / API |
| Tool invoke | `POST /v1/tools/invoke` | Execute one tool |
| Named invoke | `POST /v1/tools/{name}` | Convenience invoke |
| Voice session fragment | `GET /v1/voice-agent/session` | `session.update` JSON for Grok Voice |
| MCP (recommended) | `/mcp` | Remote MCP for Grok Voice Agent Builder |

All authenticated routes require:

`Authorization: Bearer $BRIDGE_API_KEY`  
(or `X-API-Key: $BRIDGE_API_KEY`)

## Tools

Read-only (default enabled):

- `openclaw_health`
- `openclaw_list_agents`
- `openclaw_get_status`
- `openclaw_get_summary`

Write (disabled until `ENABLE_WRITE_TOOLS=true`):

- `openclaw_assign_task` (requires `confirmed=true`)
- `openclaw_control_session` (requires `confirmed=true`)

## Local run

```bash
cd bridge
python3 -m pip install -r requirements.txt
export BRIDGE_API_KEY=dev-bridge-key
export OPENCLAW_GATEWAY_TOKEN=dev-gateway-token
export OPENCLAW_BASE_URL=http://127.0.0.1:18789
export ENABLE_WRITE_TOOLS=false
export AUDIT_LOG_PATH=./audit.jsonl
PYTHONPATH=src python3 -m openclaw_voice_bridge.app
```

## Tests

```bash
cd bridge
PYTHONPATH=src python3 -m pytest -q
```
