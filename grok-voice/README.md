# Grok Voice Agent artifacts

Source of truth for the OpenClaw voice agent. Cursor syncs these to the VPS and pushes them to xAI when the Agents API is available.

| File | Use |
| --- | --- |
| `prompts/system.md` | Agent instructions (spoken unlock + tools) |
| `configs/tools.json` | Function-calling schemas (non-MCP path) |
| `configs/voice-agent-mcp.json` | Remote MCP attachment config |
| `examples/dialogues.md` | Unlock + confirmation spoken flows |

## Spoken unlock

- Bridge env: `VOICE_SPOKEN_PASSWORD=pursuewithenthusiasm` (no spaces)
- User may speak: “pursue with enthusiasm”
- Agent calls `openclaw_voice_unlock` with `passphrase=pursuewithenthusiasm`
- Bridge compact-matches spaced / punctuated STT

## How config is applied

1. Edit files here in git
2. `scripts/vps/sync-voice-artifacts.sh` → VPS copies + bridge restart
3. `scripts/vps/update-xai-voice-agent.py` → saved xAI agent (when `/v1/agents` is enabled)

VPS mirrors:

- `/opt/openclaw-voice-bridge/grok-voice/...`
- `/root/openclaw-backups/voice-agent-system.md`
- `/home/stan/clawd/second-brain/docs/voice-agent-system.md`
