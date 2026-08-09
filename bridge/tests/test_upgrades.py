from __future__ import annotations

import json
from pathlib import Path

import pytest

from openclaw_voice_bridge import upgrades as ug
from openclaw_voice_bridge.audit import AuditLogger
from openclaw_voice_bridge.config import Settings
from openclaw_voice_bridge.tools import VoiceTools


class _Dummy:
    pass


@pytest.fixture()
def upgrades_dir(tmp_path: Path) -> Path:
    root = tmp_path / "upgrades"
    root.mkdir()
    return root


def _tools(upgrades_dir: Path, tmp_path: Path, **extra: object) -> VoiceTools:
    settings = Settings(
        bridge_api_key="test-key",
        openclaw_gateway_token="gw",
        audit_log_path=str(tmp_path / "audit.jsonl"),
        assistant_upgrades_root=str(upgrades_dir),
        enable_upgrade_approvals=True,
        require_confirmation=True,
        cursor_api_key="",
        voice_spoken_password="",
        **extra,
    )
    return VoiceTools(settings, _Dummy(), _Dummy(), AuditLogger(settings.audit_log_path))


def test_save_and_list_suggestions(upgrades_dir: Path) -> None:
    data = ug.save_suggestion(
        upgrades_dir,
        {
            "id": "2026-08-09",
            "date": "2026-08-09",
            "title": "Calendar brief skill",
            "summary": "Add a morning calendar brief skill.",
            "status": "pending",
            "implementation_prompt": "Build it",
        },
    )
    assert data["id"] == "2026-08-09"
    assert (upgrades_dir / "2026-08-09.json").is_file()
    assert (upgrades_dir / "2026-08-09.md").is_file()
    items = ug.list_suggestions(upgrades_dir, status="pending")
    assert len(items) == 1
    assert items[0]["title"] == "Calendar brief skill"


@pytest.mark.asyncio
async def test_get_and_approve_queues_without_cursor_key(
    upgrades_dir: Path, tmp_path: Path
) -> None:
    ug.save_suggestion(
        upgrades_dir,
        {
            "id": "2026-08-09",
            "date": "2026-08-09",
            "title": "Email triage skill",
            "summary": "Summarize unread QDS mail each morning.",
            "status": "pending",
            "implementation_prompt": "Implement email triage skill and tests.",
        },
    )
    tools = _tools(upgrades_dir, tmp_path)
    got = await tools.get_upgrade()
    assert got.ok
    assert "Email triage" in (got.spoken_hint or "")

    blocked = await tools.approve_upgrade(confirmed=False)
    assert blocked.needs_confirmation

    approved = await tools.approve_upgrade(confirmed=True)
    assert approved.ok
    assert approved.data["status"] == "queued_no_api_key"
    reloaded = ug.load_suggestion(upgrades_dir, "2026-08-09")
    assert reloaded["status"] == "queued_no_api_key"


@pytest.mark.asyncio
async def test_reject_upgrade(upgrades_dir: Path, tmp_path: Path) -> None:
    ug.save_suggestion(
        upgrades_dir,
        {
            "id": "2026-08-09",
            "date": "2026-08-09",
            "title": "Nope",
            "summary": "Skip me",
            "status": "pending",
        },
    )
    tools = _tools(upgrades_dir, tmp_path)
    result = await tools.reject_upgrade(confirmed=True, reason="not now")
    assert result.ok
    assert result.data["status"] == "rejected"
    assert json.loads((upgrades_dir / "2026-08-09.json").read_text())["rejection_reason"] == "not now"
