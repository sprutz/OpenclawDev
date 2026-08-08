from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import Settings

logger = logging.getLogger("openclaw_voice_bridge.openclaw")


class OpenClawError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class OpenClawClient:
    """Thin async client over OpenClaw Gateway HTTP surfaces."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client or httpx.AsyncClient(
            base_url=settings.openclaw_base_url.rstrip("/"),
            headers=settings.openclaw_headers,
            timeout=settings.openclaw_timeout_seconds,
        )
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def admin_rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        body = {"method": method, "params": params or {}}
        response = await self._client.post("/api/v1/admin/rpc", json=body)
        return self._parse_admin(response, method)

    async def tools_invoke(
        self,
        tool: str,
        args: dict[str, Any] | None = None,
        *,
        session_key: str | None = None,
        agent_id: str | None = None,
    ) -> Any:
        payload: dict[str, Any] = {
            "tool": tool,
            "args": args or {},
            "sessionKey": session_key or self.settings.openclaw_session_key,
        }
        if agent_id:
            payload["agentId"] = agent_id
        response = await self._client.post("/tools/invoke", json=payload)
        if response.status_code >= 400:
            raise OpenClawError(
                f"/tools/invoke {tool} failed ({response.status_code}): {response.text}",
                status_code=response.status_code,
                payload=_safe_json(response),
            )
        data = response.json()
        if isinstance(data, dict) and data.get("ok") is False:
            err = data.get("error") or {}
            raise OpenClawError(
                err.get("message") or f"Tool {tool} failed",
                status_code=response.status_code,
                payload=data,
            )
        return data.get("result") if isinstance(data, dict) else data

    async def list_models(self) -> Any:
        response = await self._client.get("/v1/models")
        if response.status_code >= 400:
            raise OpenClawError(
                f"/v1/models failed ({response.status_code}): {response.text}",
                status_code=response.status_code,
                payload=_safe_json(response),
            )
        return response.json()

    async def chat_completions(
        self,
        message: str,
        *,
        agent: str | None = None,
        model: str | None = None,
    ) -> str:
        selected = model or f"openclaw/{agent or self.settings.openclaw_default_agent}"
        body = {
            "model": selected,
            "messages": [{"role": "user", "content": message}],
            "stream": False,
        }
        response = await self._client.post("/v1/chat/completions", json=body)
        if response.status_code >= 400:
            raise OpenClawError(
                f"/v1/chat/completions failed ({response.status_code}): {response.text}",
                status_code=response.status_code,
                payload=_safe_json(response),
            )
        data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenClawError("Unexpected chat completions response", payload=data) from exc

    async def health(self) -> dict[str, Any]:
        try:
            payload = await self.admin_rpc("health")
            return {"ok": True, "source": "admin-rpc", "payload": payload}
        except OpenClawError as admin_err:
            # Fall back to models probe when admin-http-rpc is disabled.
            try:
                models = await self.list_models()
                return {
                    "ok": True,
                    "source": "models",
                    "admin_rpc_error": str(admin_err),
                    "models": models,
                }
            except OpenClawError as models_err:
                return {
                    "ok": False,
                    "admin_rpc_error": str(admin_err),
                    "models_error": str(models_err),
                }

    async def list_agents(self) -> dict[str, Any]:
        try:
            agents = await self.admin_rpc("agents.list")
            return {"source": "admin-rpc", "agents": agents}
        except OpenClawError as err:
            models = await self.list_models()
            return {
                "source": "models-fallback",
                "warning": f"admin-http-rpc unavailable: {err}",
                "models": models,
            }

    async def gateway_status(self) -> dict[str, Any]:
        try:
            status = await self.admin_rpc("status")
            return {"source": "admin-rpc", "status": status}
        except OpenClawError:
            return await self.health()

    async def list_sessions(self) -> Any:
        return await self.tools_invoke("sessions_list", {})

    async def get_task(self, task_id: str) -> Any:
        return await self.admin_rpc("tasks.get", {"id": task_id})

    async def list_tasks(self) -> Any:
        return await self.admin_rpc("tasks.list", {})

    async def cancel_task(self, task_id: str) -> Any:
        return await self.admin_rpc("tasks.cancel", {"id": task_id})

    async def assign_task(
        self,
        description: str,
        *,
        agent: str | None = None,
        priority: str = "normal",
    ) -> dict[str, Any]:
        target = agent or self.settings.openclaw_default_agent
        prompt = (
            f"[Voice Control / priority={priority}] "
            f"Please execute the following task and report status clearly:\n\n{description}"
        )
        reply = await self.chat_completions(prompt, agent=target)
        return {
            "accepted": True,
            "agent": target,
            "priority": priority,
            "description": description,
            "reply": reply,
        }

    async def control_session(self, action: str, target: str | None = None) -> dict[str, Any]:
        action = action.lower().strip()
        if action == "start":
            agent = target or self.settings.openclaw_default_agent
            reply = await self.chat_completions(
                "Voice control: start or resume your active work session and summarize current focus.",
                agent=agent,
            )
            return {"action": action, "target": agent, "reply": reply}
        if action in {"pause", "stop"}:
            # Prefer task cancel when a task id is provided; otherwise instruct agent.
            if target and _looks_like_id(target):
                payload = await self.cancel_task(target)
                return {"action": action, "target": target, "result": payload}
            agent = target or self.settings.openclaw_default_agent
            verb = "pause" if action == "pause" else "stop"
            reply = await self.chat_completions(
                f"Voice control: {verb} non-critical active work and acknowledge.",
                agent=agent,
            )
            return {"action": action, "target": agent, "reply": reply}
        if action == "resume":
            agent = target or self.settings.openclaw_default_agent
            reply = await self.chat_completions(
                "Voice control: resume paused work and summarize next steps.",
                agent=agent,
            )
            return {"action": action, "target": agent, "reply": reply}
        raise OpenClawError(f"Unsupported session action: {action}")

    def _parse_admin(self, response: httpx.Response, method: str) -> Any:
        if response.status_code == 404:
            raise OpenClawError(
                "admin-http-rpc route not found. Enable with: openclaw plugins enable admin-http-rpc",
                status_code=404,
                payload=_safe_json(response),
            )
        data = _safe_json(response)
        if response.status_code >= 400:
            raise OpenClawError(
                f"admin-rpc {method} failed ({response.status_code}): {response.text}",
                status_code=response.status_code,
                payload=data,
            )
        if isinstance(data, dict) and data.get("ok") is False:
            err = data.get("error") or {}
            raise OpenClawError(
                err.get("message") or f"admin-rpc {method} failed",
                status_code=response.status_code,
                payload=data,
            )
        if isinstance(data, dict):
            return data.get("payload", data)
        return data


class TelegramBridge:
    """Optional temporary path: inject a message into the existing Telegram bot chat."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client or httpx.AsyncClient(timeout=settings.openclaw_timeout_seconds)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @property
    def configured(self) -> bool:
        return bool(self.settings.telegram_bot_token and self.settings.telegram_chat_id)

    async def send_message(self, text: str) -> dict[str, Any]:
        if not self.configured:
            raise OpenClawError("Telegram bridge is not configured")
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        response = await self._client.post(
            url,
            json={
                "chat_id": self.settings.telegram_chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
        )
        data = _safe_json(response)
        if response.status_code >= 400 or (isinstance(data, dict) and not data.get("ok", True)):
            raise OpenClawError(
                f"Telegram sendMessage failed: {response.text}",
                status_code=response.status_code,
                payload=data,
            )
        return {"accepted": True, "transport": "telegram", "result": data}


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text}


def _looks_like_id(value: str) -> bool:
    cleaned = value.strip()
    if len(cleaned) < 6:
        return False
    return all(ch.isalnum() or ch in "-_" for ch in cleaned)
