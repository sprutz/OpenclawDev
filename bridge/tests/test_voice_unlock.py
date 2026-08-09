from __future__ import annotations

import pytest

from openclaw_voice_bridge.audit import AuditLogger
from openclaw_voice_bridge.config import Settings
from openclaw_voice_bridge.tools import (
    VoiceTools,
    compact_passphrase,
    normalize_passphrase,
    passphrase_matches,
)


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
        voice_spoken_password="pursuewithenthusiasm",
        voice_unlock_ttl_seconds=600,
        enable_write_tools=False,
    )
    tools = VoiceTools(settings, _DummyOpenClaw(), _DummyTelegram(), AuditLogger(settings.audit_log_path))

    locked = await tools.dispatch("openclaw_health")
    assert locked.ok is False

    bad = await tools.dispatch("openclaw_voice_unlock", {"passphrase": "wrong phrase"})
    assert bad.ok is False

    # Spaced speech must unlock against compact stored password.
    ok = await tools.dispatch(
        "openclaw_voice_unlock",
        {"passphrase": "pursue with enthusiasm."},
    )
    assert ok.ok is True

    health = await tools.dispatch("openclaw_health")
    assert health.ok is True


def test_compact_and_match():
    assert compact_passphrase("pursue with enthusiasm.") == "pursuewithenthusiasm"
    assert compact_passphrase("PursueWithEnthusiasm!") == "pursuewithenthusiasm"
    assert passphrase_matches("pursue with enthusiasm.", "pursuewithenthusiasm")
    assert passphrase_matches("pursuewithenthusiasm", "pursue with enthusiasm")
    assert passphrase_matches("password is pursue with enthusiasm.", "pursuewithenthusiasm")
    assert not passphrase_matches("pursue with energy", "pursuewithenthusiasm")
    assert normalize_passphrase("  Pursue, with-Enthusiasm! ") == "pursue with enthusiasm"
