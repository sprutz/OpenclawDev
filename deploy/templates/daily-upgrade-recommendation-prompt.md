# Daily OpenClaw assistant upgrade recommendation

You are recommending **one** concrete improvement that would make OpenClaw a better personal/ops assistant for Stan (QDS Systems).

## Context to review
- `/home/stan/clawd/TOOLS.md`
- `/home/stan/clawd/skills/` (existing skills)
- Recent Second Brain journals under `/home/stan/clawd/second-brain/journal/`
- Prior suggestions under `/opt/openclaw-voice-bridge/data/assistant-upgrades/` (avoid repeats)
- Current OpenClaw ↔ Grok Voice bridge capabilities

## Output (required)
Write **exactly one** recommendation as JSON to:

`/opt/openclaw-voice-bridge/data/assistant-upgrades/YYYY-MM-DD.json`

(use today's date) with this shape:

```json
{
  "id": "YYYY-MM-DD",
  "date": "YYYY-MM-DD",
  "title": "short title",
  "summary": "one or two spoken sentences",
  "rationale": "why this helps Stan now",
  "category": "skill|tool|bridge|workflow|integration",
  "implementation_prompt": "detailed instructions for a Cursor cloud agent to implement, test, deploy to the VPS via scripts/vps, commit, push, and open/update a PR. Be specific about files and acceptance checks. Do not ask Stan to paste console values.",
  "status": "pending"
}
```

Also write a short markdown mirror at the same path with `.md` instead of `.json`, and copy the markdown to:

`/home/stan/clawd/second-brain/docs/assistant-upgrades/YYYY-MM-DD.md`

## Selection rules
- Prefer high-leverage, implementable-in-one-agent-run upgrades
- Prefer skills/tools that reduce Stan's manual work (clients, Second Brain, voice, Telegram, calendar, industrial ops)
- One recommendation only — best of the day
- Keep `summary` easy to speak aloud
- End your Telegram reply with the title + summary so Stan can approve by voice later
