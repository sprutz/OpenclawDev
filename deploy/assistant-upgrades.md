# Daily assistant upgrade suggestions

OpenClaw proposes **one** tool/skill upgrade each day. Stan can approve it by voice; the bridge then launches a Cursor cloud agent to build, test, and open a PR.

## Flow

```text
22:00 UTC OpenClaw cron
   → writes /opt/openclaw-voice-bridge/data/assistant-upgrades/YYYY-MM-DD.json
   → mirrors markdown + Second Brain copy
   → Telegram announce

Voice (after unlock)
   “What’s today’s upgrade suggestion?” → openclaw_get_upgrade
   “Approve it” / “Build it”           → openclaw_approve_upgrade (confirmed=true)
   “Reject it”                         → openclaw_reject_upgrade (confirmed=true)

Approve
   → POST https://api.cursor.com/v1/agents
   → Cursor implements/tests/PRs on OpenclawDev
```

## Setup (Cursor operator)

```bash
./scripts/vps/setup-daily-upgrade-cron.sh
./scripts/vps/sync-voice-artifacts.sh
```

Bridge `.env`:

```env
ENABLE_UPGRADE_APPROVALS=true
ASSISTANT_UPGRADES_ROOT=/opt/openclaw-voice-bridge/data/assistant-upgrades
CURSOR_API_KEY=...                 # from https://cursor.com/dashboard/api
CURSOR_REPO_URL=https://github.com/sprutz/OpenclawDev
CURSOR_STARTING_REF=main
CURSOR_AUTO_CREATE_PR=true
```

Without `CURSOR_API_KEY`, voice approve still records approval as `queued_no_api_key` so nothing is lost.

## Voice examples

- “What’s today’s suggestion?”
- “Approve it” / “Build that”
- “Reject that for now”
