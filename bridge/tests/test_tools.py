from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from openclaw_voice_bridge.app import create_app
from openclaw_voice_bridge.audit import AuditLogger
from openclaw_voice_bridge.config import Settings
from openclaw_voice_bridge.openclaw_client import OpenClawClient, OpenClawError, TelegramBridge
from openclaw_voice_bridge.tools import VoiceTools


class FakeOpenClaw(OpenClawClient):
    def __init__(self) -> None:  # noqa: ANN204
        self.settings = Settings(
            bridge_api_key="test-bridge-key",
            openclaw_gateway_token="test-gateway-token",
            enable_write_tools=True,
            require_confirmation=True,
            audit_log_path="audit-test.jsonl",
            backend_mode="gateway",
        )
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def aclose(self) -> None:
        return None

    async def health(self) -> dict[str, Any]:
        self.calls.append(("health", {}))
        return {"ok": True, "source": "admin-rpc", "payload": {"status": "ok"}}

    async def list_agents(self) -> dict[str, Any]:
        self.calls.append(("list_agents", {}))
        return {"source": "admin-rpc", "agents": [{"id": "main"}, {"id": "ops"}]}

    async def gateway_status(self) -> dict[str, Any]:
        return {"source": "admin-rpc", "status": {"runtime": "running"}}

    async def list_sessions(self) -> Any:
        return [{"key": "main", "state": "idle"}]

    async def get_task(self, task_id: str) -> Any:
        return {"id": task_id, "state": "running"}

    async def chat_completions(self, message: str, *, agent: str | None = None, model: str | None = None) -> str:
        self.calls.append(("chat", {"message": message, "agent": agent, "model": model}))
        return f"ack:{agent or 'main'}:{message[:40]}"

    async def assign_task(self, description: str, *, agent: str | None = None, priority: str = "normal") -> dict[str, Any]:
        self.calls.append(("assign", {"description": description, "agent": agent, "priority": priority}))
        return {
            "accepted": True,
            "agent": agent or "main",
            "priority": priority,
            "description": description,
            "reply": "queued",
        }

    async def control_session(self, action: str, target: str | None = None) -> dict[str, Any]:
        return {"action": action, "target": target or "main", "reply": "ok"}


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        bridge_api_key="test-bridge-key",
        openclaw_gateway_token="test-gateway-token",
        enable_write_tools=False,
        require_confirmation=True,
        audit_log_path=str(tmp_path / "audit.jsonl"),
        backend_mode="gateway",
        host="127.0.0.1",
        port=8787,
    )


@pytest.mark.asyncio
async def test_list_agents_and_confirmation_gate(tmp_path):
    settings = Settings(
        bridge_api_key="k",
        openclaw_gateway_token="g",
        enable_write_tools=True,
        require_confirmation=True,
        audit_log_path=str(tmp_path / "a.jsonl"),
    )
    oc = FakeOpenClaw()
    tools = VoiceTools(settings, oc, TelegramBridge(settings), AuditLogger(str(tmp_path / "a.jsonl")))

    listed = await tools.dispatch("openclaw_list_agents")
    assert listed.ok
    assert listed.data["agents"][0]["id"] == "main"

    blocked = await tools.dispatch(
        "openclaw_assign_task",
        {"description": "draft checklist", "priority": "high", "confirmed": False},
    )
    assert not blocked.ok
    assert blocked.needs_confirmation

    assigned = await tools.dispatch(
        "openclaw_assign_task",
        {"description": "draft checklist", "priority": "high", "confirmed": True},
    )
    assert assigned.ok
    assert assigned.data["accepted"] is True


@pytest.mark.asyncio
async def test_write_tools_disabled(tmp_path):
    settings = Settings(
        bridge_api_key="k",
        openclaw_gateway_token="g",
        enable_write_tools=False,
        require_confirmation=True,
        audit_log_path=str(tmp_path / "a.jsonl"),
    )
    tools = VoiceTools(settings, FakeOpenClaw(), TelegramBridge(settings), AuditLogger(str(tmp_path / "a.jsonl")))
    result = await tools.dispatch(
        "openclaw_control_session",
        {"action": "pause", "target": "ops", "confirmed": True},
    )
    assert not result.ok
    assert "Write tools are disabled" in (result.error or "")


@pytest.mark.asyncio
async def test_http_auth_and_invoke(settings: Settings, monkeypatch):
    # Avoid loading .env required fields through get_settings in factory path.
    app = create_app(settings)
    # Replace tools with fakes bound to app state
    fake = FakeOpenClaw()
    app.state.tools.openclaw = fake

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unauth = await client.get("/v1/tools")
        assert unauth.status_code == 401

        ok = await client.get("/v1/tools", headers={"Authorization": "Bearer test-bridge-key"})
        assert ok.status_code == 200
        assert any(t["name"] == "openclaw_list_agents" for t in ok.json()["tools"])

        # Patch dispatch target by swapping openclaw methods already done.
        # Force health through fake via tools object
        app.state.tools.openclaw = fake
        health = await client.post(
            "/v1/tools/invoke",
            headers={"Authorization": "Bearer test-bridge-key"},
            json={"name": "openclaw_health", "arguments": {}},
        )
        assert health.status_code == 200
        assert health.json()["ok"] is True


@pytest.mark.asyncio
async def test_get_status_bundles_context(tmp_path):
    settings = Settings(
        bridge_api_key="k",
        openclaw_gateway_token="g",
        enable_write_tools=False,
        audit_log_path=str(tmp_path / "a.jsonl"),
    )
    tools = VoiceTools(settings, FakeOpenClaw(), TelegramBridge(settings), AuditLogger(str(tmp_path / "a.jsonl")))
    result = await tools.dispatch("openclaw_get_status", {"target": "ops"})
    assert result.ok
    assert "gateway" in result.data
    assert "agent_report" in result.data


@pytest.mark.asyncio
async def test_telegram_hybrid_fallback(tmp_path, monkeypatch):
    settings = Settings(
        bridge_api_key="k",
        openclaw_gateway_token="g",
        enable_write_tools=True,
        require_confirmation=True,
        backend_mode="hybrid",
        telegram_bot_token="bot",
        telegram_chat_id="123",
        audit_log_path=str(tmp_path / "a.jsonl"),
    )

    class FailingAssign(FakeOpenClaw):
        async def assign_task(self, description: str, *, agent: str | None = None, priority: str = "normal"):
            raise OpenClawError("gateway down")

    class FakeTelegram(TelegramBridge):
        async def send_message(self, text: str) -> dict[str, Any]:
            return {"accepted": True, "transport": "telegram", "text": text}

    tools = VoiceTools(settings, FailingAssign(), FakeTelegram(settings), AuditLogger(str(tmp_path / "a.jsonl")))
    result = await tools.dispatch(
        "openclaw_assign_task",
        {"description": "ping via telegram", "confirmed": True},
    )
    assert result.ok
    assert result.data["transport"] == "telegram"
