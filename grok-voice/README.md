# Grok Voice Agent artifacts

Ready-to-paste materials for Voice Agent Builder / Voice Agent API.

| File | Use |
| --- | --- |
| `prompts/system.md` | Agent instructions / system prompt |
| `configs/tools.json` | Function-calling tool schemas (non-MCP path) |
| `configs/voice-agent-mcp.json` | Recommended Remote MCP attachment config |
| `examples/dialogues.md` | Confirmation-style spoken flows |

## Builder checklist

1. Create agent **OpenClaw Voice Control**
2. Paste `prompts/system.md`
3. Attach MCP using `configs/voice-agent-mcp.json` values
4. Start with read-only `allowed_tools`
5. Voice: `eve` (or your preference)
6. Guardrail: confirm before write/state changes
