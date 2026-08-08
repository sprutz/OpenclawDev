from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .audit import AuditLogger
from .config import Settings
from .openclaw_client import OpenClawClient, OpenClawError, TelegramBridge

Priority = Literal["low", "normal", "high", "urgent"]
SessionAction = Literal["start", "pause", "resume", "stop"]


class ToolResult(BaseModel):
    ok: bool
    tool: str
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    needs_confirmation: bool = False
    spoken_hint: str | None = None


class VoiceTools:
    """Maps Grok Voice tool calls onto OpenClaw (and optional Telegram)."""

    WRITE_TOOLS = {"openclaw_assign_task", "openclaw_control_session"}

    def __init__(
        self,
        settings: Settings,
        openclaw: OpenClawClient,
        telegram: TelegramBridge,
        audit: AuditLogger,
    ) -> None:
        self.settings = settings
        self.openclaw = openclaw
        self.telegram = telegram
        self.audit = audit

    async def dispatch(self, name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
        args = arguments or {}
        handlers = {
            "openclaw_list_agents": self.list_agents,
            "openclaw_get_status": self.get_status,
            "openclaw_assign_task": self.assign_task,
            "openclaw_control_session": self.control_session,
            "openclaw_get_summary": self.get_summary,
            "openclaw_health": self.health,
        }
        handler = handlers.get(name)
        if handler is None:
            result = ToolResult(ok=False, tool=name, error=f"Unknown tool: {name}")
            self.audit.log(tool=name, args=args, error=result.error)
            return result
        try:
            result = await handler(**args)
        except TypeError as exc:
            result = ToolResult(ok=False, tool=name, error=f"Invalid arguments: {exc}")
        except OpenClawError as exc:
            result = ToolResult(ok=False, tool=name, error=str(exc), data={"payload": exc.payload})
        except Exception as exc:  # noqa: BLE001 - surface unexpected failures to voice layer
            result = ToolResult(ok=False, tool=name, error=f"Unexpected error: {exc}")
        self.audit.log(
            tool=name,
            args=args,
            result=result.model_dump(),
            error=result.error,
            confirmed=args.get("confirmed"),
        )
        return result

    def _gate_write(self, tool: str, confirmed: bool | None) -> ToolResult | None:
        if not self.settings.enable_write_tools:
            return ToolResult(
                ok=False,
                tool=tool,
                error=(
                    "Write tools are disabled. Set ENABLE_WRITE_TOOLS=true after validating "
                    "read-only voice control."
                ),
                spoken_hint="Write actions are currently locked. I can still check status.",
            )
        if self.settings.require_confirmation and not confirmed:
            return ToolResult(
                ok=False,
                tool=tool,
                needs_confirmation=True,
                error="Confirmation required before changing OpenClaw state.",
                spoken_hint="Please confirm before I make that change.",
            )
        return None

    async def health(self) -> ToolResult:
        data = await self.openclaw.health()
        return ToolResult(
            ok=bool(data.get("ok")),
            tool="openclaw_health",
            data=data,
            spoken_hint="Gateway is healthy." if data.get("ok") else "Gateway health check failed.",
        )

    async def list_agents(self) -> ToolResult:
        data = await self.openclaw.list_agents()
        return ToolResult(
            ok=True,
            tool="openclaw_list_agents",
            data=data,
            spoken_hint="Here are the active OpenClaw agents.",
        )

    async def get_status(self, target: str) -> ToolResult:
        target = (target or "").strip()
        if not target:
            raise OpenClawError("target is required")

        bundle: dict[str, Any] = {"target": target}
        # Always include gateway status context.
        bundle["gateway"] = await self.openclaw.gateway_status()

        lowered = target.lower()
        if lowered in {"gateway", "openclaw", "orchestrator", "system"}:
            return ToolResult(
                ok=True,
                tool="openclaw_get_status",
                data=bundle,
                spoken_hint="Gateway status retrieved.",
            )

        # Try task lookup when it looks like an id; otherwise inspect sessions + agent chat.
        if _looks_like_id(target):
            try:
                bundle["task"] = await self.openclaw.get_task(target)
            except OpenClawError as exc:
                bundle["task_error"] = str(exc)

        try:
            bundle["sessions"] = await self.openclaw.list_sessions()
        except OpenClawError as exc:
            bundle["sessions_error"] = str(exc)

        try:
            reply = await self.openclaw.chat_completions(
                f"Voice control status check for: {target}. "
                "Reply with a concise operational status only.",
                agent=target if not _looks_like_id(target) else None,
            )
            bundle["agent_report"] = reply
        except OpenClawError as exc:
            bundle["agent_report_error"] = str(exc)

        return ToolResult(
            ok=True,
            tool="openclaw_get_status",
            data=bundle,
            spoken_hint=f"Status for {target} retrieved.",
        )

    async def get_summary(self, target: str | None = None) -> ToolResult:
        focus = target or "all active agents and tasks"
        gateway = await self.openclaw.gateway_status()
        agents = await self.openclaw.list_agents()
        sessions = None
        sessions_error = None
        try:
            sessions = await self.openclaw.list_sessions()
        except OpenClawError as exc:
            sessions_error = str(exc)
        try:
            narrative = await self.openclaw.chat_completions(
                f"Voice control summary request covering: {focus}. "
                "Give a short spoken-friendly operations summary.",
            )
        except OpenClawError as exc:
            narrative = None
            narrative_error = str(exc)
        else:
            narrative_error = None

        return ToolResult(
            ok=True,
            tool="openclaw_get_summary",
            data={
                "focus": focus,
                "gateway": gateway,
                "agents": agents,
                "sessions": sessions,
                "sessions_error": sessions_error,
                "summary": narrative,
                "summary_error": narrative_error,
            },
            spoken_hint="Summary ready.",
        )

    async def assign_task(
        self,
        description: str,
        agent: str | None = None,
        priority: Priority = "normal",
        confirmed: bool = False,
    ) -> ToolResult:
        gate = self._gate_write("openclaw_assign_task", confirmed)
        if gate:
            return gate
        if not description or not description.strip():
            raise OpenClawError("description is required")

        mode = self.settings.backend_mode
        if mode in {"gateway", "hybrid"}:
            try:
                data = await self.openclaw.assign_task(
                    description.strip(),
                    agent=agent,
                    priority=priority,
                )
                data["transport"] = "gateway"
                return ToolResult(
                    ok=True,
                    tool="openclaw_assign_task",
                    data=data,
                    spoken_hint="Task assigned.",
                )
            except OpenClawError:
                if mode != "hybrid":
                    raise

        message = (
            f"[Grok Voice → OpenClaw]\n"
            f"Priority: {priority}\n"
            f"Agent: {agent or self.settings.openclaw_default_agent}\n"
            f"Task: {description.strip()}"
        )
        data = await self.telegram.send_message(message)
        return ToolResult(
            ok=True,
            tool="openclaw_assign_task",
            data={**data, "priority": priority, "agent": agent, "description": description},
            spoken_hint="Task sent through Telegram.",
        )

    async def control_session(
        self,
        action: SessionAction,
        target: str | None = None,
        confirmed: bool = False,
    ) -> ToolResult:
        gate = self._gate_write("openclaw_control_session", confirmed)
        if gate:
            return gate
        data = await self.openclaw.control_session(action, target)
        return ToolResult(
            ok=True,
            tool="openclaw_control_session",
            data=data,
            spoken_hint=f"Session {action} completed.",
        )


def tool_specs(*, include_write_tools: bool = True) -> list[dict[str, Any]]:
    """Grok Voice / OpenAI-style function tool definitions."""
    tools: list[dict[str, Any]] = [
        {
            "type": "function",
            "name": "openclaw_health",
            "description": "Check OpenClaw gateway health and connectivity",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "type": "function",
            "name": "openclaw_list_agents",
            "description": "List all configured OpenClaw agents and related model aliases",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "type": "function",
            "name": "openclaw_get_status",
            "description": "Get detailed status of a gateway, agent, task, or project",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Agent name, task ID, project name, or 'gateway'",
                    }
                },
                "required": ["target"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "openclaw_get_summary",
            "description": "Get a concise operational summary across agents/tasks",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Optional focus area (agent, project, or omit for all)",
                    }
                },
                "additionalProperties": False,
            },
        },
    ]
    if include_write_tools:
        tools.extend(
            [
                {
                    "type": "function",
                    "name": "openclaw_assign_task",
                    "description": (
                        "Assign a new task to an OpenClaw agent or the orchestrator. "
                        "Requires confirmed=true after explicit user confirmation."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "agent": {
                                "type": "string",
                                "description": "Optional agent id/name. Defaults to orchestrator/main.",
                            },
                            "description": {
                                "type": "string",
                                "description": "Clear task description to execute",
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["low", "normal", "high", "urgent"],
                                "description": "Task priority",
                            },
                            "confirmed": {
                                "type": "boolean",
                                "description": "Must be true after the user explicitly confirms",
                            },
                        },
                        "required": ["description"],
                        "additionalProperties": False,
                    },
                },
                {
                    "type": "function",
                    "name": "openclaw_control_session",
                    "description": (
                        "Start, pause, resume, or stop an agent/task session. "
                        "Requires confirmed=true after explicit user confirmation."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["start", "pause", "resume", "stop"],
                            },
                            "target": {
                                "type": "string",
                                "description": "Agent name or task ID",
                            },
                            "confirmed": {
                                "type": "boolean",
                                "description": "Must be true after the user explicitly confirms",
                            },
                        },
                        "required": ["action"],
                        "additionalProperties": False,
                    },
                },
            ]
        )
    return tools


def _looks_like_id(value: str) -> bool:
    cleaned = value.strip()
    if len(cleaned) < 6:
        return False
    return all(ch.isalnum() or ch in "-_" for ch in cleaned)
