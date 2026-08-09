# Grok Voice Agent artifacts

Ready-to-paste materials for Voice Agent Builder / Voice Agent API.

| File | Use |
| --- | --- |
| `prompts/system.md` | Agent instructions / system prompt (includes spoken unlock) |
| `configs/tools.json` | Function-calling tool schemas (non-MCP path) |
| `configs/voice-agent-mcp.json` | Recommended Remote MCP attachment config |
| `examples/dialogues.md` | Unlock + confirmation-style spoken flows |

## Spoken unlock

- Bridge env: `VOICE_SPOKEN_PASSWORD=pursuewithenthusiasm` (no spaces)
- User may speak: “pursue with enthusiasm”
- Agent must call `openclaw_voice_unlock` with `passphrase=pursuewithenthusiasm`
- Bridge accepts spaced or compacted speech via compact matching

## Builder checklist

1. Create / open agent **OpenClaw Voice Control**
2. Replace instructions with `prompts/system.md` (VPS copies listed in `voice-agent-mcp.json` → `rollout_notes.vps_instruction_copies`)
3. Attach MCP using `configs/voice-agent-mcp.json` values
4. Ensure `openclaw_voice_unlock` is first in `allowed_tools`
5. Voice: `eve` (or your preference)
6. Guardrail: confirm before write/state changes
