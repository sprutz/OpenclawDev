from __future__ import annotations

import pytest

from openclaw_voice_bridge.audit import AuditLogger
from openclaw_voice_bridge.config import Settings
from openclaw_voice_bridge.tools import VoiceTools, normalize_passphrase


class _DummyOpenClaw:
    async def health(self):
        return {"ok": True}


class _DummyTelegram:
    pass


@pytest.mark.asyncio
async def test_voice_unlock_gate(tmp_path):
    settings = Settings(
        bridge_api_key="k",
        openclaw_gateway_token="g",
        audit_log_path=str(tmp_path / "a.jsonl"),
        voice_spoken_password="Quebec Delta Seven",
        voice_unlock_ttl_seconds=600,
        enable_write_tools=False,
    )
    tools = VoiceTools(settings, _DummyOpenClaw(), _DummyTelegram(), AuditLogger(settings.audit_log_path))

    locked = await tools.dispatch("openclaw_health")
    assert locked.ok is False
    assert locked.data.get("locked") is True

    bad = await tools.dispatch("openclaw_voice_unlock", {"passphrase": "wrong phrase"})
    assert bad.ok is False

    still = await tools.dispatch("openclaw_health")
    assert still.ok is False

    ok = await tools.dispatch("openclaw_voice_unlock", {"passphrase": "quebec delta seven"})
    assert ok.ok is True

    health = await tools.dispatch("openclaw_health")
    assert health.ok is True


def test_normalize_passphrase():
    assert normalize_passphrase("  Quebec, Delta-Seven! ") == "quebec delta seven"
